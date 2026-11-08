"""Native desktop presentation for review, execution, and saved evidence.

Widgets never execute SAS or infer comparison success. The desktop service owns
file import, analysis, execution, and immutable workspace records.
"""
from __future__ import annotations

from copy import deepcopy
import json
import importlib.util
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, font, messagebox, simpledialog, ttk


BG = '#f4f6f3'
PAPER = '#ffffff'
INK = '#263a33'
MUTED = '#56685f'
ACCENT = '#2e6652'
LINE = '#d5ded7'
PAGE_SIZE = 200
TEXT_LIMIT = 250_000
DATA_TYPES = [('SAS datasets', '*.sas7bdat'), ('SAS transport', '*.xpt'),
              ('CSV', '*.csv'), ('Typed dataset catalog', '*.json'), ('All files', '*')]


def display_value(value, present=True):
    """Keep exact numeric representations, padding, and missing tags visible."""
    if not present:
        return '[not present]'
    if value is None:
        return '.'
    if isinstance(value, dict) and set(value) == {'missing'}:
        return '.' + str(value['missing'])
    if isinstance(value, (str, float)):
        return repr(value)
    return json.dumps(value, ensure_ascii=False)


def pretty(value):
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def set_text(widget, text):
    value = str(text)
    if len(value) > TEXT_LIMIT:
        value = value[:TEXT_LIMIT] + '\n\n[Preview limit reached. Saved evidence remains complete.]'
    widget.configure(state='normal')
    widget.delete('1.0', 'end')
    widget.insert('1.0', value)
    widget.configure(state='disabled')


def text_view(parent, code_font, *, height=10, wrap='none'):
    frame = ttk.Frame(parent)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)
    view = tk.Text(frame, font=code_font, height=height, width=1, wrap=wrap,
                   background=PAPER, foreground=INK, insertbackground=INK,
                   selectbackground='#d5e8dc', selectforeground=INK,
                   relief='flat', borderwidth=0, padx=12, pady=10, state='disabled')
    vertical = ttk.Scrollbar(frame, orient='vertical', command=view.yview)
    horizontal = ttk.Scrollbar(frame, orient='horizontal', command=view.xview)
    view.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    view.grid(row=0, column=0, sticky='nsew')
    vertical.grid(row=0, column=1, sticky='ns')
    horizontal.grid(row=1, column=0, sticky='ew')
    return frame, view


def tree_view(parent, columns, *, height=5, selectmode='browse'):
    frame = ttk.Frame(parent)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)
    tree = ttk.Treeview(frame, columns=[key for key, _ in columns], show='headings',
                        height=height, selectmode=selectmode)
    for key, label in columns:
        tree.heading(key, text=label)
        tree.column(key, width=160, minwidth=100, stretch=True)
    ybar = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
    xbar = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
    tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
    tree.grid(row=0, column=0, sticky='nsew')
    ybar.grid(row=0, column=1, sticky='ns')
    xbar.grid(row=1, column=0, sticky='ew')
    return frame, tree


class ScrollPage(ttk.Frame):
    """A setup page that remains reachable at larger fonts and short heights."""

    def __init__(self, parent):
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, background=BG, highlightthickness=0)
        bar = ttk.Scrollbar(self, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        bar.grid(row=0, column=1, sticky='ns')
        self.body = ttk.Frame(self.canvas, padding=16)
        self.window = self.canvas.create_window(0, 0, anchor='nw', window=self.body)
        self.body.columnconfigure(0, weight=1)
        self.canvas.bind('<Configure>', lambda event: self.canvas.itemconfigure(self.window, width=event.width))
        self.body.bind('<Configure>', lambda _: self.canvas.configure(scrollregion=self.canvas.bbox('all')))

    def connect_navigation(self):
        def focus(event):
            self.after_idle(lambda: self.reveal(event.widget))
        def wheel(event):
            delta = -1 if getattr(event, 'num', None) == 4 or getattr(event, 'delta', 0) > 0 else 1
            self.canvas.yview_scroll(delta * 3, 'units')
            return 'break'
        def connect(widget):
            widget.bind('<FocusIn>', focus, add='+')
            if not isinstance(widget, (tk.Text, ttk.Treeview, ttk.Combobox, ttk.Scrollbar)):
                for event in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                    widget.bind(event, wheel, add='+')
            for child in widget.winfo_children():
                connect(child)
        connect(self.body)

    def reveal(self, widget):
        if not widget.winfo_exists() or not widget.winfo_viewable():
            return
        top = widget.winfo_rooty() - self.body.winfo_rooty()
        visible_top = self.canvas.canvasy(0)
        height = self.canvas.winfo_height()
        if top < visible_top or top + widget.winfo_height() > visible_top + height:
            self.canvas.yview_moveto(max(0, top - 12) / max(1, self.body.winfo_height()))


class FlowBar(ttk.Frame):
    """Wrap actions into additional rows instead of clipping them at large text."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._pending = None
        self._layout = None
        self._watched = set()
        self.bind('<Configure>', self.schedule)

    def schedule(self, _=None):
        if self._pending is None:
            self._pending = self.after_idle(self.reflow)

    def reflow(self):
        self._pending = None
        children = self.winfo_children()
        width = max(1, self.winfo_width())
        layout = (width, tuple((str(child), child.winfo_reqwidth(), child.winfo_reqheight()) for child in children))
        if layout == self._layout:
            return
        self._layout = layout
        x, y, line_height = 0, 0, 0
        for child in children:
            if child not in self._watched:
                child.bind('<Configure>', self.schedule, add='+')
                self._watched.add(child)
            requested = child.winfo_reqwidth()
            if x and x + requested > width:
                x, y, line_height = 0, y + line_height + 6, 0
            if child.winfo_manager() == 'pack':
                child.pack_forget()
            elif child.winfo_manager() == 'grid':
                child.grid_forget()
            child.place(x=x, y=y, width=min(requested, width))
            x += requested + 8
            line_height = max(line_height, child.winfo_reqheight())
        self.configure(height=y + line_height)


class CodePair(ttk.Frame):
    """Two readable code views with a drag handle and automatic stacking."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.panes = tk.PanedWindow(self, orient='horizontal', background=LINE,
                                    sashwidth=9, sashrelief='flat', borderwidth=0,
                                    showhandle=True, handlesize=8, opaqueresize=True)
        self.panes.grid(sticky='nsew')
        self.titles, self.views = [], []
        for title in ('SAS program', 'Converted Python'):
            frame = ttk.Frame(self.panes)
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(1, weight=1)
            label = ttk.Label(frame, text=title, style='Subheading.TLabel', padding=(10, 8))
            label.grid(row=0, column=0, sticky='ew')
            box, view = text_view(frame, app.code_font)
            box.grid(row=1, column=0, sticky='nsew')
            self.panes.add(frame, minsize=220, stretch='always')
            self.titles.append(label)
            self.views.append(view)
        self.bind('<Configure>', self._resize)

    def _resize(self, event):
        orientation = 'vertical' if event.width < self.app.body_font.measure('0') * 100 else 'horizontal'
        if str(self.panes.cget('orient')) != orientation:
            self.panes.configure(orient=orientation)
            self.after_idle(self._balance)

    def _balance(self):
        if self.winfo_exists():
            self.panes.sash_place(0, self.panes.winfo_width() // 2, self.panes.winfo_height() // 2)

    def show(self, source, code, *, target='python', snapshot=False):
        self.titles[0].configure(text='Saved SAS program' if snapshot else 'SAS program')
        self.titles[1].configure(text='C++ code preview' if target == 'cpp' else 'Converted Python')
        set_text(self.views[0], source)
        set_text(self.views[1], code)


class Connections(ttk.Frame):
    """Editable file-to-member bindings. Reading files belongs to the service."""

    def __init__(self, parent, app, *, results=False):
        super().__init__(parent)
        self.app, self.results, self.entries = app, results, []
        self.columnconfigure(0, weight=1)
        title = 'Compare with SAS results (optional)' if results else 'Input datasets'
        ttk.Label(self, text=title, style='Subheading.TLabel').grid(row=0, column=0, sticky='w')
        copy = ('Connect output datasets produced by SAS. Match each member name to a converted output.' if results else
                'Connect the datasets read by the program. Use the member name expected by SET, MERGE or SQL.')
        app.label(self, copy).grid(row=1, column=0, sticky='ew', pady=(4, 8))
        bar = FlowBar(self)
        bar.grid(row=2, column=0, sticky='ew', pady=(0, 6))
        app.button(bar, 'Add SAS results' if results else 'Add input files', self.add).pack(side='left')
        app.button(bar, 'Edit connection', self.edit).pack(side='left', padx=6)
        app.button(bar, 'Remove', self.remove).pack(side='left')
        box, self.tree = tree_view(self, [('name', 'Dataset name'), ('file', 'File'), ('encoding', 'Encoding'), ('path', 'Location')], height=3)
        box.grid(row=3, column=0, sticky='nsew')
        self.tree.bind('<Double-1>', lambda _: self.edit())
        self.tree.bind('<Return>', lambda _: self.edit())

    def show(self, entries):
        self.entries = deepcopy(entries)
        self.tree.delete(*self.tree.get_children())
        for i, entry in enumerate(self.entries):
            self.tree.insert('', 'end', iid=str(i), values=(entry.get('name') or 'From file',
                Path(entry['path']).name, entry.get('encoding') or 'From file', entry['path']))

    def add(self):
        if self.app.busy:
            return
        paths = filedialog.askopenfilenames(parent=self.winfo_toplevel(), title='Connect SAS result datasets' if self.results else 'Connect input datasets', filetypes=DATA_TYPES)
        if paths:
            self.show(self.entries + [{'path': path} for path in paths])
            self.app.invalidate()

    def edit(self):
        selected = self.tree.selection()
        if not selected or self.app.busy:
            return
        index = int(selected[0])
        item = self.entries[index]
        dialog = tk.Toplevel(self)
        dialog.title('Dataset connection')
        dialog.transient(self.winfo_toplevel())
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)
        page = ScrollPage(dialog)
        page.grid(sticky='nsew')
        area = page.body
        self.app.label(area, item['path']).grid(row=0, column=0, sticky='ew')
        self.app.label(area, 'Dataset member name. Leave blank to use the name from the file. Library-qualified names require program review.').grid(row=1, column=0, sticky='ew', pady=10)
        name = tk.StringVar(value=item.get('name', ''))
        entry = ttk.Entry(area, textvariable=name, width=36)
        entry.grid(row=2, column=0, sticky='ew')
        ttk.Label(area, text='Text encoding').grid(row=3, column=0, sticky='w', pady=(12, 4))
        encoding = tk.StringVar(value=item.get('encoding') or 'From file')
        ttk.Combobox(area, textvariable=encoding, values=['From file', 'utf-8', 'ascii', 'latin-1'], state='readonly').grid(row=4, column=0, sticky='ew')
        self.app.label(area, 'Use an explicit encoding only when you know the file encoding. The source file is not changed.').grid(row=5, column=0, sticky='ew', pady=10)
        bar = FlowBar(area)
        bar.grid(row=6, column=0, sticky='ew')
        def save():
            self.entries[index] = {'path': item['path'], 'name': name.get().strip(),
                                   'encoding': None if encoding.get() == 'From file' else encoding.get()}
            self.show(self.entries)
            self.app.invalidate()
            dialog.destroy()
        ttk.Button(bar, text='Cancel', command=dialog.destroy).pack(side='left', padx=6)
        ttk.Button(bar, text='Use connection', command=save).pack(side='left')
        dialog.bind('<Escape>', lambda _: dialog.destroy())
        dialog.geometry('640x440')
        page.connect_navigation()
        dialog.grab_set()
        entry.focus_set()

    def remove(self):
        selected = self.tree.selection()
        if selected and not self.app.busy:
            self.show([item for i, item in enumerate(self.entries) if str(i) not in selected])
            self.app.invalidate()


class DatasetView(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=12)
        self.catalog, self.page = {}, 0
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        bar = FlowBar(self)
        bar.grid(row=0, column=0, sticky='ew')
        ttk.Label(bar, text='Output dataset').pack(side='left', padx=(0, 8))
        self.selected = tk.StringVar()
        self.selector = ttk.Combobox(bar, textvariable=self.selected, state='readonly', width=24)
        self.selector.pack(side='left')
        self.selector.bind('<<ComboboxSelected>>', lambda _: self.select())
        self.note = app.label(self, 'No execution output is open.')
        self.note.grid(row=1, column=0, sticky='ew', pady=8)
        box, self.tree = tree_view(self, [], height=8)
        box.grid(row=2, column=0, sticky='nsew')
        nav = FlowBar(self)
        nav.grid(row=3, column=0, sticky='ew', pady=6)
        self.previous = ttk.Button(nav, text='Previous observations', command=lambda: self.move(-1))
        self.previous.pack(side='left')
        self.next = ttk.Button(nav, text='Next observations', command=lambda: self.move(1))
        self.next.pack(side='left', padx=6)
        self.position = ttk.Label(nav)
        self.position.pack(side='left', padx=6)
        metadata, self.metadata = text_view(self, app.code_font, height=4, wrap='word')
        metadata.grid(row=4, column=0, sticky='ew')
        metadata.grid_remove()
        self.metadata_frame = metadata
        ttk.Button(nav, text='Value / metadata details', command=self.toggle_details).pack(side='left')
        self.tree.bind('<<TreeviewSelect>>', self.row_detail)

    def show(self, catalog):
        self.catalog = catalog or {}
        names = list(self.catalog)
        self.selector.configure(values=names)
        self.selected.set(names[0] if names else '')
        self.select()

    def select(self):
        self.page = 0
        self.render()

    def move(self, step):
        self.page += step
        self.render()

    def render(self):
        table = self.catalog.get(self.selected.get(), {})
        schema, rows = table.get('schema', {}), table.get('rows', [])
        self.tree.delete(*self.tree.get_children())
        keys = ['observation'] + ['v' + str(i) for i in range(len(schema))]
        self.tree.configure(columns=keys)
        for key, label in zip(keys, ['Observation'] + list(schema)):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=160, minwidth=110)
        self.page = max(0, min(self.page, max(0, (len(rows) - 1) // PAGE_SIZE)))
        start = self.page * PAGE_SIZE
        for index in range(start, min(start + PAGE_SIZE, len(rows))):
            row = rows[index]
            self.tree.insert('', 'end', iid=str(index), values=[index + 1] + [display_value(row.get(key), key in row) for key in schema])
        self.note.configure(text=(f'{len(rows):,} observations, {len(schema):,} variables. Raw stored values; character quotes reveal spaces. SAS dates remain numeric.' if table else 'No datasets were produced by this run. See reports and the execution log for other output.'))
        self.position.configure(text=f'{start + 1 if rows else 0:,} to {min(start + PAGE_SIZE, len(rows)):,} of {len(rows):,}')
        self.previous.configure(state='normal' if self.page else 'disabled')
        self.next.configure(state='normal' if start + PAGE_SIZE < len(rows) else 'disabled')
        set_text(self.metadata, 'Dataset metadata\n' + pretty({key: value for key, value in table.items() if key != 'rows'}))

    def toggle_details(self):
        if self.metadata_frame.winfo_manager():
            self.metadata_frame.grid_remove()
        else:
            self.metadata_frame.grid()

    def row_detail(self, _=None):
        selected = self.tree.selection()
        if selected:
            table = self.catalog[self.selected.get()]
            row = table['rows'][int(selected[0])]
            set_text(self.metadata, 'Selected observation ' + str(int(selected[0]) + 1) + '\n' + '\n'.join(f'{key}: {display_value(row.get(key), key in row)}' for key in table['schema']) + '\n\nVariable metadata\n' + pretty(table['schema']))


class ComparisonView(ScrollPage):
    def __init__(self, parent, app):
        super().__init__(parent)
        body = self.body
        self.summary, self.page = {}, 0
        self.heading = app.label(body, 'No comparison is open.')
        self.heading.grid(row=0, column=0, sticky='ew', pady=(0, 8))
        box, self.datasets = tree_view(body, [('dataset', 'Dataset'), ('status', 'Comparison'), ('differed', 'Different values'), ('unpaired', 'Unpaired cells')], height=3)
        box.grid(row=1, column=0, sticky='ew')
        self.datasets.bind('<<TreeviewSelect>>', lambda _: self.select())
        self.checks = app.label(body, '')
        self.checks.grid(row=2, column=0, sticky='ew', pady=8)
        box, self.differences = tree_view(body, [('row', 'Observation'), ('variable', 'Variable'), ('expected', 'SAS result'), ('actual', 'Converted result')], height=6)
        box.grid(row=3, column=0, sticky='nsew')
        self.differences.bind('<<TreeviewSelect>>', self.detail)
        nav = FlowBar(body)
        nav.grid(row=4, column=0, sticky='ew', pady=6)
        self.previous = ttk.Button(nav, text='Previous differences', command=lambda: self.move(-1))
        self.previous.pack(side='left')
        self.next = ttk.Button(nav, text='Next differences', command=lambda: self.move(1))
        self.next.pack(side='left', padx=6)
        self.position = ttk.Label(nav)
        self.position.pack(side='left', padx=6)
        box, self.details = text_view(body, app.code_font, height=3, wrap='word')
        box.grid(row=5, column=0, sticky='ew')
        self.limits = app.label(body, '')
        self.limits.grid(row=6, column=0, sticky='ew', pady=8)
        self.connect_navigation()

    def show(self, summary, *, run_comparison=False):
        self.summary = summary or {}
        self.run_comparison = run_comparison
        self.differences.heading('expected', text='Earlier result' if run_comparison else 'SAS result')
        self.differences.heading('actual', text='Later result' if run_comparison else 'Converted result')
        status = self.summary.get('status', 'not_checked')
        if status == 'not_checked':
            headline = 'Not compared. ' + self.summary.get('reason', 'No SAS results were connected.')
        else:
            headline = ('Compared saved runs' if run_comparison else 'Compared with supplied SAS results') + ': ' + status.replace('_', ' ') + '. '
            headline += f"{self.summary.get('compared', 0):,} paired values checked: {self.summary.get('matched', 0):,} matched, {self.summary.get('differed', 0):,} different; {self.summary.get('unpaired', 0):,} unpaired cells. "
            headline += 'Rows are compared by position, with exact typed values, variable order and metadata.'
        outside = self.summary.get('uncompared_actual_datasets', [])
        if outside:
            headline += ' Outside supplied scope: ' + ', '.join(outside) + '.'
        if self.summary.get('not_checked'):
            headline += ' Not checked: ' + ', '.join(self.summary['not_checked']) + '.'
        self.heading.configure(text=headline)
        self.limits.configure(text='Import limits: ' + '; '.join(str(item) for item in self.summary.get('limits', [])) if self.summary.get('limits') else '')
        self.datasets.delete(*self.datasets.get_children())
        for i, (name, item) in enumerate(self.summary.get('datasets', {}).items()):
            self.datasets.insert('', 'end', iid=str(i), values=(name, item.get('status', '').replace('_', ' '), item.get('differed', 0), item.get('unpaired', 0)))
        children = self.datasets.get_children()
        if children:
            self.datasets.selection_set(children[0])
        self.select()

    def current(self):
        selected = self.datasets.selection()
        names = list(self.summary.get('datasets', {}))
        return self.summary['datasets'][names[int(selected[0])]] if selected and names else {}

    def select(self):
        self.page = 0
        self.render()

    def move(self, step):
        self.page += step
        self.render()

    def render(self):
        item = self.current()
        self.checks.configure(text='; '.join(key.replace('_', ' ').capitalize() + ': ' + value for key, value in item.get('checks', {}).items()) + ('\n' + item['reason'] if item.get('reason') else ''))
        rows = item.get('differences', [])
        self.page = max(0, min(self.page, max(0, (len(rows) - 1) // PAGE_SIZE)))
        start = self.page * PAGE_SIZE
        self.differences.delete(*self.differences.get_children())
        for i in range(start, min(start + PAGE_SIZE, len(rows))):
            row = rows[i]
            self.differences.insert('', 'end', iid=str(i), values=(row['observation'], row['variable'], display_value(row.get('expected'), row.get('expected_present', True)), display_value(row.get('actual'), row.get('actual_present', True))))
        self.position.configure(text=f'{start + 1 if rows else 0:,} to {min(start + PAGE_SIZE, len(rows)):,} of {len(rows):,}')
        self.previous.configure(state='normal' if self.page else 'disabled')
        self.next.configure(state='normal' if start + PAGE_SIZE < len(rows) else 'disabled')
        set_text(self.details, ('No paired value differences. Review shape and metadata checks above.' if item and not rows else 'Select a difference to read complete values.') + '\n' + (f"Observations: expected {item.get('expected_rows')}, actual {item.get('actual_rows')}." if item else ''))

    def detail(self, _=None):
        selected = self.differences.selection()
        if selected:
            row = self.current()['differences'][int(selected[0])]
            expected_label = 'Earlier result' if self.run_comparison else 'SAS result'
            actual_label = 'Later result' if self.run_comparison else 'Converted result'
            set_text(self.details, 'Observation ' + str(row['observation']) + ' | Variable: ' + row['variable'] + '\n' + expected_label + ': ' + display_value(row.get('expected'), row.get('expected_present', True)) + '\n' + actual_label + ': ' + display_value(row.get('actual'), row.get('actual_present', True)) + '\nExact typed values compared by observation position. Cause of the difference is not established.')


class Desktop:
    """Native UI over an injectable service module, with all I/O off the Tk thread."""

    def __init__(self, root, service=None):
        if service is None:
            from . import desktop_service as service
        self.root, self.service = root, service
        self.busy, self.prepared, self.record = False, None, None
        self.events, self.controls, self.labels = queue.Queue(), [], []
        self._saved_control_states = []
        self._snapshot_source, self._snapshot_name = None, None
        self._record_workspace, self._bindings = None, {}
        self._bindings_by_run = {}
        self.paths = {'source': tk.StringVar(master=root)}
        self.folder = tk.StringVar(master=root, value=str(Path.home() / 'Documents' / 'SASchi-Go'))
        self.status = tk.StringVar(master=root, value='Open a SAS program to begin. Review does not run it.')
        self.target = tk.StringVar(master=root, value='python')
        self.source_encoding = tk.StringVar(master=root, value='utf-8-sig')
        self.compare_enabled = tk.BooleanVar(master=root, value=False)
        self.font_size = tk.StringVar(master=root, value='12')
        self.body_font = font.nametofont('TkDefaultFont').copy()
        self.body_font.configure(size=12)
        self.code_font = font.nametofont('TkFixedFont').copy()
        self.code_font.configure(size=12)
        self.heading_font = self.body_font.copy()
        self.heading_font.configure(size=22, weight='bold')
        self.subheading_font = self.body_font.copy()
        self.subheading_font.configure(weight='bold')
        self.style = ttk.Style(root)
        if 'clam' in self.style.theme_names():
            self.style.theme_use('clam')
        self._style()
        root.title('SASchi-Go')
        root.geometry('1180x850')
        root.minsize(640, 540)
        root.configure(background=BG)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        header = ttk.Frame(root, padding=(20, 14, 20, 8))
        header.grid(row=0, column=0, sticky='ew')
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text='SASchi-Go', font=self.heading_font).grid(row=0, column=0, sticky='w')
        settings = ttk.Frame(header)
        settings.grid(row=0, column=1, sticky='e')
        ttk.Label(settings, text='Text size').pack(side='left', padx=6)
        size = ttk.Combobox(settings, values=['12', '14', '16'], textvariable=self.font_size, state='readonly', width=3)
        size.pack(side='left')
        size.bind('<<ComboboxSelected>>', self.resize_fonts)
        tagline = self.label(header, 'Open a program. Review the conversion. Run it when you are ready.')
        tagline.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(4, 8))
        def compact(event):
            if event.widget == root:
                tagline.grid_remove() if event.height < 680 else tagline.grid()
        root.bind('<Configure>', compact, add='+')
        workspace = ttk.Frame(header)
        workspace.grid(row=2, column=0, columnspan=2, sticky='ew')
        workspace.columnconfigure(1, weight=1)
        self.button(workspace, 'Workspace folder', self.choose_folder).grid(row=0, column=0, padx=(0, 10))
        ttk.Entry(workspace, textvariable=self.folder, state='readonly').grid(row=0, column=1, sticky='ew')
        self.tabs = ttk.Notebook(root)
        self.tabs.grid(row=1, column=0, sticky='nsew', padx=16)
        self._build_setup()
        self._build_options()
        self._build_run()
        self._build_saved()
        footer = ttk.Frame(root, padding=(20, 8, 20, 12))
        footer.grid(row=2, column=0, sticky='ew')
        footer.columnconfigure(0, weight=1)
        self.status_label = self.label(footer, '', textvariable=self.status)
        self.status_label.grid(row=0, column=0, sticky='ew')
        self.progress = ttk.Progressbar(footer, mode='indeterminate', length=100)
        self.progress.grid(row=0, column=1, padx=(8, 0))
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.bind('<Control-o>', lambda _: self.choose('source', '*.sas'))
        root.after(100, self.poll)
        self._capabilities()

    def _style(self):
        for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont'):
            font.nametofont(name).configure(size=self.body_font.actual('size'))
        self.style.configure('.', font=self.body_font, foreground=INK, background=BG)
        self.style.configure('TFrame', background=BG)
        self.style.configure('TLabel', background=BG, foreground=INK)
        self.style.configure('Subheading.TLabel', font=self.subheading_font)
        self.style.configure('TButton', padding=(10, 7))
        self.style.configure('TEntry', font=self.body_font)
        self.style.configure('TCombobox', font=self.body_font)
        self.style.configure('TMenubutton', font=self.body_font, padding=(10, 7))
        self.style.configure('Primary.TButton', background=ACCENT, foreground=PAPER)
        self.style.map('Primary.TButton', background=[('active', '#244e3f'), ('disabled', LINE)], foreground=[('disabled', MUTED)])
        self.style.configure('TNotebook', background=BG, borderwidth=0)
        self.style.configure('TNotebook.Tab', padding=(12, 8))
        self.style.map('TNotebook.Tab', background=[('selected', PAPER)])
        self.style.configure('Treeview', background=PAPER, fieldbackground=PAPER, rowheight=self.body_font.metrics('linespace') + 12)
        self.style.map('Treeview', background=[('selected', '#d5e8dc')], foreground=[('selected', INK)])
        self.style.configure('Treeview.Heading', font=self.subheading_font, padding=(6, 8))
        self.root.option_add('*TCombobox*Listbox.font', self.body_font)

    def resize_fonts(self, _=None):
        size = int(self.font_size.get())
        self.body_font.configure(size=size)
        self.code_font.configure(size=size)
        self.subheading_font.configure(size=size)
        self.heading_font.configure(size=size + 10)
        self._style()
        for pair in (self.review_code, self.run_code):
            pair.event_generate('<Configure>', width=pair.winfo_width(), height=pair.winfo_height())

    def label(self, parent, text, **kwargs):
        label = ttk.Label(parent, text=text, wraplength=620, justify='left', **kwargs)
        label.bind('<Configure>', lambda event: label.configure(wraplength=max(100, event.width)))
        return label

    def button(self, parent, text, command, *, primary=False):
        button = ttk.Button(parent, text=text, command=command, style='Primary.TButton' if primary else 'TButton')
        self.controls.append(button)
        return button

    def _build_setup(self):
        self.setup_page = ScrollPage(self.tabs)
        self.tabs.add(self.setup_page, text='Files & setup')
        area = self.setup_page.body
        ttk.Label(area, text='Start with your SAS program', style='Subheading.TLabel').grid(row=0, column=0, sticky='w')
        self.label(area, 'Your original files stay unchanged. Input files supply the program; SAS result files supply an optional comparison.').grid(row=1, column=0, sticky='ew', pady=(6, 12))
        bar = ttk.Frame(area)
        bar.grid(row=2, column=0, sticky='ew')
        bar.columnconfigure(1, weight=1)
        self.button(bar, 'Open .sas program', lambda: self.choose('source', '*.sas')).grid(row=0, column=0, padx=(0, 10))
        ttk.Entry(bar, textvariable=self.paths['source'], state='readonly').grid(row=0, column=1, sticky='ew')
        self.source_note = self.label(area, 'No program is open. Ctrl+O opens the file chooser.')
        self.source_note.grid(row=3, column=0, sticky='ew', pady=6)
        encoding = ttk.Frame(area)
        encoding.grid(row=4, column=0, sticky='w', pady=(0, 12))
        ttk.Label(encoding, text='Program text encoding').pack(side='left', padx=(0, 8))
        combo = ttk.Combobox(encoding, textvariable=self.source_encoding, values=['utf-8-sig', 'ascii', 'latin-1'], state='readonly', width=12)
        combo.pack(side='left')
        combo.bind('<<ComboboxSelected>>', lambda _: self._source_selected() if self._snapshot_source is None else self.status.set('The saved program snapshot is already decoded. Open a source file to change its encoding.'))
        self.controls.append(combo)
        self.inputs = Connections(area, self)
        self.inputs.grid(row=5, column=0, sticky='ew', pady=(0, 16))
        check = ttk.Checkbutton(area, text='Compare with SAS results', variable=self.compare_enabled, command=self._toggle_comparison)
        check.grid(row=6, column=0, sticky='w')
        self.controls.append(check)
        self.results_connections = Connections(area, self, results=True)
        self.results_connections.grid(row=7, column=0, sticky='ew', pady=12)
        self.results_connections.grid_remove()
        self.label(area, 'Without SAS results, you can inspect and run the conversion. Result agreement remains not compared.').grid(row=8, column=0, sticky='ew', pady=8)
        self.button(self.setup_page, 'Review conversion options', self.review, primary=True).grid(row=1, column=0, sticky='w', padx=16, pady=10)
        ttk.Label(area, text='Program preview', style='Subheading.TLabel').grid(row=10, column=0, sticky='w', pady=6)
        box, self.source_preview = text_view(area, self.code_font, height=10)
        box.grid(row=11, column=0, sticky='ew')
        self.setup_page.connect_navigation()

    def _build_options(self):
        self.options_page = ScrollPage(self.tabs)
        self.tabs.add(self.options_page, text='Options')
        area = self.options_page.body
        area.columnconfigure(0, weight=1)
        area.rowconfigure(2, weight=1)
        self.review_status = self.label(area, 'Review a program to see supported targets and anything that needs attention.')
        self.review_status.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        bar = FlowBar(area)
        bar.grid(row=1, column=0, sticky='ew', pady=(0, 10))
        self.run_button = self.button(bar, 'Run Python', self.start, primary=True)
        self.run_button.pack(side='left')
        self.button(bar, 'Back to files', lambda: self.tabs.select(self.setup_page)).pack(side='left', padx=6)
        self.code_button = self.button(bar, 'Save code', self.save_code)
        self.code_button.pack(side='left')
        details = ttk.Notebook(area, height=520)
        details.grid(row=2, column=0, sticky='nsew')
        review = ScrollPage(details)
        details.add(review, text='Readiness')
        body = review.body
        self.readiness = self.label(body, 'No analysis is open.')
        self.readiness.grid(row=0, column=0, sticky='ew', pady=(0, 12))
        self.target_area = ttk.Frame(body)
        self.target_area.grid(row=1, column=0, sticky='ew')
        self.target_area.columnconfigure(1, weight=1)
        for row, (title, reason) in enumerate([('Python', 'Review the program to check readiness.'), ('R', 'Needs engine work: no general R program emitter.'), ('SQL', 'Needs engine work: no general SQL program emitter.')]):
            ttk.Label(self.target_area, text=title, style='Subheading.TLabel').grid(row=row, column=0, sticky='nw', padx=(0, 16), pady=8)
            self.label(self.target_area, reason).grid(row=row, column=1, sticky='ew', pady=8)
        target_bar = FlowBar(body)
        target_bar.grid(row=2, column=0, sticky='ew', pady=10)
        self.button(target_bar, 'Review Python', lambda: self.review('python')).pack(side='left')
        self.button(target_bar, 'Advanced: preview C++', lambda: self.review('cpp')).pack(side='left', padx=6)
        self.label(body, 'C++ is a bounded scalar code preview. Desktop execution is available for Python. Generated code requires the SASchi-Go runtime or target support described in the code.').grid(row=3, column=0, sticky='ew', pady=6)
        ttk.Label(body, text='Items to review', style='Subheading.TLabel').grid(row=4, column=0, sticky='w', pady=8)
        box, self.review_notes = text_view(body, self.body_font, height=14, wrap='word')
        box.grid(row=5, column=0, sticky='ew')
        review.connect_navigation()
        self.review_code = CodePair(details, self)
        details.add(self.review_code, text='Code')
        box, self.plan_view = text_view(details, self.code_font)
        details.add(box, text='Plan')
        self.options_page.connect_navigation()

    def _build_run(self):
        self.run_page = ScrollPage(self.tabs)
        area = self.run_page.body
        self.tabs.add(self.run_page, text='Run review')
        area.columnconfigure(0, weight=1)
        area.rowconfigure(3, weight=1)
        self.run_heading = self.label(area, 'No saved run is open.')
        self.run_heading.grid(row=0, column=0, sticky='ew', pady=(0, 8))
        bar = FlowBar(area)
        bar.grid(row=1, column=0, sticky='ew', pady=(0, 8))
        self.record_buttons = []
        compare = self.button(bar, 'Compare with SAS results', self.add_comparison)
        compare.pack(side='left')
        actions = ttk.Menubutton(bar, text='More actions')
        actions.pack(side='left')
        menu = tk.Menu(actions, tearoff=False, font=self.body_font)
        menu.add_command(label='Export saved run', command=self.export)
        menu.add_command(label='New run from this', command=self.new_from_saved)
        actions.configure(menu=menu)
        self.controls.append(actions)
        self.record_buttons.extend([compare, actions])
        self.run_note = self.label(area, 'Opening saved evidence does not rerun the program.')
        self.run_note.grid(row=2, column=0, sticky='ew', pady=(0, 8))
        self.run_tabs = ttk.Notebook(area, height=520)
        self.run_tabs.grid(row=3, column=0, sticky='nsew')
        self.data_view = DatasetView(self.run_tabs, self)
        self.run_tabs.add(self.data_view, text='Data')
        comparison_area = ttk.Frame(self.run_tabs)
        comparison_area.columnconfigure(0, weight=1)
        comparison_area.rowconfigure(1, weight=1)
        selector = ttk.Frame(comparison_area, padding=(12, 8))
        selector.grid(row=0, column=0, sticky='ew')
        ttk.Label(selector, text='Comparison evidence').pack(side='left', padx=(0, 8))
        self.attempt = tk.StringVar()
        self.attempt_selector = ttk.Combobox(selector, textvariable=self.attempt, state='readonly', width=44)
        self.attempt_selector.pack(side='left', fill='x', expand=True)
        self.attempt_selector.bind('<<ComboboxSelected>>', lambda _: self.select_attempt())
        self.comparison_view = ComparisonView(comparison_area, self)
        self.comparison_view.grid(row=1, column=0, sticky='nsew')
        self.run_tabs.add(comparison_area, text='Compare')
        self.comparison_area = comparison_area
        self.run_code = CodePair(self.run_tabs, self)
        self.run_tabs.add(self.run_code, text='Code')
        box, self.reports_view = text_view(self.run_tabs, self.code_font)
        self.run_tabs.add(box, text='Reports')
        box, self.receipt_view = text_view(self.run_tabs, self.code_font)
        self.run_tabs.add(box, text='Record')
        self.run_page.connect_navigation()

    def _build_saved(self):
        self.saved_page = ttk.Frame(self.tabs, padding=14)
        self.tabs.add(self.saved_page, text='Saved runs')
        self.saved_page.columnconfigure(0, weight=1)
        self.saved_page.rowconfigure(2, weight=1)
        self.label(self.saved_page, 'Saved evidence stays available when original files move. Select one run to reopen it, or two runs to compare their outputs.').grid(row=0, column=0, sticky='ew', pady=(0, 10))
        bar = FlowBar(self.saved_page)
        bar.grid(row=1, column=0, sticky='ew', pady=(0, 10))
        for label, command in [('Refresh runs', self.refresh_runs), ('Open selected', self.open_selected), ('Compare two runs', self.compare_runs), ('Check original files', self.check_files)]:
            self.button(bar, label, command).pack(side='left', padx=(0, 6))
        box, self.saved_tree = tree_view(self.saved_page, [('created', 'Saved at'), ('source', 'SAS program'), ('execution', 'Execution'), ('comparison', 'SAS comparison'), ('id', 'Run ID')], height=10, selectmode='extended')
        box.grid(row=2, column=0, sticky='nsew')
        self.saved_tree.bind('<Double-1>', lambda _: self.open_selected())
        self.saved_tree.bind('<Return>', lambda _: self.open_selected())
        self.saved_note = self.label(self.saved_page, 'Refresh to read this workspace. No program is executed.')
        self.saved_note.grid(row=3, column=0, sticky='ew', pady=10)
        self.saved_rows = []

    def choose(self, key, pattern):
        if getattr(self, 'busy', False):
            return
        value = filedialog.askopenfilename(parent=self.root, title='Open SAS program' if key == 'source' else 'Select ' + key.replace('_', ' '), filetypes=[('Selected file type', pattern), ('All files', '*')])
        if value:
            self.paths[key].set(value)
            callback = getattr(self, '_source_selected', None)
            if key == 'source' and callback:
                callback()

    def choose_folder(self):
        if getattr(self, 'busy', False):
            return
        value = filedialog.askdirectory(parent=self.root, title='Select workspace folder', mustexist=True)
        if value:
            self.folder.set(value)
            callback = getattr(self, '_workspace_changed', None)
            if callback:
                callback()

    def _workspace_changed(self):
        self.saved_tree.delete(*self.saved_tree.get_children())
        self.saved_rows = []
        self.saved_note.configure(text='Workspace changed. Refresh to read its saved runs.')
        self.status.set('New runs will be saved in the selected workspace. The open run retains its original workspace.')

    def invalidate(self):
        self.prepared = None
        self.review_status.configure(text='Setup changed. Review conversion options again before running.')
        self._capabilities()

    def _source_selected(self):
        self._snapshot_source, self._snapshot_name = None, None
        self.invalidate()
        path, encoding = self.paths['source'].get(), self.source_encoding.get()
        set_text(self.source_preview, '')
        if path:
            self.task('Reading the SAS program. No execution is requested.', lambda: self.service.read_program(path, encoding=encoding), self._show_source)

    def _show_source(self, source):
        set_text(self.source_preview, source)
        self.source_note.configure(text='Program opened. Connect any external input datasets, then review conversion options.')
        self.status.set('Program opened. Original files stay unchanged.')

    def _toggle_comparison(self):
        if self.compare_enabled.get():
            self.results_connections.grid()
        else:
            self.results_connections.grid_remove()
        self.invalidate()

    def selection(self, target=None):
        selection = {'source': self.paths['source'].get(), 'source_encoding': self.source_encoding.get(),
                     'inputs': deepcopy(self.inputs.entries),
                     'sas_results': deepcopy(self.results_connections.entries) if self.compare_enabled.get() else [],
                     'target': target or self.target.get()}
        if self._snapshot_source is not None:
            selection.update(source_text=self._snapshot_source, source_name=self._snapshot_name)
        return selection

    def review(self, target=None):
        if self.busy:
            return
        selection = self.selection(target if isinstance(target, str) else None)
        self.prepared = None
        self.target.set(selection['target'])
        self.task('Reading files and reviewing conversion options. The program is not running.', lambda: self.service.review_setup(selection), self.show_prepared)

    def show_prepared(self, prepared):
        self.prepared = prepared
        self.target.set(prepared['target'])
        ready = prepared['ready']
        self.review_status.configure(text=('Ready to run Python.' if ready else 'Review needed. See readiness details.'))
        required = ', '.join(prepared.get('required_inputs', [])) or 'None: the program has no external dataset inputs.'
        connected = ', '.join(prepared.get('inputs', {})) or 'None'
        comparison = ', '.join(prepared.get('expected') or {}) or 'Not requested'
        layer = ('Parquet export is available through the local DuckDB data layer.' if importlib.util.find_spec('duckdb') else 'Parquet export is unavailable: the optional DuckDB data layer is not installed. Typed JSON and CSV exports remain available.')
        self.readiness.configure(text=f'Required input datasets: {required}\nConnected datasets: {connected}\nCompare with SAS results: {comparison}\nData layers: {layer}')
        for child in self.target_area.winfo_children():
            child.destroy()
        for row, target in enumerate(prepared.get('targets', [])):
            ttk.Label(self.target_area, text=target['label'], style='Subheading.TLabel').grid(row=row, column=0, sticky='nw', padx=(0, 16), pady=8)
            self.label(self.target_area, target['status'] + '. ' + target['reason']).grid(row=row, column=1, sticky='ew', pady=8)
        notes = []
        if prepared.get('missing_inputs'):
            notes.append('Connect these input datasets: ' + ', '.join(prepared['missing_inputs']))
        for ticket in prepared.get('tickets', []):
            notes.append('Line ' + str(ticket.get('line', '?')) + ': ' + ticket.get('reason', '') + '\n' + ticket.get('statement', ''))
        notes.extend(prepared.get('warnings', []))
        set_text(self.review_notes, '\n\n'.join(notes) or 'No blocking items were found in this analysis. Execution and result comparison are separate checks.')
        set_text(self.plan_view, pretty(prepared.get('plan', {})))
        self.review_code.show(prepared['source'], prepared['translation'].get('code', ''), target=prepared['target'], snapshot=self._snapshot_source is not None)
        self.tabs.select(self.options_page)
        self.status.set('Analysis complete. The program has not run.')
        self._capabilities()

    def start(self):
        if self.busy or not self.prepared or not self.prepared.get('ready'):
            return
        prepared, workspace = deepcopy(self.prepared), self.folder.get()
        self._clear_run('Running the reviewed Python conversion. Results will appear after the run is saved.')
        self.tabs.select(self.run_page)
        self.task('Running Python and saving the run record.', lambda: self.service.execute_prepared(prepared, workspace), lambda record: self.show_record(record, workspace), self._run_failed)

    def _clear_run(self, message):
        self.record = None
        self.run_heading.configure(text=message)
        self.run_note.configure(text='')
        self.data_view.show({})
        self.comparison_view.show({'status': 'not_checked', 'reason': 'No current run result is available.'})
        self.attempt_selector.configure(values=[])
        self.attempt.set('')
        self.run_code.show('', '')
        set_text(self.reports_view, '')
        set_text(self.receipt_view, '')
        self._capabilities()

    def _run_failed(self, error):
        self.run_heading.configure(text='The run could not be completed and saved: ' + str(error))
        self.run_note.configure(text='Your setup is retained. Return to Files & setup, resolve the issue, and review again. Earlier saved runs remain in the workspace.')
        self.prepared = None
        self.status.set('Run did not complete. No new saved evidence is displayed.')
        self._capabilities()

    def show_record(self, record, workspace):
        self.record, self._record_workspace = record, workspace
        key = (str(Path(workspace).expanduser().resolve()), record['id'])
        self._bindings = self._bindings_by_run.setdefault(key, {})
        execution = record.get('execution', 'unknown')
        comparison = record.get('comparison', {}).get('status', 'not_checked').replace('_', ' ')
        self.run_heading.configure(text=f"{record.get('source_name', 'SAS program')}\nExecution: {execution} | SAS comparison: {comparison}")
        error = record.get('receipt', {}).get('error')
        self.run_note.configure(text=(str(error) + '\n' if error else '') + 'Saved evidence is read-only. Record details include the run ID and timestamp.')
        result = record.get('result') or {}
        self.data_view.show(result.get('datasets', {}))
        self.run_code.show(record.get('source', ''), record.get('translation', {}).get('code', ''), target=record.get('receipt', {}).get('target', 'python'), snapshot=True)
        set_text(self.reports_view, 'Reports\n' + pretty(result.get('reports', [])) + '\n\nExecution log\n' + pretty(result.get('log', [])))
        set_text(self.receipt_view, pretty({key: value for key, value in record.items() if key not in ('source', 'translation', 'result', 'expected', 'comparison_attempts')}))
        attempts = record.get('comparison_attempts', [])
        names = ['Original run comparison'] + [str(i + 1) + ': ' + item['created_at'] + ' (' + item['summary']['status'].replace('_', ' ') + ')' for i, item in enumerate(attempts)]
        self.attempt_selector.configure(values=names)
        self.attempt.set(names[0])
        self.select_attempt()
        self.tabs.select(self.run_page)
        self.status.set('Saved run opened. Execution: ' + execution + '. SAS comparison: ' + comparison + '.')
        self._capabilities()

    def select_attempt(self):
        if not self.record:
            return
        index = self.attempt_selector.current()
        summary = self.record['comparison'] if index <= 0 else self.record['comparison_attempts'][index - 1]['summary']
        self.comparison_view.show(summary)

    def refresh_runs(self):
        workspace = self.folder.get()
        self.task('Reading saved runs. No execution is requested.', lambda: self.service.list_saved_runs(workspace), self.show_runs)

    def show_runs(self, rows):
        self.saved_rows = rows
        self.saved_tree.delete(*self.saved_tree.get_children())
        for row in rows:
            self.saved_tree.insert('', 'end', iid=row['id'], values=(row.get('created_at', ''), row.get('source_name', ''), row.get('execution', ''), row.get('comparison', {}).get('status', 'not_checked').replace('_', ' '), row['id']))
        self.saved_note.configure(text=f'{len(rows):,} saved runs in this workspace. Use Ctrl or Shift to select two for comparison.')
        self.status.set('Saved run list refreshed.')

    def open_selected(self):
        selected = self.saved_tree.selection()
        if len(selected) != 1 or self.busy:
            self.status.set('Select one saved run to open.')
            return
        workspace, run_id = self.folder.get(), selected[0]
        self.task('Opening saved evidence. Original files are not required.', lambda: self.service.open_saved_run(workspace, run_id), lambda record: self.show_record(record, workspace))

    def _saved_selection(self):
        selected = self.saved_tree.selection()
        if len(selected) != 1:
            self.status.set('Select one saved run to check its original files.')
            return None
        return self.folder.get(), selected[0]

    def check_files(self):
        selected = self._saved_selection()
        if selected:
            workspace, run_id = selected
            def checked(value):
                record, rows = value
                self.show_record(record, workspace)
                self._files_dialog(workspace, run_id, rows)
            self.task('Checking saved file identities. The program is not running.', lambda: (self.service.open_saved_run(workspace, run_id), self.service.check_saved_files(workspace, run_id, bindings=self._bindings_by_run.get((str(Path(workspace).expanduser().resolve()), run_id)))), checked)

    def _files_dialog(self, workspace, run_id, rows):
        dialog = tk.Toplevel(self.root)
        dialog.title('Original files for saved run')
        dialog.transient(self.root)
        dialog.geometry('900x510')
        dialog.minsize(640, 360)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)
        self.label(dialog, 'Saved results remain available. Locate moved originals for a new run or optional export copies. A changed file never replaces saved evidence.').grid(row=0, column=0, sticky='ew', padx=16, pady=12)
        box, tree = tree_view(dialog, [('role', 'Use'), ('name', 'File'), ('status', 'Content check'), ('path', 'Current location')], height=8)
        box.grid(row=1, column=0, sticky='nsew', padx=16)
        bindings = dict(self._bindings) if self.record and self.record['id'] == run_id else {}
        def show(items):
            tree.delete(*tree.get_children())
            for item in items:
                tree.insert('', 'end', iid=item['id'], values=(item['role'], item['dataset'] or item['name'], item['status'].replace('_', ' '), item['path']))
        def refresh():
            self.task('Checking the selected file contents.', lambda: self.service.check_saved_files(workspace, run_id, bindings=bindings), show)
        def locate():
            selected = tree.selection()
            if not selected or self.busy:
                return
            value = filedialog.askopenfilename(parent=dialog, title='Locate original file', filetypes=[('All files', '*')])
            if value:
                bindings[selected[0]] = value
                refresh()
        def finish():
            if self.busy:
                return
            if self.record and self.record['id'] == run_id:
                self._bindings = bindings
                self._bindings_by_run[(str(Path(workspace).expanduser().resolve()), run_id)] = bindings
            dialog.destroy()
        bar = FlowBar(dialog, padding=16)
        bar.grid(row=2, column=0, sticky='ew')
        self.button(bar, 'Locate selected file', locate).pack(side='left')
        self.button(bar, 'Recheck', refresh).pack(side='left', padx=6)
        self.button(bar, 'Done', finish).pack(side='right')
        show(rows)
        dialog.protocol('WM_DELETE_WINDOW', finish)
        dialog.grab_set()
        tree.focus_set()

    def new_from_saved(self):
        if not self.record or self.busy:
            return
        record, bindings, workspace = deepcopy(self.record), dict(self._bindings), self._record_workspace
        def checked(rows):
            changed = [row for row in rows if row['status'] == 'changed' and row['role'] != 'source']
            allow_changed = False
            if changed:
                allow_changed = messagebox.askyesno('Use changed files for a new run?', 'These files differ from the saved run:\n\n' + '\n'.join(row.get('dataset') or row['name'] for row in changed) + '\n\nUse their current contents for a new setup? The saved run will stay unchanged. Nothing runs until you review and choose Run.', parent=self.root)
                if not allow_changed:
                    return
            self.task('Preparing a new setup from the saved program.', lambda: self.service.select_saved_setup(record, bindings=bindings, use_saved_program=True, allow_changed=allow_changed), self.load_setup)
        self.task('Checking originals before preparing a new run.', lambda: self.service.check_saved_files(workspace, record['id'], bindings=bindings), checked)

    def load_setup(self, selection):
        self._snapshot_source = selection.get('source_text')
        self._snapshot_name = selection.get('source_name')
        self.paths['source'].set(selection.get('source') or selection.get('source_name', 'Saved program'))
        self.inputs.show(selection.get('inputs', []))
        self.results_connections.show(selection.get('sas_results', []))
        self.compare_enabled.set(bool(selection.get('sas_results')))
        self._toggle_comparison()
        self.target.set(selection.get('target', 'python'))
        self.source_note.configure(text='Using the saved SAS program snapshot. Open a different .sas file to replace it for this new setup.')
        set_text(self.source_preview, selection.get('source_text', ''))
        self.tabs.select(self.setup_page)
        self.status.set('New setup prepared. Review the connections and conversion options before running.')

    def add_comparison(self):
        if not self.record or self.busy:
            return
        workspace, run_id = self._record_workspace, self.record['id']
        dialog = tk.Toplevel(self.root)
        dialog.title('Compare with SAS results')
        dialog.transient(self.root)
        dialog.geometry('900x440')
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)
        page = ScrollPage(dialog)
        page.grid(sticky='nsew')
        body = page.body
        self.label(body, 'Compare existing converted output with SAS result files. This adds comparison evidence and does not rerun or alter the saved conversion.').grid(row=0, column=0, sticky='ew', padx=16, pady=16)
        connections = Connections(body, self, results=True)
        connections.grid(row=1, column=0, sticky='nsew', padx=16)
        compare_note = self.label(body, '')
        compare_note.grid(row=2, column=0, sticky='ew', padx=16, pady=8)
        def compare():
            if self.busy:
                return
            if not connections.entries:
                messagebox.showinfo('Connect SAS results', 'Add at least one SAS result dataset.', parent=dialog)
                return
            files = deepcopy(connections.entries)
            def done(_):
                dialog.destroy()
                self.task('Opening the new saved comparison.', lambda: self.service.open_saved_run(workspace, run_id), reopened)
            def reopened(record):
                self.show_record(record, workspace)
                self.attempt_selector.current(len(record.get('comparison_attempts', [])))
                self.select_attempt()
                self.run_tabs.select(self.comparison_area)
                self.status.set('Comparison saved. The original execution and comparison remain unchanged.')
            def failed(error):
                compare_note.configure(text='Comparison did not complete: ' + str(error) + '\nYour connections are retained. Check the files and dataset names, then try again.')
                self.status.set('Comparison did not complete. The saved run is unchanged.')
            self.task('Comparing saved output with supplied SAS results.', lambda: self.service.compare_with_sas(workspace, run_id, files), done, failed)
        bar = FlowBar(body, padding=16)
        bar.grid(row=3, column=0, sticky='ew')
        cancel = lambda: dialog.destroy() if not self.busy else None
        self.button(bar, 'Cancel', cancel).pack(side='left')
        self.button(bar, 'Compare saved output', compare).pack(side='left')
        dialog.protocol('WM_DELETE_WINDOW', cancel)
        dialog.bind('<Escape>', lambda _: cancel())
        page.connect_navigation()
        dialog.grab_set()

    def compare_runs(self):
        selected = self.saved_tree.selection()
        if len(selected) != 2 or self.busy:
            self.status.set('Select exactly two saved runs to compare.')
            return
        rows = sorted((row for row in self.saved_rows if row['id'] in selected), key=lambda row: (row['created_at'], row['id']))
        earlier, later = rows[0], rows[1]
        workspace = self.folder.get()
        self.task('Comparing two saved runs. Neither program is running.', lambda: self.service.compare_saved_runs(workspace, earlier['id'], later['id']), self.show_run_comparison)

    def show_run_comparison(self, comparison):
        self.status.set('Saved run comparison opened. No programs ran.')
        dialog = tk.Toplevel(self.root)
        dialog.title('Compare saved runs')
        dialog.geometry('1100x800')
        dialog.minsize(680, 540)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)
        self.label(dialog, 'Earlier: ' + comparison['earlier_id'] + '\nLater: ' + comparison['later_id'] + '\nThis compares saved run output. It is not a new SAS comparison. Causes of changes are not established.').grid(row=0, column=0, sticky='ew', padx=16, pady=12)
        tabs = ttk.Notebook(dialog)
        tabs.grid(row=1, column=0, sticky='nsew', padx=12, pady=(0, 12))
        outputs = ComparisonView(tabs, self)
        outputs.show(comparison.get('outputs', {}), run_comparison=True)
        tabs.add(outputs, text='Outputs')
        box, program = text_view(tabs, self.code_font)
        set_text(program, comparison['program'].get('diff') or 'Program snapshots are identical.')
        tabs.add(box, text='SAS code')
        box, inputs = text_view(tabs, self.code_font, wrap='word')
        files_copy = ['File content digests are compared. Input values are checked only when both recorded versions remain available and match their saved digests.']
        for item in comparison.get('files', []):
            identity = item.get('later') or item.get('earlier') or {}
            line = (identity.get('dataset') or identity.get('name') or item['id']) + ': file contents ' + item['status'] + '. Input values: ' + item.get('values', 'not_checked').replace('_', ' ') + '.'
            if item.get('value_comparison'):
                values = item['value_comparison']
                line += ' ' + str(values.get('compared', 0)) + ' paired values checked, ' + str(values.get('differed', 0)) + ' different.'
            if item.get('value_reason'):
                line += ' ' + item['value_reason']
            files_copy.append(line)
        files_copy.append('Earlier SAS comparison: ' + comparison.get('earlier_comparison', {}).get('status', 'not_checked').replace('_', ' '))
        files_copy.append('Later SAS comparison: ' + comparison.get('later_comparison', {}).get('status', 'not_checked').replace('_', ' '))
        set_text(inputs, '\n\n'.join(files_copy) + '\n\nRecorded details\n' + pretty(comparison.get('files', [])))
        tabs.add(box, text='Files')
        box, old = text_view(tabs, self.code_font, wrap='word')
        original = comparison.get('original_differences', [])
        copy = 'Earlier differences against SAS results, followed through to the later output. These statuses do not establish the cause.\n\n'
        copy += '\n\n'.join(item.get('dataset', '') + ', observation ' + str(item.get('observation')) + ', ' + item.get('variable', '') + ': ' + item.get('status', '').replace('_', ' ') + '\nOriginal SAS value: ' + display_value(item.get('original_expected')) + '\nEarlier output: ' + display_value(item.get('earlier_actual')) + '\nLater output: ' + display_value(item.get('later_actual')) + '\nSAS baseline identity: ' + item.get('baseline_identity', 'not recorded') for item in original) if original else 'No earlier paired value differences are recorded.'
        set_text(old, copy)
        tabs.add(box, text='Earlier differences')
        box, runtime = text_view(tabs, self.code_font, wrap='word')
        set_text(runtime, 'Runtime\n' + pretty(comparison.get('runtime', {})) + '\n\nComparison policy\n' + pretty(comparison.get('comparison_policy', {})))
        tabs.add(box, text='Runtime')
        dialog.bind('<Escape>', lambda _: dialog.destroy())

    def save_code(self):
        if self.busy or not self.prepared:
            return
        code = self.prepared.get('translation', {}).get('code', '')
        if not code:
            return
        suffix = '.cpp' if self.prepared['target'] == 'cpp' else '.py'
        destination = filedialog.asksaveasfilename(parent=self.root, title='Save converted code', initialfile='converted' + suffix, defaultextension=suffix, filetypes=[('Converted code', '*' + suffix)], confirmoverwrite=False)
        if not destination:
            return
        if Path(destination).exists():
            messagebox.showerror('Choose a new file', 'This file already exists. Choose a new name to preserve existing files.', parent=self.root)
            return
        def write():
            with Path(destination).open('x', encoding='utf-8') as stream:
                stream.write(code)
            return destination
        self.task('Saving converted code.', write, lambda path: self.status.set('Code saved to ' + str(path) + '. Generated code requires its referenced runtime and input catalog.'))

    def export(self):
        if not self.record or self.busy:
            return
        workspace, run_id = self._record_workspace, self.record['id']
        dialog = tk.Toplevel(self.root)
        dialog.title('Export saved run')
        dialog.transient(self.root)
        dialog.geometry('680x440')
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)
        page = ScrollPage(dialog)
        page.grid(sticky='nsew')
        body = page.body
        self.label(body, 'Export a ZIP containing converted code, produced datasets as typed JSON, a comparison report and a portable run record. Parquet and CSV copies are optional. Exporting does not rerun the program.').grid(row=0, column=0, sticky='ew', pady=(0, 12))
        self.label(body, 'Compared values remain in the report and record. Optional original file copies may contain additional data. The SASchi-Go runtime is not bundled.').grid(row=1, column=0, sticky='ew', pady=(0, 12))
        choices = {}
        parquet_available = importlib.util.find_spec('duckdb') is not None
        for row, (key, label) in enumerate([('include_source', 'Include the saved SAS program'), ('include_inputs', 'Include original input file copies'), ('include_sas_results', 'Include original SAS result file copies'), ('include_csv', 'Include CSV convenience copies'), ('include_parquet', 'Include Parquet with metadata sidecars')], 2):
            choices[key] = tk.BooleanVar(value=(parquet_available if key == 'include_parquet' else not parquet_available if key == 'include_csv' else False))
            check = ttk.Checkbutton(body, text=label, variable=choices[key])
            check.grid(row=row, column=0, sticky='w', pady=4)
            if key == 'include_parquet' and not parquet_available:
                check.configure(state='disabled')
            self.controls.append(check)
        if not parquet_available:
            self.label(body, 'Parquet requires the optional DuckDB data layer. Typed JSON and CSV can be exported now.').grid(row=7, column=0, sticky='ew', pady=6)
        destination_choice = tk.StringVar(value='')
        export_note = self.label(body, '')
        export_note.grid(row=9, column=0, sticky='ew', pady=8)
        def save():
            if self.busy:
                return
            destination = filedialog.asksaveasfilename(parent=dialog, title='Export saved run', initialfile=run_id + '.zip', defaultextension='.zip', filetypes=[('Review package', '*.zip')], confirmoverwrite=False)
            if not destination:
                return
            if Path(destination).exists():
                messagebox.showerror('Choose a new file', 'This export already exists. Choose a new name.', parent=dialog)
                return
            options = {key: value.get() for key, value in choices.items()}
            options['bindings'] = dict(self._bindings)
            destination_choice.set(destination)
            def exported(path):
                dialog.destroy()
                self.status.set('Saved run exported to ' + str(path))
            def failed(error):
                export_note.configure(text='Export did not complete: ' + str(error) + '\nYour options are retained. Check the location or original file connections, then try again.\nChosen location: ' + destination_choice.get())
                self.status.set('Export did not complete. The saved run is unchanged.')
            self.task('Exporting saved evidence. The program is not running.', lambda: self.service.export_saved_run(workspace, run_id, destination, **options), exported, failed)
        bar = FlowBar(body)
        bar.grid(row=8, column=0, sticky='ew', pady=16)
        cancel = lambda: dialog.destroy() if not self.busy else None
        self.button(bar, 'Cancel', cancel).pack(side='left')
        self.button(bar, 'Choose export location', save).pack(side='left')
        dialog.protocol('WM_DELETE_WINDOW', cancel)
        dialog.bind('<Escape>', lambda _: cancel())
        page.connect_navigation()
        dialog.grab_set()

    def _capabilities(self):
        if self.busy:
            return
        if hasattr(self, 'run_button'):
            self.run_button.configure(state='normal' if self.prepared and self.prepared.get('ready') else 'disabled')
            self.code_button.configure(state='normal' if self.prepared and self.prepared.get('translation', {}).get('code') else 'disabled')
        for button in getattr(self, 'record_buttons', []):
            button.configure(state='normal' if self.record else 'disabled')

    def task(self, label, operation, done, failure=None):
        if self.busy:
            return
        self.busy = True
        self.status.set(label)
        self.progress.start()
        self._saved_control_states = []
        self.controls = [widget for widget in self.controls if widget.winfo_exists()]
        for control in self.controls:
            self._saved_control_states.append((control, str(control.cget('state'))))
            control.configure(state='disabled')
        def worker():
            try:
                self.events.put((True, operation(), done, failure))
            except Exception as error:
                self.events.put((False, error, done, failure))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            ok, value, done, failure = self.events.get_nowait()
        except queue.Empty:
            self.root.after(100, self.poll)
            return
        self.busy = False
        self.progress.stop()
        for control, state in self._saved_control_states:
            if control.winfo_exists():
                control.configure(state=state)
        try:
            if ok:
                done(value)
            elif failure:
                failure(value)
            else:
                self.status.set(str(value))
                messagebox.showerror('Needs attention', str(value), parent=self.root)
        except Exception as error:
            self.status.set('The operation completed, but its view could not be displayed: ' + str(error))
            messagebox.showerror('Display needs attention', str(error), parent=self.root)
        self._capabilities()
        self.root.after(100, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo('Operation in progress', 'Wait for the current operation to finish before closing.', parent=self.root)
        else:
            self.root.destroy()
