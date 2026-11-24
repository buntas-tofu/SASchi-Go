"""Windows checkout checks shared by the publication scan and synchronization."""
from pathlib import Path
import re
import subprocess


DEVICE_NAMES = {'AUX', 'CON', 'CONIN$', 'CONOUT$', 'NUL', 'PRN'} | {
    device + digit for device in ('COM', 'LPT') for digit in '123456789\u00b9\u00b2\u00b3'
}
INVALID_CHARACTERS = re.compile(r'[\x00-\x1f<>:"\\|?*]')


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True).stdout


def candidate_paths(root: Path, tree=None):
    """Include staged paths and visible candidates, even if their bytes are absent."""
    if tree is not None:
        revision = git(root, 'rev-parse', '--verify', '--end-of-options', tree + '^{tree}').decode().strip()
        raw = git(root, 'ls-tree', '-r', '-z', '--name-only', revision)
    elif (root / '.git').exists():
        raw = git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z')
    else:
        return sorted(path.relative_to(root).as_posix() for path in root.rglob('*')
                      if path.is_symlink() or path.is_file())
    return sorted(set(raw.decode('utf-8', 'surrogateescape').split('\0')) - {''})


def windows_path_issues(paths):
    issues = set()
    seen = {}
    for path in sorted(set(paths)):
        parts = path.split('/')
        prefix = ''
        for position, part in enumerate(parts, 1):
            prefix = f'{prefix}/{part}' if prefix else part
            if not part or INVALID_CHARACTERS.search(part):
                issues.add((prefix, 'invalid Windows path character or empty component'))
            if part.endswith(('.', ' ')):
                issues.add((prefix, 'trailing period or space'))
            stem = part.split('.', 1)[0].rstrip(' ').upper()
            if stem in DEVICE_NAMES:
                issues.add((prefix, 'reserved Windows device name'))
            if part.casefold() in {'.git', 'git~1'}:
                issues.add((prefix, 'reserved Git metadata name on NTFS'))
            entry = (prefix, position < len(parts))
            previous = seen.setdefault(prefix.casefold(), entry)
            if previous != entry:
                issues.add((prefix, f'case-insensitive collision with {previous[0]!a}'))
    return sorted(issues)


def check_windows_paths(root, tree=None):
    try:
        paths = candidate_paths(root, tree)
    except (OSError, subprocess.CalledProcessError):
        print('Windows path check could not read the publication candidates.')
        return 2
    issues = windows_path_issues(paths)
    for path, reason in issues:
        print(f'Windows path finding: {path!a}: {reason}')
    print(f'Windows paths: {len(paths)} checked, {len(issues)} finding(s)')
    return int(bool(issues))
