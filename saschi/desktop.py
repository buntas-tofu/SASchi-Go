"""Desktop entry point and compatibility helpers for the CLI publication path."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid


FIELDS = [('source', 'SAS program', '*.sas'),
          ('inputs', 'Input datasets (JSON, optional)', '*.json'),
          ('expect', 'Expected datasets (JSON, optional)', '*.json'),
          ('expect_reports', 'Expected reports (JSON, optional)', '*.json'),
          ('expect_exports', 'Expected exports (JSON, optional)', '*.json'),
          ('expect_log', 'Expected log (JSON, optional)', '*.json')]


def run_files(selection, folder, *, python=None):
    """Execute selected files in an isolated worker process, preserving CLI receipts."""
    source = Path(selection.get('source', '')).expanduser().resolve()
    if not source.is_file():
        raise ValueError('Choose an existing SAS program.')
    parent = Path(folder).expanduser().resolve()
    if not parent.is_dir():
        raise ValueError('Choose an existing output folder.')
    paths = {'source': source}
    for key, _, _ in FIELDS[1:]:
        if selection.get(key):
            path = Path(selection[key]).expanduser().resolve()
            if not path.is_file():
                raise ValueError('Selected supporting file does not exist: ' + key)
            paths[key] = path
    name = 'saschi-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex
    output = parent / name
    command = [python or sys.executable, '-m', 'saschi', 'run', str(source), '--output', str(output)]
    for key, path in paths.items():
        if key != 'source':
            command += ['--' + key.replace('_', '-'), str(path)]
    # Use the same installed package when launched through the Debian wrapper.
    env = os.environ.copy()
    package_root = str(Path(__file__).resolve().parent.parent)
    env['PYTHONPATH'] = package_root
    run = subprocess.run(command, env=env, capture_output=True, text=True)
    receipt_path = output / 'receipt.json'
    if not receipt_path.is_file():
        try:
            detail = json.loads(run.stdout).get('error', 'Job could not be saved.')
        except (ValueError, AttributeError):
            detail = 'Job worker failed before saving a receipt (exit ' + str(run.returncode) + ').'
        raise ValueError(detail)
    receipt = json.loads(receipt_path.read_text())
    return {'output': str(output), 'receipt': receipt, 'code': run.returncode}


def preview(path, limit=200000):
    with Path(path).open(encoding='utf-8') as stream:
        text = stream.read(limit + 1)
    return text[:limit] + ('\n[Preview truncated. The complete file is saved on disk.]' if len(text) > limit else '')


def __getattr__(name):
    # Keep CLI helpers importable on systems without Tk installed.
    if name == 'Desktop':
        from .desktop_ui import Desktop
        return Desktop
    raise AttributeError(name)


def main():
    try:
        import tkinter as tk
        from .desktop_ui import Desktop
        root = tk.Tk()
    except ImportError:
        print('Install Ubuntu desktop support: sudo apt install python3-tk', file=sys.stderr)
        return 1
    except Exception as exc:
        print('Desktop display unavailable: ' + str(exc), file=sys.stderr)
        return 1
    Desktop(root)
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
