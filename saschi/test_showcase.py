"""Behavioral tests for the showcase document.

The showcase is the output: one self-contained HTML file that details the
treatment of one program at every stage. These tests pin what it must say
and what it must not: every stage the job produced, a labeled not-reached
for every stage it did not, the checksummed receipt, and no external asset
anywhere in the document.
"""
import re
import unittest
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
    def test_accepted_job_renders_every_stage_with_its_artifact(self):
        html = build_showcase(accepted_job(), 'workflow')
        for stage in ('stage-source', 'stage-plan', 'stage-translate', 'stage-run',
                      'stage-compare', 'stage-receipt'):
            self.assertIn(f'id="{stage}"', html)
        self.assertIn('ACCEPTED', html)
        self.assertIn('data rounded; set raw;', html)
        self.assertIn('comparison passed', html)
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
