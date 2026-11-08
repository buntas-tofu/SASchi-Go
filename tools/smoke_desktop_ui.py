"""Exercise the native workflow on synthetic data, with an available Tk display.

Run with xvfb-run -a python tools/smoke_desktop_ui.py in headless environments.
This is UI integration evidence, not native SAS validation.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import traceback
from unittest.mock import patch
import zipfile

import tkinter as tk
from tkinter import ttk

from saschi.desktop_ui import Connections, Desktop


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def button(widget, label):
    return next(child for child in descendants(widget) if isinstance(child, ttk.Button) and child.cget('text') == label)


def wait(root, app):
    deadline = time.monotonic() + 30
    while True:
        root.update()
        if not app.busy:
            root.update()
            return
        if time.monotonic() > deadline:
            raise AssertionError('Native operation did not finish: ' + app.status.get())
        time.sleep(.01)


def settle(root):
    for _ in range(8):
        root.update()
        time.sleep(.01)


def dialog(root, title):
    return next(child for child in root.winfo_children() if isinstance(child, tk.Toplevel) and child.title() == title)


def main():
    errors = []
    root = tk.Tk()
    root.report_callback_exception = lambda *args: errors.append(''.join(traceback.format_exception(*args)))
    app = Desktop(root)
    try:
        with tempfile.TemporaryDirectory(prefix='saschi-native-ui-') as temporary, patch('tkinter.messagebox.showerror', side_effect=lambda *args, **kwargs: errors.append(str(args))):
            area = Path(temporary)
            program = area / 'orders review.sas'
            inputs = area / 'orders.json'
            expected = area / 'sas results.json'
            workspace = area / 'workspace'
            program.write_text('data result; set orders; total = amount - refunded; run;\n', encoding='utf-8')
            schema = {'amount': 'number', 'refunded': 'number'}
            inputs.write_text(json.dumps({'orders': {'schema': schema, 'rows': [{'amount': 1000, 'refunded': 50}]}}), encoding='utf-8')
            expected.write_text(json.dumps({'result': {'schema': {**schema, 'total': 'number'}, 'rows': [{'amount': 1000, 'refunded': 50, 'total': 960}]}}), encoding='utf-8')
            app.folder.set(str(workspace))
            with patch('tkinter.filedialog.askopenfilename', return_value=str(program)):
                app.choose('source', '*.sas')
            wait(root, app)
            assert 'data result' in app.source_preview.get('1.0', 'end')
            with patch('tkinter.filedialog.askopenfilenames', return_value=(str(inputs),)):
                app.inputs.add()
            app.review()
            wait(root, app)
            assert app.prepared['ready'] and app.prepared['expected'] is None
            assert not workspace.exists(), 'Optional comparison must not be required for review'
            app.compare_enabled.set(True)
            app._toggle_comparison()
            with patch('tkinter.filedialog.askopenfilenames', return_value=(str(expected),)):
                app.results_connections.add()
            app.review()
            wait(root, app)
            assert app.prepared['ready'] and not workspace.exists(), 'Review must not execute or save a run'
            assert app.record is None and app.run_button.cget('state') != 'disabled'
            assert app.prepared['required_inputs'] == ['orders']
            app.start()
            wait(root, app)
            assert app.record, app.status.get()
            run_id = app.record['id']
            assert app.record['execution'] == 'completed'
            assert app.record['comparison']['status'] == 'differed'
            assert app.record['comparison']['differed'] == 1
            assert app.record['result']['datasets']['result']['rows'][0]['total'] == 950
            assert 'Execution: completed' in app.run_heading.cget('text')
            assert '1 different' in app.comparison_view.heading.cget('text')
            print('PASS review, input binding, execution and distinct comparison outcome', flush=True)

            # Reopening uses saved evidence even when the original program moved.
            program.rename(area / 'moved program.sas')
            app.refresh_runs()
            wait(root, app)
            app.saved_tree.selection_set(run_id)
            app.open_selected()
            wait(root, app)
            assert app.record['id'] == run_id and 'data result' in app.run_code.views[0].get('1.0', 'end')
            before = len(list(workspace.glob('run-*')))
            app.new_from_saved()
            wait(root, app)
            assert app._snapshot_source and len(list(workspace.glob('run-*'))) == before
            app.review()
            wait(root, app)
            assert app.prepared['ready'], app.status.get()
            print('PASS reopen and prepare new setup without original source or execution', flush=True)

            # A moved input can be reconnected and its binding survives reopening.
            moved_inputs = area / 'moved orders.json'
            inputs.rename(moved_inputs)
            app.check_files()
            wait(root, app)
            files_dialog = dialog(root, 'Original files for saved run')
            file_tree = next(child for child in descendants(files_dialog) if isinstance(child, ttk.Treeview))
            input_id = next(item['id'] for item in app.record['files'] if item['role'] == 'input')
            file_tree.selection_set(input_id)
            with patch('tkinter.filedialog.askopenfilename', return_value=str(moved_inputs)):
                button(files_dialog, 'Locate selected file').invoke()
            wait(root, app)
            assert file_tree.item(input_id, 'values')[2] == 'moved same'
            button(files_dialog, 'Done').invoke()
            app.open_selected()
            wait(root, app)
            assert app._bindings[input_id] == str(moved_inputs)

            # Failed comparison keeps its editable connections; retry appends evidence.
            app.add_comparison()
            compare_dialog = dialog(root, 'Compare with SAS results')
            connections = next(child for child in descendants(compare_dialog) if isinstance(child, Connections))
            connections.show([{'path': str(area / 'missing results.json')}])
            button(compare_dialog, 'Compare saved output').invoke()
            wait(root, app)
            assert compare_dialog.winfo_exists() and len(connections.entries) == 1
            assert 'Comparison did not complete' in app.status.get()
            connections.show([{'path': str(expected)}])
            button(compare_dialog, 'Compare saved output').invoke()
            wait(root, app)
            assert not compare_dialog.winfo_exists()
            assert app.record['id'] == run_id and len(app.record['comparison_attempts']) == 1
            assert app.record['comparison']['differed'] == 1
            assert app._bindings[input_id] == str(moved_inputs)
            assert len(list(workspace.glob('run-*'))) == before
            print('PASS failed comparison recovery and append-only retry', flush=True)

            # Export errors retain their options; the retry creates a real ZIP.
            app.export()
            export_dialog = dialog(root, 'Export saved run')
            destination = area / 'review package.zip'
            with patch('tkinter.filedialog.asksaveasfilename', return_value=str(destination)), patch.object(app.service, 'export_saved_run', side_effect=ValueError('Synthetic temporary export failure')):
                button(export_dialog, 'Choose export location').invoke()
                wait(root, app)
            assert export_dialog.winfo_exists() and not destination.exists()
            with patch('tkinter.filedialog.asksaveasfilename', return_value=str(destination)):
                button(export_dialog, 'Choose export location').invoke()
                wait(root, app)
            assert not export_dialog.winfo_exists() and destination.is_file(), app.status.get()
            with zipfile.ZipFile(destination) as archive:
                assert 'run-record.json' in archive.namelist()
                assert 'results/result.json' in archive.namelist()
            print('PASS export recovery and real evidence package', flush=True)

            # Changed input contents require an explicit new-run choice.
            moved_inputs.write_text(json.dumps({'orders': {'schema': schema, 'rows': [{'amount': 1000, 'refunded': 40}]}}), encoding='utf-8')
            with patch('tkinter.messagebox.askyesno', return_value=False) as choice:
                app.new_from_saved()
                wait(root, app)
                assert choice.called
            assert len(list(workspace.glob('run-*'))) == before
            with patch('tkinter.messagebox.askyesno', return_value=True):
                app.new_from_saved()
                wait(root, app)
            app.review()
            wait(root, app)
            assert app.prepared['ready'], app.status.get()
            app.start()
            wait(root, app)
            later_id = app.record['id']
            assert later_id != run_id and app.record['result']['datasets']['result']['rows'][0]['total'] == 960
            original = app.service.open_saved_run(str(workspace), run_id)
            assert original['result']['datasets']['result']['rows'][0]['total'] == 950
            app.refresh_runs()
            wait(root, app)
            app.saved_tree.selection_set(run_id, later_id)
            app.compare_runs()
            wait(root, app)
            comparison_dialog = dialog(root, 'Compare saved runs')
            text = '\n'.join(child.get('1.0', 'end') for child in descendants(comparison_dialog) if isinstance(child, tk.Text))
            assert 'now matches' in text, text
            assert any('not established' in str(child.cget('text')) for child in descendants(comparison_dialog) if isinstance(child, ttk.Label))
            comparison_dialog.destroy()
            print('PASS moved inputs, explicit changed-file choice and saved-run comparison', flush=True)

            # Narrow, large-text navigation keeps primary actions in the viewport.
            root.geometry('640x540')
            app.font_size.set('16')
            app.resize_fonts()
            for page in (app.setup_page, app.options_page, app.run_page, app.saved_page):
                app.tabs.select(page)
                settle(root)
                for child in descendants(page):
                    if isinstance(child, ttk.Button) and child.winfo_viewable() and child.winfo_manager() == 'place':
                        left = child.winfo_rootx() - root.winfo_rootx()
                        assert left >= 0 and left + child.winfo_width() <= root.winfo_width(), child.cget('text')
            app.tabs.select(app.options_page)
            option_tabs = app.review_code.master
            option_tabs.select(app.review_code)
            settle(root)
            assert str(app.review_code.panes.cget('orient')) == 'vertical'
            assert all(view.winfo_height() >= 120 for view in app.review_code.views)
            for view in app.review_code.views:
                app.options_page.reveal(view)
                settle(root)
                top = view.winfo_rooty()
                assert top < root.winfo_rooty() + root.winfo_height() and top + view.winfo_height() > root.winfo_rooty()
            app.tabs.select(app.setup_page)
            settle(root)
            review_button = button(app.setup_page, 'Review conversion options')
            assert review_button.winfo_rooty() + review_button.winfo_height() <= root.winfo_rooty() + root.winfo_height()
            assert review_button.winfo_width() > 100
            print('PASS 640x540 layout with 16-point text and stacked code', flush=True)
            assert not errors, '\n'.join(errors)
        print('NATIVE UI VERIFIED: 6 workflow groups passed', flush=True)
        return 0
    finally:
        root.destroy()


if __name__ == '__main__':
    raise SystemExit(main())
