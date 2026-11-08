"""Saved evidence and export boundaries using synthetic local fixtures only."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from .job import build_job
from .workspace import Workspace, compare_catalogs, comparison_report, file_identity


SOURCE = 'data net_sales;\n  merge orders returns;\n  by order_id;\n  net = gross - refunded;\nrun;\n'


def inputs(refunded=40):
    return {'orders': {'schema': {'order_id': 'number', 'gross': 'number'},
                       'rows': [{'order_id': i, 'gross': value} for i, value in enumerate([1200, 800, 1000, 450, 250, 1600], 1)]},
            'returns': {'schema': {'order_id': 'number', 'refunded': 'number'},
                        'rows': [{'order_id': i, 'refunded': value} for i, value in enumerate([100, 0, refunded, 25, 0, 200], 1)]},
            'private_unused': {'schema': {'private_value': 'number'}, 'rows': [{'private_value': 987654321}]}}


def expected():
    rows = [[1, 1200, 100, 1100], [2, 800, 0, 800], [3, 1000, 40, 950],
            [4, 450, 25, 425], [5, 250, 0, 250], [6, 1600, 200, 1400]]
    names = ['order_id', 'gross', 'refunded', 'net']
    return {'net_sales': {'schema': dict.fromkeys(names, 'number'),
                          'rows': [dict(zip(names, row)) for row in rows]}}


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.workspace = Workspace(self.folder / 'workspace')
        self.source = self.folder / 'program.sas'
        self.input = self.folder / 'inputs.json'
        self.sas = self.folder / 'sas-results.json'
        self.source.write_text(SOURCE)
        self.input.write_text(json.dumps(inputs()))
        self.sas.write_text(json.dumps(expected()))

    def job(self, compare=True):
        return build_job(self.source.read_text(), self.input, self.sas if compare else None)

    def identities(self):
        connected = file_identity(self.input, role='input')
        connected['datasets'] = list(inputs())
        return [file_identity(self.source, role='source'), connected,
                file_identity(self.sas, role='sas_result', dataset='net_sales')]

    def save(self, compare=True):
        identities = self.identities()
        return self.workspace.save_run(self.job(compare), files=identities,
                                       expected=expected() if compare else None,
                                       source_name=self.source.name)

    def test_reopen_retains_rejected_execution_without_reading_changed_originals(self):
        record = self.save()
        self.assertEqual(record['execution'], 'completed')
        self.assertFalse(record['receipt']['accepted'])
        self.assertEqual(record['comparison']['matched'], 23)
        self.assertEqual(record['comparison']['differed'], 1)
        self.assertEqual(list(record['result']['datasets']), ['net_sales'])
        self.input.unlink()
        self.source.write_text('a changed program')
        record['source'] = 'caller mutation'
        loaded = self.workspace.load_run(record['id'])
        self.assertEqual(loaded['source'], SOURCE)
        self.assertEqual(loaded['result']['datasets']['net_sales']['rows'][2]['net'], 960)
        states = {f['role']: f['status'] for f in self.workspace.check_files(record['id'])}
        self.assertEqual(states, {'source': 'changed', 'input': 'missing', 'sas_result': 'same'})

    def test_move_is_distinct_from_changed_content_and_unreadable(self):
        record = self.save()
        moved = self.folder / 'moved.json'
        self.input.rename(moved)
        binding = {record['files'][1]['id']: moved}
        self.assertEqual(self.workspace.check_files(record['id'], binding)[1]['status'], 'moved_same')
        moved.write_text('{}')
        self.assertEqual(self.workspace.check_files(record['id'], binding)[1]['status'], 'changed')
        binding[record['files'][1]['id']] = self.folder
        self.assertEqual(self.workspace.check_files(record['id'], binding)[1]['status'], 'unreadable')
        self.assertEqual(self.workspace.load_run(record['id'])['files'][1]['path'], str(self.input))

    def test_additional_comparison_does_not_replace_original_evidence(self):
        record = self.save()
        original_bytes = (self.workspace.root / record['id'] / 'record.json').read_bytes()
        actual = record['result']['datasets']
        attempt = self.workspace.add_comparison(record['id'], actual)
        loaded = self.workspace.load_run(record['id'])
        self.assertEqual(loaded['comparison']['status'], 'differed')
        self.assertEqual(loaded['comparison_attempts'][0]['summary']['status'], 'matched')
        self.assertEqual(loaded['comparison_attempts'][0]['summary']['matched'], 24)
        self.assertEqual(loaded['receipt']['comparison'], 'failed')
        self.assertEqual(loaded['comparison_attempts'][0]['id'], attempt['id'])
        self.assertEqual((self.workspace.root / record['id'] / 'record.json').read_bytes(), original_bytes)

    def test_between_run_changes_are_not_sas_difference_counts(self):
        earlier = self.save()
        self.input.write_text(json.dumps(inputs(50)))
        later = self.save()
        comparison = self.workspace.compare_runs(earlier['id'], later['id'])
        self.assertEqual(comparison['outputs']['differed'], 2)
        self.assertEqual(comparison['outputs']['matched'], 22)
        self.assertEqual(comparison['earlier_comparison']['differed'], 1)
        self.assertEqual(comparison['later_comparison']['differed'], 1)
        self.assertEqual(comparison['later_comparison']['datasets']['net_sales']['differences'][0]['variable'], 'refunded')
        self.assertEqual(comparison['program']['status'], 'same')
        self.assertEqual(comparison['files'][1]['status'], 'changed')
        self.assertEqual(comparison['files'][1]['values'], 'not_checked')
        self.assertEqual(comparison['original_differences'][0]['status'], 'now_matches')

    def test_available_original_input_versions_can_be_compared_without_output_substitution(self):
        earlier = self.save()
        original = self.input
        self.input = self.folder / 'inputs-v2.json'
        self.input.write_text(json.dumps(inputs(50)))
        later = self.save()
        comparison = self.workspace.compare_runs(earlier['id'], later['id'])
        self.assertEqual(comparison['files'][1]['values'], 'differed')
        self.assertEqual(comparison['files'][1]['value_comparison']['differed'], 1)
        self.assertEqual(comparison['outputs']['differed'], 2)
        original.unlink()
        unavailable = self.workspace.compare_runs(earlier['id'], later['id'])
        self.assertEqual(unavailable['files'][1]['values'], 'not_checked')
        self.assertEqual(unavailable['outputs']['differed'], 2)

    def test_new_baseline_and_missing_comparison_do_not_resolve_original_difference(self):
        earlier = self.save()
        replaced = deepcopy(earlier['result']['datasets'])
        self.sas.write_text(json.dumps(replaced))
        later = self.workspace.save_run(self.job(), files=self.identities(), expected=replaced)
        comparison = self.workspace.compare_runs(earlier['id'], later['id'])
        self.assertEqual(comparison['later_comparison']['matched'], 24)
        self.assertEqual(comparison['original_differences'][0]['status'], 'sas_result_changed')
        attempt = self.workspace.add_comparison(later['id'], expected())
        selected = self.workspace.compare_runs(earlier['id'], later['id'], later_attempt=attempt['id'])
        self.assertEqual(selected['original_differences'][0]['status'], 'still_differs')
        self.assertEqual(self.workspace.compare_runs(earlier['id'], later['id'])['later_comparison']['matched'], 24)
        unchecked = self.save(False)
        self.assertEqual(self.workspace.compare_runs(earlier['id'], unchecked['id'])['original_differences'][0]['status'], 'not_checked')
        with self.assertRaises(ValueError):
            self.workspace.compare_runs(earlier['id'], later['id'], later_attempt='comparison-' + '0' * 32)

    def test_input_value_diff_rejects_transient_bytes_restored_before_final_identity_check(self):
        from .data_files import load_data_file
        earlier, later = self.save(), self.save()
        saved_bytes = self.input.read_bytes()

        def transient_input(path, *args, **kwargs):
            path = Path(path)
            original = path.read_bytes()
            try:
                path.write_text(json.dumps(inputs(50)))
                return load_data_file(path, *args, **kwargs)
            finally:
                path.write_bytes(original)

        with patch('saschi.data_files.load_data_file', side_effect=transient_input):
            comparison = self.workspace.compare_runs(earlier['id'], later['id'])
        checked = comparison['files'][1]
        self.assertEqual(checked['status'], 'same')
        self.assertEqual(checked['values'], 'not_checked')
        self.assertIn('Decoded input bytes differ', checked['value_reason'])
        self.assertNotIn('value_comparison', checked)
        self.assertEqual(self.input.read_bytes(), saved_bytes)
        self.assertEqual(comparison['outputs']['status'], 'matched')

    def test_saved_checksums_and_run_id_validation_fail_visibly(self):
        record = self.save()
        for bad in ('../elsewhere', 'run-../../elsewhere', 'comparison-' + 'a' * 32):
            with self.assertRaises(ValueError):
                self.workspace.load_run(bad)
        path = self.workspace.root / record['id'] / 'record.json'
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.workspace.load_run(record['id'])

    def test_comparison_error_and_execution_failure_remain_not_checked(self):
        no_compare = self.save(False)
        self.assertEqual(no_compare['comparison']['status'], 'not_checked')
        self.assertIsNone(no_compare['comparison']['differed'])
        blocked_job = build_job('data d; set absent; run;')
        blocked = self.workspace.save_run(blocked_job, expected=expected())
        self.assertEqual(blocked['execution'], 'failed')
        self.assertIsNone(blocked['result'])
        self.assertEqual(blocked['comparison']['status'], 'not_checked')
        malformed_job = self.job()
        malformed = self.workspace.save_run(malformed_job, expected={'net_sales': None})
        self.assertEqual(malformed['execution'], 'completed')
        self.assertEqual(malformed['comparison']['status'], 'not_checked')

    def test_report_escapes_content_and_retains_not_checked_and_difference(self):
        record = self.save()
        self.workspace.add_comparison(record['id'], record['result']['datasets'])
        report = comparison_report(self.workspace.load_run(record['id']), ['<private> excluded'])
        self.assertIn('23 values matched; 1 values differed', report)
        self.assertIn('24 values matched; 0 values differed', report)
        self.assertIn('SAS result origin: not checked', report)
        self.assertIn('&lt;private&gt; excluded', report)
        self.assertNotIn('<private>', report)
        self.assertNotIn(str(self.folder), report)
        self.assertNotIn('private_unused', report)

    def test_export_preserves_scope_omissions_and_runtime_requirements(self):
        record = self.save()
        archive = self.workspace.export_run(record['id'], self.folder / 'review.zip')
        with zipfile.ZipFile(archive) as package:
            names = package.namelist()
            self.assertIn('results/net_sales.parquet', names)
            self.assertIn('results/net_sales.metadata.json', names)
            self.assertEqual(json.loads(package.read('results/net_sales.json')), record['result']['datasets']['net_sales'])
            self.assertIn('comparison-report.html', names)
            self.assertFalse(any(n.startswith(('inputs/', 'source/', 'sas-results/')) for n in names))
            portable = json.loads(package.read('run-record.json'))
            self.assertEqual(portable['comparison']['differed'], 1)
            self.assertEqual(portable['output_names'], ['net_sales'])
            self.assertEqual(portable['data_exports']['parquet']['status'], 'included')
            for name in ('run-record.json', 'comparison-report.html'):
                self.assertNotIn(str(self.folder).encode(), package.read(name))
                self.assertNotIn(b'private_unused', package.read(name))
            self.assertIn(b'not a standalone', package.read('comparison-report.html'))
            self.assertIn(b'not bundled', package.read('README.txt'))
        with self.assertRaises(FileExistsError):
            self.workspace.export_run(record['id'], archive)

    def test_explicit_export_without_parquet_retains_typed_results_and_discloses_omission(self):
        record = self.save()
        with patch.dict(sys.modules, {'duckdb': None}):
            archive = self.workspace.export_run(record['id'], self.folder / 'no-parquet.zip',
                                                 include_parquet=False, include_csv=True)
        with zipfile.ZipFile(archive) as package:
            self.assertFalse(any(n.endswith(('.parquet', '.metadata.json')) for n in package.namelist()))
            self.assertIn('results/net_sales.csv', package.namelist())
            self.assertEqual(json.loads(package.read('results/net_sales.json')), record['result']['datasets']['net_sales'])
            portable = json.loads(package.read('run-record.json'))
            self.assertEqual(portable['data_exports']['parquet']['status'], 'not_requested')
            self.assertEqual(portable['data_exports']['parquet']['files'], [])
            self.assertEqual(portable['comparison']['differed'], 1)
            self.assertIn(b'Parquet output was not selected', package.read('comparison-report.html'))
            self.assertIn(b'Parquet output: not requested', package.read('README.txt'))
        failed = self.folder / 'required-parquet.zip'
        with patch.dict(sys.modules, {'duckdb': None}):
            with self.assertRaisesRegex(ValueError, 'DuckDB'):
                self.workspace.export_run(record['id'], failed)
        self.assertFalse(failed.exists())

    def test_selected_original_copies_require_recorded_identity(self):
        record = self.save()
        self.input.write_text('{}')
        destination = self.folder / 'bad.zip'
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.workspace.export_run(record['id'], destination, include_inputs=True)
        self.assertFalse(destination.exists())
        self.input.write_text(json.dumps(inputs()))
        archive = self.workspace.export_run(record['id'], self.folder / 'complete.zip',
                                             include_inputs=True, include_source=True, include_sas_results=True)
        with zipfile.ZipFile(archive) as package:
            self.assertEqual(package.read('source/program.sas').decode(), SOURCE)
            self.assertEqual(package.read('inputs/1-inputs.json'), self.input.read_bytes())
            self.assertEqual(package.read('sas-results/1-sas-results.json'), self.sas.read_bytes())

    def test_csv_reports_logs_and_import_limits_travel_with_export(self):
        job = self.job()
        job.result['reports'] = {'report_01.txt': 'Observed formatted report\n'}
        job.result['exports'] = {'export.csv': 'x\n1\n'}
        job.result['log'] = ['Observed execution log']
        job.receipt['desktop_warnings'] = ['Display width and decimals were not imported.']
        job.receipt['desktop_imports'] = [{'file': 'sample.sas7bdat', 'metadata': {'format_name_only': True}}]
        record = self.workspace.save_run(job, files=self.identities(), expected=expected())
        new_identity = file_identity(self.sas, role='sas_result')
        new_identity['import_warnings'] = ['Custom format catalog not loaded.']
        self.workspace.add_comparison(record['id'], expected(), files=[new_identity])
        archive = self.workspace.export_run(record['id'], self.folder / 'details.zip', include_csv=True)
        with zipfile.ZipFile(archive) as package:
            self.assertIn(b'1000.0,40.0,960.0', package.read('results/net_sales.csv'))
            self.assertEqual(package.read('reports/report_01.txt'), b'Observed formatted report\n')
            self.assertEqual(package.read('exports/export.csv'), b'x\n1\n')
            self.assertIn(b'Observed execution log', package.read('execution.log'))
            report = package.read('comparison-report.html')
            self.assertIn(b'Display width and decimals were not imported', report)
            self.assertIn(b'Custom format catalog not loaded', report)
            self.assertIn(b'covers imported fields only', report)
            portable = json.loads(package.read('run-record.json'))
            self.assertEqual(portable['import_facts'], job.receipt['desktop_imports'])

    def test_no_input_catalog_is_saved_for_report_only_steps(self):
        job = self.job(False)
        with patch.object(job.plan, 'to_dict', return_value={'steps': [{'kind': 'proc_print', 'name': 'orders'}]}):
            record = self.workspace.save_run(job)
        self.assertEqual(record['output_names'], [])
        self.assertEqual(record['result']['datasets'], {})


class ComparisonEvidenceTests(unittest.TestCase):
    def test_no_output_datasets_do_not_claim_a_matching_comparison(self):
        summary = compare_catalogs({}, {}, include_extra=True)
        self.assertEqual(summary['status'], 'not_checked')
        self.assertIsNone(summary['matched'])

    def test_scope_metadata_order_and_unpaired_rows_have_distinct_evidence(self):
        baseline = expected()
        actual = deepcopy(baseline)
        actual['not_compared'] = deepcopy(actual['net_sales'])
        summary = compare_catalogs(actual, baseline)
        self.assertEqual(summary['status'], 'matched')
        self.assertEqual(summary['uncompared_actual_datasets'], ['not_compared'])
        actual['net_sales']['label'] = 'changed label'
        actual['net_sales']['rows'].append(deepcopy(actual['net_sales']['rows'][0]))
        summary = compare_catalogs(actual, baseline)
        self.assertEqual(summary['matched'], 24)
        self.assertEqual(summary['differed'], 0)
        self.assertEqual(summary['unpaired'], 4)
        self.assertEqual(summary['status'], 'differed')
        self.assertEqual(summary['datasets']['net_sales']['checks']['metadata'], 'differed')
        self.assertEqual(summary['datasets']['net_sales']['checks']['row_count'], 'differed')
        reordered = deepcopy(baseline)
        reordered['net_sales']['schema'] = dict(reversed(list(reordered['net_sales']['schema'].items())))
        summary = compare_catalogs(reordered, baseline)
        self.assertEqual(summary['matched'], 24)
        self.assertEqual(summary['status'], 'differed')
        self.assertEqual(summary['datasets']['net_sales']['checks']['variable_order'], 'differed')

    def test_absent_datasets_and_missing_values_are_not_matches(self):
        summary = compare_catalogs({}, expected())
        self.assertEqual(summary['unpaired'], 24)
        self.assertEqual(summary['compared'], 0)
        self.assertEqual(summary['status'], 'differed')
        table = {'schema': {'x': 'number'}, 'rows': [{'x': None}, {'x': {'missing': 'A'}}, {'x': 1}]}
        changed = deepcopy(table)
        changed['rows'][1]['x'] = {'missing': 'B'}
        changed['rows'][2]['x'] = True
        summary = compare_catalogs({'x': changed}, {'x': table})
        self.assertEqual(summary['matched'], 1)
        self.assertEqual(summary['differed'], 2)


if __name__ == '__main__':
    unittest.main()
