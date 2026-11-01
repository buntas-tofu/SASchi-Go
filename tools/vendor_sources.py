"""Pinned external fixture acquisition; verification never performs network I/O."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'docs/vendor-benchmark-manifest.json'
MAX_FILE_BYTES = 1048576


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _pairs(items):
    result = {}
    for key, value in items:
        _need(key not in result, 'duplicate vendor manifest key')
        result[key] = value
    return result


def _relative(value):
    _need(type(value) is str and value and value.isascii(), 'vendor path requires nonempty ASCII')
    path = PurePosixPath(value)
    _need(bool(path.parts) and not path.is_absolute() and str(path) == value and
          all(part not in ('.', '..', '.git') for part in path.parts) and
          not any(c in value for c in ('\\', ':', '\0')) and
          all(32 <= ord(c) <= 126 for c in value), 'unsafe vendor relative path')
    return value


def validate_manifest(value):
    _need(type(value) is dict and set(value) == {'schema_version', 'status', 'programs'} and
          type(value['schema_version']) is int and value['schema_version'] == 1 and
          type(value['status']) is str and value['status'] and
          type(value['programs']) is list and 1 <= len(value['programs']) <= 32,
          'vendor manifest requires version1, status and a bounded program list')
    ids, destinations = set(), {}
    for program in value['programs']:
        _need(type(program) is dict and set(program) == {
            'id', 'repository', 'commit', 'license_identifier', 'source', 'license'},
            'vendor program requires exact identity, source and license fields')
        name = program['id']
        _need(type(name) is str and re.fullmatch(r'[a-z][a-z0-9-]{0,63}', name, re.ASCII)
              and name not in ids, 'invalid or duplicate vendor program id')
        ids.add(name)
        repo, commit = program['repository'], program['commit']
        _need(type(repo) is str and re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+', repo, re.ASCII)
              and repo.split('/')[1] not in ('.', '..'), 'invalid vendor repository identity')
        _need(type(commit) is str and re.fullmatch(r'[0-9a-f]{40}', commit),
              'vendor source requires an immutable full commit')
        _need(program['license_identifier'] == 'Apache-2.0', 'unadmitted vendor license')
        for role in ('source', 'license'):
            item = program[role]
            _need(type(item) is dict and set(item) == {'path', 'bytes', 'sha256', 'git_blob_sha1'},
                  'vendor file requires exact byte and hash fields')
            relative = _relative(item['path'])
            _need(type(item['bytes']) is int and 1 <= item['bytes'] <= MAX_FILE_BYTES,
                  'vendor file byte bound is invalid')
            for key, width in [('sha256', 64), ('git_blob_sha1', 40)]:
                _need(type(item[key]) is str and re.fullmatch('[0-9a-f]{' + str(width) + '}', item[key]),
                      'invalid vendor content hash')
            destination = repo + '/' + commit + '/' + relative
            _need(destination not in destinations or destinations[destination] == item,
                  'conflicting vendor cache identities')
            destinations[destination] = item
        _need(program['source']['path'] != program['license']['path'], 'source and license paths collide')
    return value


def read_manifest(path=MANIFEST):
    data = Path(path).read_bytes()
    _need(len(data) <= MAX_FILE_BYTES, 'vendor manifest exceeds one MiB')
    try:
        value = json.loads(data, object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite manifest JSON')))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError('vendor manifest requires bounded valid JSON') from error
    return validate_manifest(value)


def cache_root(value=None):
    path = Path(value if value is not None else os.environ.get(
        'SASCHI_VENDOR_CACHE', str(Path(tempfile.gettempdir()) / 'saschi-vendor-cache'))).absolute()
    _need('.git' not in path.parts, 'vendor cache cannot use Git metadata directories')
    _need(not path.resolve().is_relative_to(ROOT.resolve()), 'vendor bodies cannot be stored inside Go')
    for part in (path, *path.parents):
        _need(not part.is_symlink(), 'vendor cache path cannot follow symlinks')
    for part in (path.resolve(), *path.resolve().parents):
        # A machine-wide scratch Git marker must not absorb every temporary
        # research directory. A closer checkout still refuses independently.
        if part == Path(tempfile.gettempdir()).resolve():
            break
        _need(not (part / '.git').exists(), 'vendor bodies must stay outside Git checkouts')
    return path


def _safe_path(root, relative):
    path = root / _relative(relative)
    for part in (path, *path.parents):
        if part == root.parent:
            break
        _need(not part.is_symlink(), 'vendor cache entry cannot follow symlinks')
        _need(not (part / '.git').exists(), 'vendor bodies must stay outside nested Git checkouts')
    return path


def _matches(data, item):
    _need(type(data) is bytes and len(data) == item['bytes'] and
          hashlib.sha256(data).hexdigest() == item['sha256'] and
          hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == item['git_blob_sha1'],
          'vendor source or license bytes differ from the immutable pin')


def _read_pinned(path, item):
    with path.open('rb') as stream:
        data = stream.read(item['bytes'] + 1)
    _matches(data, item)
    return data


def _entries(manifest):
    result = {}
    for program in validate_manifest(manifest)['programs']:
        for role in ('source', 'license'):
            item = program[role]
            relative = program['repository'] + '/' + program['commit'] + '/' + item['path']
            result[relative] = (program, item)
    return result


def verify_sources(manifest=None, cache=None):
    """Check all selected original bytes locally; missing files fail explicitly."""
    manifest = read_manifest() if manifest is None else validate_manifest(manifest)
    root = cache_root(cache)
    for relative, (_, item) in _entries(manifest).items():
        path = _safe_path(root, relative)
        _need(path.is_file(), 'pinned vendor cache is missing; run python tools/prepare_vendor_sources.py')
        _read_pinned(path, item)
    return {program['id']: {
        'source': _safe_path(root, program['repository'] + '/' + program['commit'] + '/' + program['source']['path']),
        'license': _safe_path(root, program['repository'] + '/' + program['commit'] + '/' + program['license']['path']),
        'program': program,
    } for program in manifest['programs']}


def _download(url):
    request = Request(url, headers={'User-Agent': 'SASchi-Go-pinned-fixture-preparation/1.0'})
    with urlopen(request, timeout=30) as response:
        _need(response.status == 200, 'vendor download did not return200')
        data = response.read(MAX_FILE_BYTES + 1)
    _need(len(data) <= MAX_FILE_BYTES, 'vendor download exceeds one MiB')
    return data


def prepare_sources(manifest=None, cache=None, *, fetch=_download):
    """Fetch and verify before writing; existing conflicting files are refused."""
    manifest = read_manifest() if manifest is None else validate_manifest(manifest)
    root = cache_root(cache)
    entries = _entries(manifest)
    bodies = {}
    for relative, (program, item) in entries.items():
        path = _safe_path(root, relative)
        if path.exists():
            _need(path.is_file(), 'vendor cache entry is not a regular file')
            _read_pinned(path, item)
            continue
        url = 'https://raw.githubusercontent.com/' + program['repository'] + '/' + program['commit'] + '/' + quote(item['path'], safe='/')
        bodies[relative] = fetch(url)
        _matches(bodies[relative], item)
    root.mkdir(parents=True, exist_ok=True)
    for relative, data in bodies.items():
        path = _safe_path(root, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation never replaces an existing source or license.
        with path.open('xb') as stream:
            stream.write(data)
    return verify_sources(manifest, root)
