"""Local desktop frontend over the unchanged CLI job and publication path."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
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


class Desktop:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk
        from tkinter.scrolledtext import ScrolledText
        self.root, self.busy, self.last_output = root, False, None
        self.events = queue.Queue()
        self.paths = {key: tk.StringVar() for key, _, _ in FIELDS}
        self.folder, self.status = tk.StringVar(), tk.StringVar(value='Choose a SAS program and an output folder.')
        self.controls = []
        root.title('SASchi-Go Desktop')
        root.geometry('1100x780')
        root.minsize(800, 620)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        frame = ttk.Frame(root, padding=20)
        frame.grid(sticky='nsew')
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text='SASchi-Go', font=('Sans', 24, 'bold')).grid(row=0, column=0, columnspan=3, sticky='w')
        ttk.Label(frame, text='Your files. Local execution. A receipt for every completed job.').grid(row=1, column=0, columnspan=3, sticky='w', pady=(0, 18))
        for row, (key, label, pattern) in enumerate(FIELDS, start=2):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', padx=(0, 12))
            entry = ttk.Entry(frame, textvariable=self.paths[key])
            entry.grid(row=row, column=1, sticky='ew', pady=4)
            button = ttk.Button(frame, text='Choose file', command=lambda k=key, p=pattern: self.choose(k, p))
            button.grid(row=row, column=2, padx=(10, 0))
            self.controls += [entry, button]
        row = 2 + len(FIELDS)
        ttk.Label(frame, text='Output folder').grid(row=row, column=0, sticky='w')
        entry = ttk.Entry(frame, textvariable=self.folder)
        entry.grid(row=row, column=1, sticky='ew', pady=4)
        button = ttk.Button(frame, text='Choose folder', command=self.choose_folder)
        button.grid(row=row, column=2, padx=(10, 0))
        self.controls += [entry, button]
        ttk.Label(frame, text='Inputs use the existing typed JSON dataset catalog. Each run creates a new subfolder.').grid(row=row+1, column=0, columnspan=3, sticky='w', pady=(8, 4))
        bar = ttk.Frame(frame)
        bar.grid(row=row+2, column=0, columnspan=3, sticky='ew', pady=8)
        self.run_button = ttk.Button(bar, text='Run selected program', command=self.start)
        self.run_button.pack(side='left')
        self.controls.append(self.run_button)
        self.open_button = ttk.Button(bar, text='Open saved job', command=self.open_output, state='disabled')
        self.open_button.pack(side='left', padx=10)
        self.progress = ttk.Progressbar(bar, mode='indeterminate')
        self.progress.pack(side='right', fill='x', expand=True)
        ttk.Label(frame, textvariable=self.status, wraplength=1000).grid(row=row+3, column=0, columnspan=3, sticky='w', pady=6)
        self.tabs = ttk.Notebook(frame)
        self.tabs.grid(row=row+4, column=0, columnspan=3, sticky='nsew')
        frame.rowconfigure(row+4, weight=1)
        self.views = {}
        for name in ['Summary', 'Results', 'Reports', 'Receipt', 'Plan']:
            box = ScrolledText(self.tabs, wrap='none', font=('Monospace', 10), state='disabled')
            self.tabs.add(box, text=name)
            self.views[name] = box
        ttk.Label(frame, text='ACCEPTED means the requested job checks passed. No per-job R or live SAS comparison is performed.').grid(row=row+5, column=0, columnspan=3, sticky='w', pady=(10, 0))
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    def choose(self, key, pattern):
        from tkinter import filedialog
        value = filedialog.askopenfilename(parent=self.root, title='Select ' + key.replace('_', ' '), filetypes=[('Selected file type', pattern), ('All files', '*')])
        if value:
            self.paths[key].set(value)

    def choose_folder(self):
        from tkinter import filedialog
        value = filedialog.askdirectory(parent=self.root, title='Select output folder', mustexist=True)
        if value:
            self.folder.set(value)

    def set_text(self, name, text):
        box = self.views[name]
        box.configure(state='normal')
        box.delete('1.0', 'end')
        box.insert('1.0', text)
        box.configure(state='disabled')

    def start(self):
        from tkinter import messagebox
        if self.busy:
            return
        selection = {key: value.get().strip() for key, value in self.paths.items()}
        folder = self.folder.get().strip()
        if not selection['source'] or not folder:
            messagebox.showerror('Choose files', 'Select a SAS program and an output folder.', parent=self.root)
            return
        self.busy, self.last_output = True, None
        for control in self.controls:
            control.configure(state='disabled')
        self.open_button.configure(state='disabled')
        for name in self.views:
            self.set_text(name, '')
        self.status.set('Running selected program. Results will appear when the job is saved.')
        self.progress.start()

        def worker():
            try:
                self.events.put(('done', run_files(selection, folder)))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            kind, value = self.events.get_nowait()
        except queue.Empty:
            self.root.after(100, self.poll)
            return
        self.busy = False
        self.progress.stop()
        for control in self.controls:
            control.configure(state='normal')
        if kind == 'error':
            self.status.set('Job could not be saved: ' + value)
            self.set_text('Summary', value)
        else:
            try:
                self.show(value)
            except (OSError, ValueError) as exc:
                self.status.set('Job saved, but preview could not be loaded: ' + str(exc))
        self.root.after(100, self.poll)

    def show(self, value):
        output, receipt = Path(value['output']), value['receipt']
        self.last_output = output
        self.open_button.configure(state='normal')
        verdict = 'ACCEPTED' if receipt['accepted'] else 'BLOCKED' if value['code'] == 2 else 'REJECTED'
        self.status.set(verdict + ' | Saved to ' + str(output))
        comparisons = '\n'.join(label + ': ' + receipt.get(key, 'not requested') for label, key in [('Dataset comparison', 'comparison'), ('Report comparison', 'report_comparison'), ('Export comparison', 'export_comparison'), ('Log comparison', 'log_comparison')])
        tickets = '\n'.join(json.dumps(ticket, ensure_ascii=False) for ticket in receipt.get('tickets', []))
        self.set_text('Summary', verdict + '\n\n' + comparisons + '\n\n' + receipt.get('error', '') + '\n' + tickets + '\n\nSaved job: ' + str(output))
        self.set_text('Receipt', preview(output / 'receipt.json'))
        self.set_text('Plan', preview(output / 'plan.json'))
        result = output / ('result.json' if receipt['accepted'] else 'observed.json')
        if result.exists():
            self.set_text('Results', preview(result))
        reports = sorted((output / 'reports').glob('*.txt')) if (output / 'reports').is_dir() else []
        self.set_text('Reports', '\n\n'.join(path.name + '\n' + preview(path) for path in reports) or 'No accepted report files were produced. See Results for observed output from rejected jobs.')

    def open_output(self):
        if self.last_output:
            subprocess.Popen(['xdg-open', str(self.last_output)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def close(self):
        if self.busy:
            from tkinter import messagebox
            messagebox.showinfo('Job in progress', 'Wait for the current job to finish before closing.', parent=self.root)
        else:
            self.root.destroy()


def main():
    try:
        import tkinter as tk
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
