"""Behavioral tests for the showcase document.

The showcase is the output: one self-contained HTML file that details the
treatment of one program at every stage. These tests pin what it must say
and what it must not: every stage the job produced, a labeled not-reached
for every stage it did not, the checksummed receipt, and no external asset
anywhere in the document.
"""
import re
import json
import tempfile
import unittest
from html import unescape
from pathlib import Path

from .job import build_job
from .showcase import build_showcase

REPO = Path(__file__).resolve().parent.parent


def accepted_job():
    source = (REPO / 'examples' / 'workflow' / 'job.sas').read_text(encoding='utf-8')
    return build_job(source, REPO / 'examples' / 'workflow' / 'inputs.json',
                     REPO / 'examples' / 'workflow' / 'expected.json')


def blocked_job():
    return build_job('data d;\n  set raw;\n  d = count(x);\nrun;\n')


class ShowcaseTests(unittest.TestCase):
    def test_formatted_reports_are_visible_as_exact_escaped_text(self):
        source = (REPO / 'examples' / 'numeric_pictures.sas').read_text()
        job = build_job(source)
        self.assertTrue(job.receipt['accepted'])
        document = build_showcase(job, 'pictures')
        section = document.split('id="stage-run"', 1)[1].split('</section>', 1)[0]
        for name, content in job.result['reports'].items():
            self.assertIn(name, section)
            self.assertIn(content, unescape(section))

    def test_report_only_comparison_is_visible_in_compare_stage(self):
        source = (REPO / 'examples' / 'numeric_pictures.sas').read_text()
        expected = json.loads((REPO / 'examples' / 'numeric_pictures_expected.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'reports.json'
            path.write_text(json.dumps(expected['reports']))
            job = build_job(source, expect_reports=path)
        document = build_showcase(job, 'report evidence')
        section = document.split('id="stage-compare"', 1)[1].split('</section>', 1)[0]
        self.assertIn('Report comparison: passed', section)
        self.assertIn('Dataset comparison: not requested', section)

    def test_requested_comparison_before_execution_failure_is_not_reached(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'expected.json'
            path.write_text('{}')
            job = build_job('data d; set absent; run;', expect=path)
        self.assertEqual(job.receipt['comparison'], 'not reached')
        document = build_showcase(job, 'unreached comparison')
        self.assertIn('Dataset comparison: not reached', document)

    def test_report_html_is_escaped_and_rejected_output_is_labelled(self):
        job = build_job((REPO / 'examples/numeric_pictures.sas').read_text())
        job.result['reports'] = {'<report>.txt': '<script>alert("test")</script>\n'}
        job.receipt['accepted'] = False
        document = build_showcase(job, 'escaped report')
        section = document.split('id="stage-run"', 1)[1].split('</section>', 1)[0]
        self.assertNotIn('<script>', section)
        self.assertIn('&lt;report&gt;.txt', section)
        self.assertIn('&lt;script&gt;', section)
        self.assertIn('Execution output from a rejected job', section)

    def status(self, job):
        document = build_showcase(job, 'evidence status')
        self.assertNotIn('Python and R agree', document)
        self.assertNotIn('verified fixture evidence', document)
        status = re.search(r'<p class="status">(.*?)</p>', document, re.S)[1]
        self.assertIn('No per-job R comparison or live SAS validation was performed.', status)
        return status

    def test_uncompared_execution_does_not_claim_verification(self):
        job = build_job('data _null_; x=7; put x=; run;')
        self.assertTrue(job.receipt['accepted'])
        self.assertEqual(job.receipt['comparison'], 'not requested')
        for r_version in (None, 'Rscript (R) version available'):
            with self.subTest(r_version=r_version):
                job.receipt['environment']['r_version'] = r_version
                status = self.status(job)
                self.assertIn('Job verdict: accepted.', status)
                self.assertIn('Dataset comparison: not requested.', status)
                self.assertIn('R availability', status)

    def test_matching_expectation_claims_only_the_recorded_comparison(self):
        job = accepted_job()
        self.assertEqual(job.receipt['comparison'], 'passed')
        self.assertIn('Dataset comparison: passed.', self.status(job))

    def test_mismatching_expectation_reports_rejection_and_failed_comparison(self):
        with tempfile.TemporaryDirectory() as temporary:
            expected = Path(temporary) / 'wrong.json'
            expected.write_text(json.dumps({'d': {'schema': {'x': 'number'},
                                                   'rows': [{'x': 8.0}]}}))
            job = build_job('data d; x=7; run;', expect=expected)
        self.assertEqual(job.code, 1)
        self.assertIsNotNone(job.result)
        self.assertIn('Job verdict: rejected.', self.status(job))
        self.assertIn('Dataset comparison: failed.', self.status(job))

    def test_blocked_and_runtime_failed_jobs_do_not_claim_verification(self):
        for job, verdict in ((blocked_job(), 'blocked'),
                             (build_job('data d; set absent; run;'), 'rejected')):
            with self.subTest(verdict=verdict):
                self.assertFalse(job.receipt['accepted'])
                self.assertIsNone(job.result)
                self.assertIn(f'Job verdict: {verdict}.', self.status(job))
                self.assertIn('Dataset comparison: not requested.', self.status(job))

    def test_log_only_expectation_is_distinct_from_dataset_comparison(self):
        with tempfile.TemporaryDirectory() as temporary:
            expected = Path(temporary) / 'log.json'
            expected.write_text(json.dumps(['hello']))
            job = build_job("data _null_; put 'hello'; run;", expect_log=expected)
        self.assertEqual(job.code, 0)
        status = self.status(job)
        self.assertIn('Dataset comparison: not requested;', status)
        self.assertIn('Log comparison: passed.', status)

    def test_accepted_job_renders_every_stage_with_its_artifact(self):
        html = build_showcase(accepted_job(), 'workflow')
        for stage in ('stage-source', 'stage-plan', 'stage-translate', 'stage-run',
                      'stage-compare', 'stage-receipt'):
            self.assertIn(f'id="{stage}"', html)
        self.assertIn('ACCEPTED', html)
        self.assertIn('data rounded; set raw;', html)
        self.assertIn('Dataset comparison: passed', html)
        self.assertIn('proc sort data=rounded out=ordered', html)
        self.assertIn('receipt.json', html)

    def test_document_is_self_contained(self):
        html = build_showcase(accepted_job(), 'workflow')
        self.assertNotIn('<script src', html)
        self.assertNotIn('<link rel="stylesheet"', html)
        self.assertNotIn('@import', html)
        self.assertIsNone(re.search(r'url\(\s*["\']?https?:', html))
        self.assertNotIn('http://', html.replace('http://www.w3.org', ''))

    def test_blocked_job_labels_the_unreached_stages(self):
        html = build_showcase(blocked_job(), 'blocked')
        self.assertIn('BLOCKED', html)
        self.assertIn('unsupported expression', html)
        self.assertIn('Not reached', html)
        self.assertIn('inspection artifact, not an executable', html)

    def test_source_hash_is_on_the_face(self):
        job = accepted_job()
        html = build_showcase(job, 'workflow')
        self.assertIn(job.source_sha256, html)


if __name__ == '__main__':
    unittest.main()
