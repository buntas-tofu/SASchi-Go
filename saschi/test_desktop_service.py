"""Desktop analysis, snapshot execution, and retry boundaries with synthetic files."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .desktop_service import (review_setup, execute_prepared, open_saved_run,
                              select_saved_setup, compare_with_sas, compare_saved_runs)


class DesktopWorkflow(unittest.TestCase):
    def setUp(self):
        self.area = tempfile.TemporaryDirectory(prefix='analyst desktop ')
        self.addCleanup(self.area.cleanup)
        self.root = Path(self.area.name)
        self.source = self.root / 'net_sales.sas'
        self.source.write_text('data net_sales; merge orders returns; by order_id; net=gross-refunded; run;')
        self.orders, self.returns = self.root / 'orders.json', self.root / 'returns.json'
        self.orders.write_text(json.dumps({'orders': {'schema': {'order_id': 'number', 'gross': 'number'},
                                                     'rows': [{'order_id': 3, 'gross': 1000}]}}))
        self.set_return(40)
        self.expected = self.root / 'net_sales.json'
        self.expected.write_text(json.dumps({'net_sales': {'schema': {'order_id': 'number', 'gross': 'number', 'refunded': 'number', 'net': 'number'},
                                                          'rows': [{'order_id': 3, 'gross': 1000, 'refunded': 40, 'net': 950}]}}))
        self.workspace = self.root / 'saved'

    def set_return(self, amount):
        self.returns.write_text(json.dumps({'returns': {'schema': {'order_id': 'number', 'refunded': 'number'},
                                                       'rows': [{'order_id': 3, 'refunded': amount}]}}))

    def selection(self, compare=True):
        return {'source': str(self.source), 'inputs': [str(self.orders), str(self.returns)],
                'sas_results': [str(self.expected)] if compare else [], 'target': 'python'}

    def test_review_reads_inputs_without_execution_or_saved_side_effects(self):
        with patch('saschi.desktop_service.build_job', side_effect=AssertionError('analysis executed')):
            prepared = review_setup(self.selection())
        self.assertTrue(prepared['ready'])
        self.assertEqual(prepared['required_inputs'], ['orders', 'returns'])
        self.assertFalse(self.workspace.exists())
        self.assertIn('saschi.runtime', prepared['translation']['code'])

    def test_missing_dataset_and_unsupported_targets_cannot_run(self):
        selection = self.selection()
        selection['inputs'] = [str(self.orders)]
        prepared = review_setup(selection)
        self.assertEqual(prepared['missing_inputs'], ['returns'])
        with self.assertRaises(ValueError):
            execute_prepared(prepared, self.workspace)
        for target in ('r', 'sql', 'cpp'):
            selection = self.selection()
            selection['target'] = target
            prepared = review_setup(selection)
            self.assertFalse(prepared['ready'])
            with self.assertRaises(ValueError):
                execute_prepared(prepared, self.workspace)

    def test_file_change_after_review_requires_another_review(self):
        prepared = review_setup(self.selection())
        self.set_return(50)
        with self.assertRaisesRegex(ValueError, 'reviewed file changed'):
            execute_prepared(prepared, self.workspace)
        self.assertFalse(self.workspace.exists())

    def test_initial_lookup_requires_its_external_dataset_before_execution(self):
        self.source.write_text('data out; if _n_=1 then set config; set orders; net=gross; run;')
        selection = self.selection(compare=False)
        selection['inputs'] = [str(self.orders)]
        prepared = review_setup(selection)
        self.assertFalse(prepared['ready'])
        self.assertEqual(prepared['required_inputs'], ['config', 'orders'])
        self.assertEqual(prepared['missing_inputs'], ['config'])
        with self.assertRaises(ValueError):
            execute_prepared(prepared, self.workspace)
        self.assertFalse(self.workspace.exists())

    def test_interim_file_versions_cannot_be_saved_under_restored_file_identity(self):
        from .data_files import load_data_file
        from .desktop_service import _read_program_snapshot
        original = self.orders.read_bytes()
        def changed_input(path, *args, **kwargs):
            if Path(path) != self.orders:
                return load_data_file(path, *args, **kwargs)
            self.orders.write_bytes(original.replace(b'1000', b'2000'))
            try:
                return load_data_file(path, *args, **kwargs)
            finally:
                self.orders.write_bytes(original)
        with patch('saschi.data_files.load_data_file', side_effect=changed_input):
            with self.assertRaisesRegex(ValueError, 'changed while'):
                review_setup(self.selection())
        original_source = self.source.read_bytes()
        def changed_source(path, **kwargs):
            self.source.write_bytes(original_source.replace(b'gross-refunded', b'gross+refunded'))
            try:
                return _read_program_snapshot(path, **kwargs)
            finally:
                self.source.write_bytes(original_source)
        with patch('saschi.desktop_service._read_program_snapshot', side_effect=changed_source):
            with self.assertRaisesRegex(ValueError, 'changed while'):
                review_setup(self.selection())
        self.assertFalse(self.workspace.exists())

    def test_original_difference_survives_new_run_and_file_move(self):
        first = execute_prepared(review_setup(self.selection()), self.workspace)
        self.assertEqual(first['execution'], 'completed')
        self.assertEqual(first['comparison']['status'], 'differed')
        self.assertEqual(first['comparison']['differed'], 1)
        self.set_return(50)
        with self.assertRaisesRegex(ValueError, 'Contents changed'):
            select_saved_setup(first)
        selected = select_saved_setup(first, allow_changed=True)
        self.source.unlink()
        second = execute_prepared(review_setup(selected), self.workspace)
        self.assertEqual(second['result']['datasets']['net_sales']['rows'][0]['net'], 950)
        self.assertEqual(second['comparison']['differed'], 1)
        changes = compare_saved_runs(self.workspace, first['id'], second['id'])
        self.assertEqual(changes['outputs']['differed'], 2)
        saved = open_saved_run(self.workspace, first['id'])
        self.assertEqual(saved['result']['datasets']['net_sales']['rows'][0]['net'], 960)
        self.assertEqual(saved['comparison'], first['comparison'])

    def test_comparison_only_retry_does_not_execute(self):
        record = execute_prepared(review_setup(self.selection(compare=False)), self.workspace)
        self.assertEqual(record['comparison']['status'], 'not_checked')
        with patch('saschi.desktop_service.build_job', side_effect=AssertionError('comparison executed program')):
            attempt = compare_with_sas(self.workspace, record['id'], [str(self.expected)])
        self.assertEqual(attempt['summary']['status'], 'differed')
        reopened = open_saved_run(self.workspace, record['id'])
        self.assertEqual(reopened['comparison']['status'], 'not_checked')
        self.assertEqual(len(reopened['comparison_attempts']), 1)

    def test_failed_execution_still_saves_original_evidence(self):
        self.orders.write_text(json.dumps({'orders': {'schema': {'order_id': 'number', 'gross': 'number'},
                                                     'rows': [{'order_id': 3, 'gross': 1000}, {'order_id': 1, 'gross': 20}]}}))
        record = execute_prepared(review_setup(self.selection()), self.workspace)
        self.assertEqual(record['execution'], 'failed')
        self.assertIsNone(record['result'])
        self.assertEqual(record['comparison']['status'], 'not_checked')
        self.assertEqual(open_saved_run(self.workspace, record['id'])['source'], self.source.read_text())
