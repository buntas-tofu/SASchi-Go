"""Desktop file selection and real CLI publication boundary checks."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .desktop import Desktop, preview, run_files


class DesktopJobs(unittest.TestCase):
    def test_selected_unicode_paths_and_inputs_run_through_cli(self):
        with tempfile.TemporaryDirectory(prefix='desktop space ') as area:
            root = Path(area)
            source = root / 'chosen café.sas'
            source.write_text('data out; set raw; x=x+1; run;')
            inputs = root / 'supporting inputs.json'
            inputs.write_text(json.dumps({'raw': {'schema': {'x': 'number'}, 'rows': [{'x': 2}]}}))
            selection = {'source': str(source), 'inputs': str(inputs)}
            before = source.read_bytes(), inputs.read_bytes()
            first = run_files(selection, root)
            second = run_files(selection, root)
            self.assertEqual(first['code'], 0)
            self.assertTrue(first['receipt']['accepted'])
            self.assertNotEqual(first['output'], second['output'])
            result = json.loads((Path(first['output']) / 'result.json').read_text())
            self.assertEqual(result['datasets']['out']['rows'], [{'x': 3.0}])
            self.assertEqual(before, (source.read_bytes(), inputs.read_bytes()))

    def test_failed_comparison_saves_observed_and_receipt(self):
        with tempfile.TemporaryDirectory() as area:
            root = Path(area)
            source, expected = root / 'job.sas', root / 'expected.json'
            source.write_text('data out; x=1; run;')
            expected.write_text('{}')
            result = run_files({'source': str(source), 'expect': str(expected)}, root)
            self.assertEqual(result['code'], 1)
            self.assertEqual(result['receipt']['comparison'], 'failed')
            output = Path(result['output'])
            self.assertTrue((output / 'observed.json').exists())
            self.assertFalse((output / 'result.json').exists())
            self.assertFalse((output / 'reports').exists())

    def test_unsupported_source_saves_tickets_without_result(self):
        with tempfile.TemporaryDirectory() as area:
            source = Path(area) / 'unsupported.sas'
            source.write_text('proc imaginary; run;')
            result = run_files({'source': str(source)}, area)
            self.assertEqual(result['code'], 2)
            self.assertTrue(result['receipt']['tickets'])
            self.assertFalse((Path(result['output']) / 'result.json').exists())

    def test_report_files_match_expected_receipt(self):
        with tempfile.TemporaryDirectory() as area:
            root = Path(area)
            examples = Path(__file__).resolve().parents[1] / 'examples'
            source = examples / 'numeric_pictures.sas'
            expected = json.loads((examples / 'numeric_pictures_expected.json').read_text())
            reports = root / 'report expectations.json'
            reports.write_text(json.dumps(expected['reports']))
            result = run_files({'source': str(source), 'expect_reports': str(reports)}, root)
            self.assertEqual(result['receipt']['report_comparison'], 'passed')
            for name, text in expected['reports'].items():
                self.assertEqual((Path(result['output']) / 'reports' / name).read_text(), text)

    def test_invalid_selection_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as area:
            with self.assertRaisesRegex(ValueError, 'SAS program'):
                run_files({'source': str(Path(area) / 'absent.sas')}, area)
            self.assertEqual(list(Path(area).iterdir()), [])

    def test_missing_supporting_input_is_not_silently_omitted(self):
        with tempfile.TemporaryDirectory() as area:
            source = Path(area) / 'job.sas'
            source.write_text('data out; x=1; run;')
            with self.assertRaisesRegex(ValueError, 'supporting file'):
                run_files({'source': str(source), 'inputs': str(Path(area) / 'absent.json')}, area)
            self.assertEqual(len(list(Path(area).iterdir())), 1)

    def test_cancel_dialog_preserves_previous_selection(self):
        from types import SimpleNamespace
        class Value:
            def __init__(self): self.value = 'previous'
            def set(self, value): self.value = value
        value = Value()
        view = SimpleNamespace(root=None, paths={'source': value}, folder=value)
        with patch('tkinter.filedialog.askopenfilename', return_value=''):
            Desktop.choose(view, 'source', '*.sas')
        with patch('tkinter.filedialog.askdirectory', return_value=''):
            Desktop.choose_folder(view)
        self.assertEqual(value.value, 'previous')

    def test_large_result_preview_is_bounded(self):
        with tempfile.TemporaryDirectory() as area:
            path = Path(area) / 'result.json'
            path.write_text('x' * 100)
            self.assertIn('Preview truncated', preview(path, 20))
            self.assertEqual(len(path.read_text()), 100)
