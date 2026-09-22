"""Explicit source and runtime evidence; receipts are checksummed, not signed."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

DEPENDENCIES = ('numpy', 'pandas', 'scipy', 'duckdb')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command_version(command):
    try:
        run = subprocess.run([command, '--version'], capture_output=True, text=True, timeout=10)
        return (run.stdout or run.stderr).strip().splitlines()[0]
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def environment():
    packages = {}
    for package in DEPENDENCIES:
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    r = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript')
    cxx = os.environ.get('CXX') or shutil.which('g++')
    return {'host': platform.node(), 'platform': platform.platform(),
            'python': platform.python_version(), 'python_executable': sys.executable,
            'packages': packages, 'r_executable': r, 'r_version': command_version(r) if r else None,
            'cpp_executable': cxx, 'cpp_version': command_version(cxx) if cxx else None}


def source_state(root):
    root = Path(root).resolve()
    def git(*args):
        try:
            r = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, timeout=10)
            return r.stdout.strip() if r.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None
    head = git('rev-parse', 'HEAD')
    paths = git('ls-files', '--cached', '--others', '--exclude-standard')
    hashes = {}
    if paths is not None:
        for relative in sorted(set(paths.splitlines())):
            path = root / relative
            if path.is_file() and not path.is_symlink():
                hashes[relative] = digest(path)
    else:
        for path in sorted(root.rglob('*.py')):
            hashes[str(path.relative_to(root))] = digest(path)
    return {'git_commit': head, 'dirty': bool(git('status', '--porcelain')) if head else None,
            'files': hashes, 'source_sha256': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()}


def implementation_hashes():
    import sas_semantics
    files = {"saschi/" + p.name: digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))}
    files["sas_semantics.py"] = digest(sas_semantics.__file__)
    return files
