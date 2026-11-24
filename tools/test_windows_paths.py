"""Regression tests for Windows checkout validation in the publication scan."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.windows_paths import windows_path_issues

ROOT = Path(__file__).resolve().parent.parent


class WindowsPathsTests(unittest.TestCase):
    def test_reserved_names_include_extensions_and_nested_components(self):
        paths = ('nul', 'NuL.txt', 'data/NUL .data', 'aux/tables.csv', 'Con', 'PRN.txt',
                 'com9.data', 'COM\u00b9.dat', 'lpt1', 'LPT\u00b3', 'CONIN$', 'conout$.txt')
        invalid = {path for path, message in windows_path_issues(paths)
                   if message == 'reserved Windows device name'}
        self.assertEqual(invalid, set(paths) - {'aux/tables.csv'} | {'aux'})

    def test_invalid_characters_and_trailing_punctuation(self):
        paths = [f'data/bad{char}name' for char in '<>:"\\|?*\t\n\x00\x1f']
        self.assertEqual(len(windows_path_issues(paths)), len(paths))
        self.assertEqual(windows_path_issues(['data./item.csv', 'data/report ']), [
            ('data.', 'trailing period or space'),
            ('data/report ', 'trailing period or space'),
        ])

    def test_case_collisions_include_files_directories_and_mixed_types(self):
        for spelling in (
            ('results/Report.csv', 'results/report.csv'),
            ('Reports/one.csv', 'reports/two.csv'),
            ('schema', 'Schema/data.csv'),
        ):
            with self.subTest(spelling=spelling):
                _, message = windows_path_issues(spelling)[0]
                self.assertIn('case-insensitive collision', message)

    def test_ordinary_names_and_repeated_directory_prefixes_pass(self):
        self.assertEqual(windows_path_issues(
            ['docs/auxiliary.md', 'docs/com10.txt', 'docs/final.nul', 'docs/Read Me.md', '.gitignore']), [])

    @unittest.skipIf(os.name == 'nt', 'Reserved-name fixture requires a filesystem that can create it')
    def test_ignore_staged_and_committed_paths_use_the_same_gate(self):
        workflow = (ROOT / '.github/workflows/governance.yml').read_text(encoding='utf-8')
        scan_line = next(line.strip() for line in workflow.splitlines()
                         if line.strip().startswith('python3 scripts/check_sanitization.py '))
        profile = scan_line.split()[-1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)

            def scan(*args):
                return subprocess.run([sys.executable, str(ROOT / 'scripts/check_sanitization.py'),
                                       profile, str(root), *args],
                                      capture_output=True, text=True, check=False)

            git('init', '-q')
            (root / '.gitignore').write_bytes((ROOT / '.gitignore').read_bytes())
            for name in ('nul', 'NuL', 'NUL'):
                git('check-ignore', '--no-index', '--', name)
            (root / 'NuL').write_text('fixture', encoding='utf-8')
            self.assertEqual(scan('--paths-only').returncode, 0)
            git('add', '-f', '--', 'NuL')
            (root / 'NuL').unlink()
            result = scan('--paths-only')
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn('reserved Windows device name', result.stdout)
            full = scan()
            self.assertEqual(full.returncode, 1, full.stderr)
            self.assertIn('reserved Windows device name', full.stdout)
            tree = git('write-tree').stdout.decode().strip()
            git('rm', '--cached', '--', 'NuL')
            self.assertEqual(scan('--paths-only').returncode, 0)
            self.assertEqual(scan('--paths-only', '--tree', tree).returncode, 1)
