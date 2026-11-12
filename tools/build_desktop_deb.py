#!/usr/bin/env python3
"""Build an Ubuntu desktop package from the local wheel, without downloading."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DESKTOP_REVISION = 'desktop3'


def build(destination):
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ValueError('Refusing to overwrite an existing package: ' + str(destination))
    with tempfile.TemporaryDirectory(prefix='saschi-desktop-build-') as temporary:
        area = Path(temporary)
        subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation', '--no-index', '--wheel-dir', str(area), str(ROOT)], check=True)
        wheel, = area.glob('*.whl')
        stage = area / 'package'
        library = stage / 'usr/lib/saschi-desktop'
        library.mkdir(parents=True)
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(library)
        binary = stage / 'usr/bin/saschi-desktop'
        binary.parent.mkdir(parents=True)
        binary.write_text('#!/usr/bin/python3\nimport sys\nsys.path.insert(0, "/usr/lib/saschi-desktop")\nfrom saschi.desktop import main\nraise SystemExit(main())\n')
        binary.chmod(0o755)
        entry = stage / 'usr/share/applications/saschi-desktop.desktop'
        entry.parent.mkdir(parents=True)
        entry.write_text('[Desktop Entry]\nType=Application\nName=SASchi-Go\nComment=Run local SAS migration jobs with saved receipts\nExec=saschi-desktop\nIcon=applications-development\nTerminal=false\nCategories=Development;Science;\nStartupNotify=true\n')
        docs = stage / 'usr/share/doc/saschi-desktop'
        docs.mkdir(parents=True)
        (docs / 'copyright').write_bytes((ROOT / 'LICENSE').read_bytes())
        (docs / 'README').write_bytes((ROOT / 'docs/DESKTOP.md').read_bytes())
        control = stage / 'DEBIAN/control'
        control.parent.mkdir()
        control.write_text('Package: saschi-desktop\nVersion: ' + version + '+' + DESKTOP_REVISION + '\nSection: science\nPriority: optional\nArchitecture: all\nMaintainer: SASchi-Go maintainers\nDepends: python3 (>= 3.11), python3-tk, python3-pandas, xdg-utils\nDescription: Local SASchi-Go desktop workflow\n Native file dialogs, bounded local execution and saved job receipts.\n')
        subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(stage), str(destination)], check=True)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(build(parser.parse_args().output))
