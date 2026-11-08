"""Saved execution evidence, append-only comparisons, and portable review packages.

Records describe observed jobs for analyst review. They are checksummed, not
signed, and do not establish native SAS equivalence or the origin of SAS results.
Original input files remain linked. Reopening and exporting never execute code.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import csv
import difflib
import hashlib
import html
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
import zipfile

from .compare import equal, table_equal
from .values import column_type


CONTRACT = 'typed-exact-values-ordered-rows-and-columns-metadata-v1'
_ID = re.compile(r'(?:run|comparison)-[0-9a-f]{32}\Z')
_DATASET = re.compile(r'[A-Za-z_][A-Za-z_0-9]{0,31}\Z')


def _now():
    return datetime.now(timezone.utc).isoformat()


def _encoded(value):
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2) + '\n').encode('utf-8')


def _clone(value):
    return json.loads(_encoded(value))


def _publish(path, payload):
    """Publish a complete file exclusively, without replacing existing evidence."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.saving-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def file_identity(path, *, role='input', dataset=None):
    """Capture bytes before execution; callers must recheck after reading inputs."""
    path = Path(path).expanduser().resolve()
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
        after = os.fstat(stream.fileno())
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError('File changed while its contents were being checked: ' + path.name)
    role = 'sas_result' if role == 'sas_results' else role
    if role not in ('source', 'input', 'sas_result', 'sas_log'):
        raise ValueError('Unknown file role: ' + str(role))
    return {'id': role + ':' + (dataset or path.name), 'role': role, 'dataset': dataset,
            'name': path.name, 'path': str(path), 'sha256': checksum, 'size': after.st_size}


def _files(files):
    result = _clone(files or [])
    if not isinstance(result, list):
        raise ValueError('files must be a list of captured file identities')
    seen = set()
    for entry in result:
        if not isinstance(entry, dict) or not isinstance(entry.get('id'), str) or entry['id'] in seen:
            raise ValueError('File identities require unique ids')
        if entry.get('role') == 'sas_results':
            entry['role'] = 'sas_result'
        if entry.get('role') not in ('source', 'input', 'sas_result', 'sas_log'):
            raise ValueError('File identity has an unsupported role')
        if not isinstance(entry.get('path'), str) or not isinstance(entry.get('name'), str):
            raise ValueError('File identity requires path and name')
        if not re.fullmatch('[0-9a-f]{64}', str(entry.get('sha256', ''))):
            raise ValueError('File identity requires a SHA-256 content digest')
        seen.add(entry['id'])
    return result


def _table_shape(table):
    if not isinstance(table, dict) or not isinstance(table.get('schema'), dict) or not isinstance(table.get('rows'), list):
        raise ValueError('Compared tables require schema and rows')
    if not all(isinstance(row, dict) for row in table['rows']):
        raise ValueError('Compared rows must be objects')
    for name, spec in table['schema'].items():
        if not isinstance(name, str) or column_type(spec) not in ('number', 'character'):
            raise ValueError('Compared variables require typed descriptors')


def _metadata(table):
    return {'table': {k: v for k, v in table.items() if k not in ('schema', 'rows')},
            'variables': {k: {n: v for n, v in spec.items() if n != 'type'}
                          for k, spec in table['schema'].items() if isinstance(spec, dict)}}


def compare_catalogs(actual, expected, *, include_extra=False):
    """Compare supplied dataset scope by position, keeping shape and value evidence separate.

    Counts cover paired cells only. Unpaired cells are counted separately rather
    than disguised as zero differences. Extra actual datasets are outside a SAS
    comparison's scope unless include_extra is explicitly requested.
    """
    if not isinstance(actual, dict) or not isinstance(expected, dict) or (not expected and not include_extra):
        raise ValueError('Comparison requires named datasets and a nonempty SAS result catalog')
    names = list(expected)
    if include_extra:
        names += [name for name in actual if name not in expected]
    if not names:
        return _not_checked('No output datasets were available for comparison')
    summary = {'status': 'matched', 'contract': CONTRACT, 'scope': names,
               'matched': 0, 'differed': 0, 'compared': 0, 'unpaired': 0,
               'datasets': {}, 'uncompared_actual_datasets': [n for n in actual if n not in names],
               'not_checked': ['SAS result origin', 'native SAS execution', 'SAS log']}
    for name in names:
        a, b = actual.get(name), expected.get(name)
        if (name in actual and a is None) or (name in expected and b is None):
            raise ValueError('Compared dataset cannot be null')
        for table in (a, b):
            if table is not None:
                _table_shape(table)
        item = {'status': 'differed', 'matched': 0, 'differed': 0, 'compared': 0,
                'unpaired': 0, 'differences': [], 'actual_rows': len(a['rows']) if a else None,
                'expected_rows': len(b['rows']) if b else None,
                'actual_columns': list(a['schema']) if a else [],
                'expected_columns': list(b['schema']) if b else []}
        if a is None or b is None:
            table = a if a is not None else b
            item.update(reason='Dataset missing from ' + ('converted output' if a is None else 'earlier output'),
                        unpaired=len(table['rows']) * len(table['schema']), checks={'dataset': 'differed'})
        else:
            common = [k for k in b['schema'] if k in a['schema']]
            item['checks'] = {
                'row_count': 'matched' if len(a['rows']) == len(b['rows']) else 'differed',
                'variable_names': 'matched' if a['schema'].keys() == b['schema'].keys() else 'differed',
                'variable_order': 'matched' if list(a['schema']) == list(b['schema']) else 'differed',
                'types': 'matched' if a['schema'].keys() == b['schema'].keys() and all(column_type(a['schema'][k]) == column_type(b['schema'][k]) for k in common) else 'differed',
                'schema': 'matched' if equal(a['schema'], b['schema'], ordered_maps=True) else 'differed',
                'metadata': 'matched' if equal(_metadata(a), _metadata(b)) else 'differed'}
            paired = min(len(a['rows']), len(b['rows']))
            item['unpaired'] = (len(a['rows']) * len(a['schema']) + len(b['rows']) * len(b['schema']) - 2 * paired * len(common))
            for index, (row_a, row_b) in enumerate(zip(a['rows'], b['rows'])):
                for variable in common:
                    a_has, b_has = variable in row_a, variable in row_b
                    matched = a_has and b_has and equal(row_a[variable], row_b[variable])
                    item['matched' if matched else 'differed'] += 1
                    item['compared'] += 1
                    if not matched:
                        item['differences'].append({'observation': index + 1, 'variable': variable,
                                                    'actual': row_a.get(variable), 'expected': row_b.get(variable),
                                                    'actual_present': a_has, 'expected_present': b_has})
            item['status'] = 'matched' if table_equal(a, b) else 'differed'
        if item['status'] != 'matched':
            summary['status'] = 'differed'
        for key in ('matched', 'differed', 'compared', 'unpaired'):
            summary[key] += item[key]
        summary['datasets'][name] = item
    return summary


def _not_checked(reason):
    return {'status': 'not_checked', 'reason': reason, 'contract': CONTRACT,
            'scope': [], 'matched': None, 'differed': None, 'compared': 0, 'unpaired': 0,
            'datasets': {}, 'not_checked': ['dataset values', 'SAS result origin', 'native SAS execution', 'SAS log']}


def _outputs(plan, result):
    if result is None:
        return None, []
    def produces(step):
        kind = step.get('kind', '')
        return kind in ('data', 'merge', 'sort', 'proc_means', 'sql_create', 'formatted_groups') or kind.endswith(('_data', '_sort'))
    names = list(dict.fromkeys(step.get('name') for step in plan['steps']
                              if produces(step) and step.get('name') in result.get('datasets', {}) and step.get('name') != '_null_'))
    saved = deepcopy(result)
    saved['datasets'] = {name: result['datasets'][name] for name in names}
    return _clone(saved), names


def _execution(record):
    if record['result'] is not None:
        return 'completed'
    return 'blocked' if record['receipt'].get('tickets') else 'failed'


def _import_limits(receipt=None, files=None):
    limits = ['Metadata comparison covers imported fields only; omitted SAS metadata is not checked.']
    limits += list((receipt or {}).get('desktop_warnings', []))
    for entry in files or []:
        limits += list(entry.get('import_warnings', []))
    return list(dict.fromkeys(limits))


def _input_values(earlier, later):
    """Read original versions only when their bytes still match the run identities."""
    from .data_files import load_data_file
    catalogs = []
    for identity in (earlier, later):
        current = file_identity(identity['path'], role=identity['role'], dataset=identity.get('dataset'))
        if current['sha256'] != identity['sha256']:
            raise ValueError('A recorded input version is no longer available at its linked location')
        loaded = load_data_file(identity['path'], dataset_name=identity.get('dataset'), encoding=identity.get('encoding'))
        if loaded.get('identity', {}).get('sha256') != identity['sha256']:
            raise ValueError('Decoded input bytes differ from the recorded input version')
        current = file_identity(identity['path'], role=identity['role'], dataset=identity.get('dataset'))
        if current['sha256'] != identity['sha256']:
            raise ValueError('An input changed while its values were being compared')
        catalogs.append(loaded['catalog'])
    summary = compare_catalogs(catalogs[1], catalogs[0], include_extra=True)
    summary['not_checked'] = []
    summary['limits'] = _import_limits(files=[earlier, later])
    return summary


def _original_differences(earlier, later, selected, expected, selected_files):
    tracked = []
    for dataset, evidence in earlier['comparison']['datasets'].items():
        for difference in evidence['differences']:
            observation, variable = difference['observation'], difference['variable']
            entry = {'dataset': dataset, **difference, 'earlier_actual': difference['actual'],
                     'original_expected': difference['expected'], 'later_actual': None,
                     'status': 'not_checked', 'cause': 'not established'}
            output = (later['result'] or {}).get('datasets', {}).get(dataset)
            baseline = (expected or {}).get(dataset)
            if output and observation <= len(output['rows']):
                entry['later_actual'] = output['rows'][observation - 1].get(variable)
            original_baseline = (earlier.get('expected') or {}).get(dataset)
            def identities(entries):
                return {f['sha256'] for f in entries if f['role'] == 'sas_result'
                        and (f.get('dataset') == dataset or dataset in f.get('datasets', [])
                             or not f.get('dataset') and not f.get('datasets'))}
            old_ids, new_ids = identities(earlier['files']), identities(selected_files)
            entry['baseline_identity'] = ('same' if old_ids == new_ids else 'changed') if old_ids and new_ids else 'not_recorded'
            if selected['status'] != 'not_checked' and dataset in selected.get('scope', []):
                if original_baseline is None or baseline is None:
                    entry['status'] = 'baseline_unknown'
                elif not table_equal(original_baseline, baseline) or entry['baseline_identity'] == 'changed':
                    entry['status'] = 'sas_result_changed'
                elif output and observation <= len(output['rows']) and variable in output['rows'][observation - 1]:
                    entry['status'] = 'now_matches' if equal(entry['later_actual'], difference['expected']) else 'still_differs'
                else:
                    entry['status'] = 'output_missing'
            tracked.append(entry)
    return tracked


class Workspace:
    """A local directory containing immutable runs and append-only comparisons."""

    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()

    def _run_path(self, run_id):
        if not isinstance(run_id, str) or not _ID.fullmatch(run_id) or not run_id.startswith('run-'):
            raise ValueError('Invalid saved run id')
        path = self.root / run_id
        if path.is_symlink():
            raise ValueError('Saved run directories must not be symbolic links')
        return path

    def save_run(self, job, *, files=None, expected=None, view_state=None, source_name='program.sas'):
        """Snapshot a finished job. File identities must describe bytes used by the caller."""
        run_id = 'run-' + uuid.uuid4().hex
        plan = job.plan.to_dict()
        result, names = _outputs(plan, job.result)
        expected = _clone(expected) if expected is not None else None
        if result is not None and expected is not None and job.receipt.get('comparison') in ('passed', 'failed'):
            try:
                comparison = compare_catalogs(result['datasets'], expected)
            except (ValueError, KeyError, TypeError) as exc:
                comparison = _not_checked('Dataset comparison could not complete: ' + str(exc))
        else:
            comparison = _not_checked('Execution produced no output' if result is None else
                                      'No completed dataset comparison evidence was supplied')
        comparison['limits'] = _import_limits(job.receipt, files)
        record = _clone({'schema_version': 1, 'id': run_id, 'created_at': _now(),
                         'source_name': Path(source_name).name, 'source': job.source,
                         'source_sha256': job.source_sha256, 'plan': plan,
                         'translation': {'code': job.translation.code, 'blocked': job.translation.blocked,
                                         'tickets': [vars(t) for t in job.translation.tickets]},
                         'receipt': job.receipt, 'result': result, 'output_names': names,
                         'files': _files(files), 'expected': expected, 'comparison': comparison,
                         'view_state': view_state or {}, 'code': job.code})
        record['execution'] = _execution(record)
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.saving-', dir=self.root) as temporary:
            staged = Path(temporary) / 'run'
            staged.mkdir()
            payload = _encoded(record)
            (staged / 'record.json').write_bytes(payload)
            (staged / 'record.sha256').write_text(hashlib.sha256(payload).hexdigest() + '\n', encoding='ascii')
            staged.rename(self._run_path(run_id))
        return self.load_run(run_id)

    def load_run(self, run_id):
        """Read saved evidence without reopening source or input files."""
        path = self._run_path(run_id)
        if (path / 'record.json').is_symlink() or (path / 'record.sha256').is_symlink() or (path / 'comparisons').is_symlink():
            raise ValueError('Saved evidence files must not be symbolic links')
        payload = (path / 'record.json').read_bytes()
        if hashlib.sha256(payload).hexdigest() != (path / 'record.sha256').read_text(encoding='ascii').strip():
            raise ValueError('Saved run checksum does not match; evidence was changed')
        record = json.loads(payload)
        if record.get('schema_version') != 1 or record.get('id') != run_id:
            raise ValueError('Saved run identity or schema is invalid')
        record['comparison_attempts'] = []
        for entry in sorted((path / 'comparisons').glob('comparison-*.json')):
            if entry.is_symlink():
                raise ValueError('Saved comparison files must not be symbolic links')
            attempt = json.loads(entry.read_bytes())
            checksum = attempt.pop('sha256', None)
            if checksum != hashlib.sha256(_encoded(attempt)).hexdigest() or attempt.get('run_id') != run_id:
                raise ValueError('Saved comparison checksum or run identity does not match')
            record['comparison_attempts'].append(attempt)
        record['comparison_attempts'].sort(key=lambda a: (a['created_at'], a['id']))
        return record

    def list_runs(self):
        summaries = []
        for path in self.root.glob('run-*'):
            if path.is_dir() and _ID.fullmatch(path.name):
                record = self.load_run(path.name)
                summaries.append({k: record[k] for k in ('id', 'created_at', 'source_name', 'execution', 'comparison', 'output_names')})
        return sorted(summaries, key=lambda r: (r['created_at'], r['id']), reverse=True)

    def check_files(self, run_id, bindings=None):
        result = []
        for saved in self.load_run(run_id)['files']:
            candidate = (bindings or {}).get(saved['id'], saved['path'])
            entry = {'id': saved['id'], 'role': saved['role'], 'dataset': saved.get('dataset'),
                     'name': saved['name'], 'saved_path': saved['path'], 'path': str(candidate)}
            try:
                current = file_identity(candidate, role=saved['role'], dataset=saved.get('dataset'))
                entry['current'] = current
                entry['status'] = ('same' if current['path'] == saved['path'] else 'moved_same') if current['sha256'] == saved['sha256'] else 'changed'
            except FileNotFoundError:
                entry['status'] = 'missing'
            except (OSError, ValueError) as exc:
                entry.update(status='unreadable', reason=str(exc))
            result.append(entry)
        return result

    def add_comparison(self, run_id, expected, *, files=None):
        record = self.load_run(run_id)
        summary = (_not_checked('Execution produced no output') if record['result'] is None else
                   compare_catalogs(record['result']['datasets'], expected))
        summary['limits'] = _import_limits(record['receipt'], files)
        attempt = {'id': 'comparison-' + uuid.uuid4().hex, 'run_id': run_id, 'created_at': _now(),
                   'summary': summary, 'expected': _clone(expected), 'files': _files(files)}
        envelope = {**attempt, 'sha256': hashlib.sha256(_encoded(attempt)).hexdigest()}
        _publish(self._run_path(run_id) / 'comparisons' / (attempt['id'] + '.json'), _encoded(envelope))
        return _clone(attempt)

    def compare_runs(self, earlier_id, later_id, *, later_attempt=None):
        earlier, later = self.load_run(earlier_id), self.load_run(later_id)
        if earlier['result'] is None or later['result'] is None:
            outputs = _not_checked('Both runs must have execution output to compare')
        else:
            outputs = compare_catalogs(later['result']['datasets'], earlier['result']['datasets'], include_extra=True)
            outputs['not_checked'] = []
        def connection_key(entry):
            if entry['role'] == 'source':
                return 'source'
            datasets = [entry['dataset']] if entry.get('dataset') else entry.get('datasets', [])
            return entry['role'] + ':' + ','.join(sorted(datasets)) if datasets else entry['id']
        a = {connection_key(f): f for f in earlier['files']}
        b = {connection_key(f): f for f in later['files']}
        changes = []
        for key in dict.fromkeys([*a, *b]):
            old, new = a.get(key), b.get(key)
            change = {'id': key, 'earlier': old, 'later': new,
                      'status': 'added' if old is None else 'removed' if new is None else
                      'same' if old['sha256'] == new['sha256'] else 'changed', 'values': 'not_checked'}
            if old and new and old['role'] == new['role'] == 'input':
                try:
                    values = _input_values(old, new)
                    change.update(values=values['status'], value_comparison=values)
                except (ImportError, OSError, ValueError, TypeError, KeyError) as exc:
                    change['value_reason'] = 'Original input values could not be checked: ' + str(exc)
            changes.append(change)
        selected, expected, selected_files = later['comparison'], later['expected'], later['files']
        if later_attempt is not None:
            attempt = next((a for a in later['comparison_attempts'] if a['id'] == later_attempt), None)
            if attempt is None:
                raise ValueError('Requested comparison attempt does not belong to the later run')
            selected, expected, selected_files = attempt['summary'], attempt['expected'], attempt['files']
        def runtime(record):
            receipt = record['receipt']
            return {'target': receipt.get('target'), 'package_version': receipt.get('package_version'),
                    'python': receipt.get('environment', {}).get('python'),
                    'packages': receipt.get('environment', {}).get('packages'),
                    'implementation_sha256': receipt.get('implementation_sha256')}
        old_runtime, new_runtime = runtime(earlier), runtime(later)
        return {'earlier_id': earlier_id, 'later_id': later_id,
                'program': {'status': 'same' if earlier['source'] == later['source'] else 'changed',
                            'diff': ''.join(difflib.unified_diff(earlier['source'].splitlines(True), later['source'].splitlines(True), fromfile='Earlier program', tofile='Later program'))},
                'files': changes, 'outputs': outputs,
                'runtime': {'status': 'same' if equal(old_runtime, new_runtime) else 'changed',
                            'earlier': old_runtime, 'later': new_runtime},
                'comparison_policy': {'status': 'same' if earlier['comparison']['contract'] == selected['contract'] else 'changed',
                                      'earlier': earlier['comparison']['contract'], 'later': selected['contract']},
                'earlier_comparison': earlier['comparison'], 'later_comparison': selected,
                'later_attempt': later_attempt,
                'original_differences': _original_differences(earlier, later, selected, expected, selected_files),
                'cause': 'not established'}

    def export_run(self, run_id, destination, *, include_source=False, include_inputs=False,
                   include_sas_results=False, include_csv=False, include_parquet=True, bindings=None):
        """Export preserved artifacts, refusing changed optional file copies and overwrite."""
        record = self.load_run(run_id)
        destination = Path(destination).expanduser()
        if destination.suffix.lower() != '.zip':
            raise ValueError('Export destination must end with .zip')
        if destination.exists():
            raise FileExistsError('Export destination already exists')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.export-', dir=destination.parent) as temporary:
            folder = Path(temporary) / 'contents'
            folder.mkdir()
            code_dir = folder / 'code'
            code_dir.mkdir()
            extension = '.cpp' if record['receipt'].get('target') == 'cpp' else '.py'
            (code_dir / ('converted' + extension)).write_text(record['translation']['code'], encoding='utf-8')
            data_exports = {name: {'status': 'not_applicable', 'files': []}
                            for name in ('typed_json', 'parquet', 'csv')}
            if record['result'] and record['output_names']:
                if include_parquet:
                    from .data_files import export_parquet
                outputs = folder / 'results'
                outputs.mkdir()
                data_exports['typed_json']['status'] = 'included'
                data_exports['parquet']['status'] = 'included' if include_parquet else 'not_requested'
                data_exports['csv']['status'] = 'included' if include_csv else 'not_requested'
                for name, table in record['result']['datasets'].items():
                    if not _DATASET.fullmatch(name):
                        raise ValueError('Unsafe output dataset name')
                    (outputs / (name + '.json')).write_bytes(_encoded(table))
                    data_exports['typed_json']['files'].append('results/' + name + '.json')
                    if include_parquet:
                        export_parquet(table, outputs / (name + '.parquet'))
                        data_exports['parquet']['files'] += ['results/' + name + '.parquet',
                                                            'results/' + name + '.metadata.json']
                    if include_csv:
                        data_exports['csv']['files'].append('results/' + name + '.csv')
                        with (outputs / (name + '.csv')).open('w', encoding='utf-8', newline='') as stream:
                            writer = csv.writer(stream)
                            writer.writerow(table['schema'])
                            for row in table['rows']:
                                writer.writerow([('.' + value['missing'] if isinstance(value, dict) else value)
                                                 for value in (row[k] for k in table['schema'])])
            if record['result'] is not None:
                (folder / 'execution.log').write_text('\n'.join(record['result'].get('log', [])) + '\n', encoding='utf-8')
                for category in ('reports', 'exports'):
                    for name, content in record['result'].get(category, {}).items():
                        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,239}', name):
                            raise ValueError('Unsafe generated artifact name')
                        target = folder / category
                        target.mkdir(exist_ok=True)
                        (target / name).write_text(content, encoding='utf-8')
            omissions = []
            if record['output_names'] and not include_parquet:
                omissions.append('Parquet output was not selected for this package. Typed JSON results retain the saved values and metadata; no Parquet file or sidecar is included.')
                data_exports['parquet']['reason'] = 'Parquet export was not selected. It requires an available DuckDB installation.'
            if include_source:
                (folder / 'source').mkdir()
                (folder / 'source' / 'program.sas').write_text(record['source'], encoding='utf-8')
            else:
                omissions.append('Original SAS program file copy: excluded from package.')
            if not include_csv:
                omissions.append('Optional CSV result copy: excluded from package.')
            else:
                omissions.append('CSV is a convenience copy; use typed JSON or Parquet with its metadata sidecar for typed results.')
            for role, selected, subdirectory in (('input', include_inputs, 'inputs'), ('sas_result', include_sas_results, 'sas-results')):
                candidates = record['files'] + [f for a in record['comparison_attempts'] for f in a['files']]
                captured = list({(f['id'], f['sha256']): f for f in candidates if f['role'] == role}.values())
                if not captured:
                    omissions.append(role + ': no original file identity was supplied for this run.')
                for index, entry in enumerate(captured, 1):
                    if not selected:
                        omissions.append(entry['name'] + ': original file copy excluded from package.')
                        continue
                    path = Path((bindings or {}).get(entry['id'], entry['path']))
                    raw = path.read_bytes()
                    if hashlib.sha256(raw).hexdigest() != entry['sha256']:
                        raise ValueError('Selected original file has changed: ' + entry['name'])
                    target = folder / subdirectory
                    target.mkdir(exist_ok=True)
                    # Prefix prevents duplicate basenames; basename prevents path traversal.
                    (target / (str(index) + '-' + Path(entry['name']).name)).write_bytes(raw)
            portable = _portable_record(record, omissions, data_exports)
            (folder / 'run-record.json').write_bytes(_encoded(portable))
            (folder / 'comparison-report.html').write_text(comparison_report(record, omissions, data_exports=data_exports), encoding='utf-8')
            (folder / 'README.txt').write_text(
                'Saved run evidence for analyst review. Exporting does not rerun the program.\n'
                'Read comparison-report.html for differences, scope and items not checked.\n'
                'Python output imports saschi.runtime and expects an input catalog from its caller.\n'
                'It does not load native input files or write Parquet by itself.\n'
                'Use Python 3.11 or later and the recorded SASchi-Go runtime and dependencies.\n'
                'The runtime is not bundled. Original file copies are optional; compared values remain included.\n'
                'Produced datasets are always included as typed JSON with ordered schema, stored metadata and missing-value tags.\n'
                'Parquet output: ' + data_exports['parquet']['status'].replace('_', ' ') + '.\n'
                'CSV output: ' + data_exports['csv']['status'].replace('_', ' ') + '.\n'
                'See data_exports in run-record.json for the actual files included.\n'
                'File digests detect changed contents; they do not establish SAS result provenance.\n', encoding='utf-8')
            archive_path = Path(temporary) / 'package.zip'
            with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(folder.rglob('*')):
                    if path.is_file():
                        archive.write(path, path.relative_to(folder).as_posix())
            _publish(destination, archive_path.read_bytes())
        return destination


def _portable_record(record, omissions, data_exports):
    receipt = record['receipt']
    environment = receipt.get('environment', {})
    return {'schema_version': 1, 'id': record['id'], 'created_at': record['created_at'],
            'source_sha256': record['source_sha256'], 'execution': record['execution'],
            'target': receipt.get('target'), 'package_version': receipt.get('package_version'),
            'runtime': {k: environment.get(k) for k in ('python', 'packages', 'r_version', 'cpp_version')},
            'implementation_sha256': receipt.get('implementation_sha256'),
            'output_names': record['output_names'], 'comparison': record['comparison'],
            'data_exports': data_exports,
            'comparison_attempts': [{'id': a['id'], 'created_at': a['created_at'], 'summary': a['summary']}
                                    for a in record['comparison_attempts']],
            'files': [{k: f.get(k) for k in ('id', 'role', 'dataset', 'name', 'sha256', 'size')} for f in record['files']],
            'import_warnings': receipt.get('desktop_warnings', []),
            'import_facts': receipt.get('desktop_imports', []),
            'omissions': omissions, 'not_checked': ['SAS result origin', 'native SAS execution'],
            'other_comparisons': {k: receipt.get(k, 'not requested') for k in ('log_comparison', 'report_comparison', 'export_comparison')}}


def comparison_report(record, omissions=None, *, data_exports=None):
    """A scoped report; unlike showcase it contains neither source nor input catalog."""
    escape = lambda value: html.escape(str(value))
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><title>SASchi-Go comparison report</title>',
             '<style>body{font:18px/1.5 system-ui,sans-serif;max-width:1000px;margin:2em auto;padding:1em}table{border-collapse:collapse;width:100%}th,td{text-align:left;border-bottom:1px solid #ccc;padding:.5em}pre{white-space:pre-wrap}h2{margin-top:2em}</style>',
             '<h1>Saved run comparison</h1><p>Execution evidence for analyst review. This report does not establish native SAS equivalence or approve output for use.</p>',
             '<p>Run: ' + escape(record['id']) + '. Execution: ' + escape(record['execution']) + '.</p>']
    comparisons = [('Original comparison', record['comparison'])]
    comparisons += [('Additional comparison ' + a['id'], a['summary']) for a in record.get('comparison_attempts', [])]
    for label, summary in comparisons:
        parts.append('<h2>' + escape(label) + ': ' + escape(summary['status'].replace('_', ' ')) + '</h2>')
        if summary.get('limits'):
            parts.append('<p>Import and metadata limits: ' + escape(' '.join(summary['limits'])) + '</p>')
        if summary['status'] == 'not_checked':
            parts.append('<p>' + escape(summary['reason']) + '. No match or difference count is established.</p>')
            continue
        parts.append('<p>' + escape(summary['matched']) + ' values matched; ' + escape(summary['differed']) +
                     ' values differed; ' + escape(summary['unpaired']) + ' unpaired values. Scope: ' + escape(', '.join(summary['scope'])) + '.</p>')
        for name, dataset in summary['datasets'].items():
            parts.append('<h3>' + escape(name) + ': ' + escape(dataset['status']) + '</h3><p>' + escape(dataset.get('reason', '')) + '</p>')
            parts.append('<p>Structure checks: ' + escape(json.dumps(dataset.get('checks', {}))) + '</p>')
            if dataset['differences']:
                parts.append('<table><thead><tr><th>Observation</th><th>Variable</th><th>Supplied SAS value</th><th>Converted value</th></tr></thead><tbody>')
                for diff in dataset['differences']:
                    parts.append('<tr>' + ''.join('<td>' + escape(value) + '</td>' for value in (
                        diff['observation'], diff['variable'], diff['expected'] if diff['expected_present'] else '(absent)',
                        diff['actual'] if diff['actual_present'] else '(absent)')) + '</tr>')
                parts.append('</tbody></table>')
    if data_exports is not None:
        parts.append('<h2>Produced dataset files</h2><ul>')
        for name, details in data_exports.items():
            parts.append('<li>' + escape(name.replace('_', ' ')) + ': ' + escape(details['status'].replace('_', ' ')) +
                         '. ' + escape(', '.join(details['files'])) + '</li>')
        parts.append('</ul><p>Typed JSON retains the saved values, ordered schema, stored metadata and missing-value tags. CSV copies do not replace that typed evidence.</p>')
    parts += ['<h2>Comparison rules and limits</h2><p>Exact typed values, observation order, variable order and stored metadata. No tolerance or key-based realignment. Matching values do not establish the cause of earlier differences.</p>',
              '<p>SAS result origin: not checked. Native SAS execution: not performed by this run.</p>',
              '<p>SAS log comparison: ' + escape(record['receipt'].get('log_comparison', 'not requested')) + '.</p>',
              '<h2>Package contents and omissions</h2><ul>']
    parts += ['<li>' + escape(item) + '</li>' for item in omissions or []]
    parts += ['</ul><p>Excluded file copies are distinct from evidence never supplied. Compared values remain included. Generated Python requires the recorded SASchi-Go runtime and input data; it is not a standalone data-loading script.</p></html>']
    return ''.join(parts)
