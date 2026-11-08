"""Desktop workflow boundary: inspect first, execute snapshots, retain evidence."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile

from .emit_py import translate as python_translate
from .emit_cpp import translate as cpp_translate
from .job import build_job
from .plan import compile_plan
from .operations import walk_operations


TARGETS = (
    {'id': 'python', 'label': 'Python', 'status': 'Available',
     'reason': 'Runs the supported program with the SASchi-Go Python runtime.', 'enabled': True},
    {'id': 'r', 'label': 'R', 'status': 'Needs engine work',
     'reason': 'R verification fixtures exist; a general R program emitter is not available.', 'enabled': False},
    {'id': 'sql', 'label': 'SQL', 'status': 'Needs engine work',
     'reason': 'Bounded SQL constructs exist; a general SQL program emitter is not available.', 'enabled': False},
    {'id': 'cpp', 'label': 'C++ (advanced)', 'status': 'Code preview only',
     'reason': 'The bounded scalar emitter can produce code. Desktop execution is Python only.', 'enabled': False},
)


def _read_program_snapshot(path, *, encoding='utf-8-sig'):
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ValueError('Choose an existing SAS program. Your previous setup is still available.')
    try:
        raw = source.read_bytes()
        return raw.decode(encoding), hashlib.sha256(raw).hexdigest()
    except UnicodeError as exc:
        raise ValueError('The SAS program could not be decoded. Select its text encoding or save a UTF-8 copy.') from exc


def read_program(path, *, encoding='utf-8-sig'):
    return _read_program_snapshot(path, encoding=encoding)[0]


def _entries(value):
    if not value:
        return []
    if isinstance(value, (str, Path)):
        return [{'path': str(value)}]
    result = []
    for item in value:
        result.append({'path': str(item)} if isinstance(item, (str, Path)) else dict(item))
    return result


def _load_connections(entries, role):
    from .data_files import load_data_file
    from .workspace import file_identity
    catalog, files, warnings, facts = {}, [], [], []
    for entry in _entries(entries):
        path = Path(entry.get('path', '')).expanduser().resolve()
        if not path.is_file():
            raise ValueError('Connected file is unavailable: ' + path.name + '. Locate it or remove this connection.')
        before = file_identity(path, role=role, dataset=entry.get('name') or None)
        imported = load_data_file(path, dataset_name=entry.get('name') or None,
                                  encoding=entry.get('encoding') or None)
        after = file_identity(path, role=role, dataset=entry.get('name') or None)
        if before['sha256'] != imported['identity']['sha256'] or before['sha256'] != after['sha256']:
            raise ValueError('The file changed while it was being read: ' + path.name + '. Review it again.')
        duplicate = set(catalog) & set(imported['catalog'])
        if duplicate:
            raise ValueError('More than one connected file supplies dataset ' + ', '.join(sorted(duplicate)) + '. Rename or remove a connection.')
        catalog.update(imported['catalog'])
        before['datasets'] = list(imported['catalog'])
        before['encoding'] = entry.get('encoding') or None
        files.append(before)
        warnings.extend(path.name + ': ' + warning for warning in imported.get('warnings', []))
        facts.append({'file': path.name, 'metadata': imported.get('metadata', {}),
                      'datasets': list(imported['catalog'])})
    return catalog, files, warnings, facts


def review_setup(selection):
    """Read and analyze selected files without executing the source program."""
    from .workspace import file_identity
    setup = deepcopy(selection)
    target = setup.get('target', 'python')
    if target not in {row['id'] for row in TARGETS}:
        raise ValueError('Choose a listed conversion target.')
    files = []
    if 'source_text' in setup:
        source = setup['source_text']
        if not isinstance(source, str):
            raise ValueError('The saved program snapshot is not text.')
        source_name = setup.get('source_name') or 'saved-program.sas'
    else:
        path = Path(setup.get('source', '')).expanduser().resolve()
        if not path.is_file():
            raise ValueError('Open a SAS program before reviewing conversion options.')
        identity = file_identity(path, role='source')
        source, snapshot_digest = _read_program_snapshot(path, encoding=setup.get('source_encoding', 'utf-8-sig'))
        if snapshot_digest != identity['sha256'] or file_identity(path, role='source')['sha256'] != identity['sha256']:
            raise ValueError('The SAS program changed while it was being read. Review it again.')
        files.append(identity)
        source_name = path.name
    if not source.strip():
        raise ValueError('The SAS program is empty. Choose a program with statements to review.')
    inputs, input_files, warnings, facts = _load_connections(setup.get('inputs'), 'input')
    expected, expected_files, expected_warnings, expected_facts = _load_connections(setup.get('sas_results'), 'sas_result')
    files.extend(input_files + expected_files)
    warnings.extend(expected_warnings)
    plan = compile_plan(source)
    python_translation = python_translate(source)
    translation = cpp_translate(source) if target == 'cpp' else python_translation
    tickets = [vars(ticket).copy() for ticket in translation.tickets]
    if target in ('r', 'sql'):
        tickets.insert(0, {'line': 0, 'statement': '', 'construct': 'target',
                           'reason': next(row['reason'] for row in TARGETS if row['id'] == target)})
    required, produced = [], set()
    for step in plan.to_dict()['steps']:
        lookups = [op['args']['dataset'] for op in walk_operations(step['operations'])
                   if op['kind'] == 'lookup']
        for name in lookups + step['inputs']:
            if name not in produced and name not in required:
                required.append(name)
        if step['name'] and step['name'] != '_null_':
            produced.add(step['name'])
    missing = [name for name in required if name not in inputs]
    unused = sorted(set(inputs) - set(required))
    if unused:
        warnings.append('Connected datasets not required by this plan: ' + ', '.join(unused) + '.')
    extra_expected = sorted(set(expected) - produced)
    if extra_expected:
        warnings.append('SAS results name datasets not produced by this plan: ' + ', '.join(extra_expected) + '. The comparison will report missing output.')
    warnings.append('Execution still checks data-dependent requirements, including BY ordering and compatible variable types. Review readiness does not establish successful execution or matching results.')
    targets = deepcopy(list(TARGETS))
    targets[0]['status'] = 'Needs attention' if python_translation.tickets or missing else 'Ready to run'
    return {'source': source, 'source_name': source_name, 'source_path': setup.get('source'),
            'source_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(),
            'inputs': inputs, 'expected': expected or None, 'files': files,
            'warnings': warnings, 'import_facts': facts + expected_facts,
            'tickets': tickets, 'required_inputs': required, 'missing_inputs': missing,
            'plan': plan.to_dict(), 'translation': {'code': translation.code,
             'blocked': translation.blocked or target in ('r', 'sql')},
            'targets': targets, 'ready': target == 'python' and not tickets and not missing,
            'target': target, 'setup': setup}


def execute_prepared(prepared, workspace_path):
    """Execute only a reviewed snapshot whose selected files still match."""
    from .workspace import Workspace, file_identity
    if not prepared.get('ready') or prepared.get('target') != 'python':
        raise ValueError('Resolve the review items and select Python before running.')
    if hashlib.sha256(prepared['source'].encode('utf-8')).hexdigest() != prepared['source_sha256']:
        raise ValueError('The reviewed program changed. Review conversion options again.')
    for record in prepared['files']:
        path = Path(record['path'])
        try:
            current = file_identity(path, role=record['role'], dataset=record.get('dataset'))
        except OSError as exc:
            raise ValueError('A reviewed file is no longer available: ' + record['name'] + '. Reconnect it and review again.') from exc
        if current['sha256'] != record['sha256']:
            raise ValueError('A reviewed file changed: ' + record['name'] + '. Review the new contents before running.')
    with tempfile.TemporaryDirectory(prefix='saschi-desktop-inputs-') as temporary:
        area = Path(temporary)
        inputs, expected = area / 'inputs.json', area / 'expected.json'
        inputs.write_text(json.dumps(prepared['inputs'], ensure_ascii=False, allow_nan=False), encoding='utf-8')
        if prepared['expected'] is not None:
            expected.write_text(json.dumps(prepared['expected'], ensure_ascii=False, allow_nan=False), encoding='utf-8')
        job = build_job(prepared['source'], inputs, expected if prepared['expected'] is not None else None, 'python')
    job.receipt['desktop_imports'] = deepcopy(prepared.get('import_facts', []))
    job.receipt['desktop_warnings'] = list(prepared.get('warnings', []))
    workspace = Workspace(Path(workspace_path).expanduser())
    return workspace.save_run(job, files=prepared['files'], expected=prepared['expected'],
                              source_name=prepared['source_name'])


def list_saved_runs(workspace_path):
    from .workspace import Workspace
    return Workspace(Path(workspace_path).expanduser()).list_runs()


def open_saved_run(workspace_path, run_id):
    from .workspace import Workspace
    return Workspace(Path(workspace_path).expanduser()).load_run(run_id)


def check_saved_files(workspace_path, run_id, bindings=None):
    from .workspace import Workspace
    return Workspace(Path(workspace_path).expanduser()).check_files(run_id, bindings=bindings)


def compare_saved_runs(workspace_path, earlier_id, later_id, *, later_attempt=None):
    from .workspace import Workspace
    return Workspace(Path(workspace_path).expanduser()).compare_runs(earlier_id, later_id, later_attempt=later_attempt)


def compare_with_sas(workspace_path, run_id, files):
    from .workspace import Workspace
    expected, identities, warnings, facts = _load_connections(files, 'sas_result')
    if not expected:
        raise ValueError('Connect at least one SAS result dataset to compare.')
    # Conversion/import caveats remain attached to the selected comparison files.
    for record in identities:
        record['import_warnings'] = warnings
        record['import_facts'] = facts
    return Workspace(Path(workspace_path).expanduser()).add_comparison(run_id, expected, files=identities)


def export_saved_run(workspace_path, run_id, destination, **options):
    from .workspace import Workspace
    return Workspace(Path(workspace_path).expanduser()).export_run(run_id, Path(destination), **options)


def select_saved_setup(record, bindings=None, use_saved_program=True, allow_changed=False):
    """Create editable choices for a new run without mutating the saved record."""
    bindings = bindings or {}
    selection = {'target': 'python', 'inputs': [], 'sas_results': [],
                 'source_name': record.get('source_name', 'saved-program.sas')}
    if use_saved_program:
        selection['source_text'] = record['source']
    for item in record.get('files', []):
        path = Path(bindings.get(item['id'], item['path'])).expanduser()
        if item['role'] == 'source' and use_saved_program:
            continue
        if path.is_file() and not allow_changed:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != item['sha256']:
                raise ValueError('Contents changed since the saved run: ' + item['name'] + '. Choose explicitly whether to use this version for a new run.')
        if item['role'] == 'source':
            selection['source'] = str(path)
        elif item['role'] in ('input', 'sas_result'):
            selection['inputs' if item['role'] == 'input' else 'sas_results'].append(
                {'path': str(path), 'name': item.get('dataset') or '', 'encoding': item.get('encoding') or None})
    return selection
