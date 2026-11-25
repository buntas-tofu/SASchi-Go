#!/usr/bin/env python3
"""check_sanitization.py : the token gate for the sanitization floor.

Design doc section 9: the tree carries no host/infra/persona identity
beyond the instance's allowed tokens. Three classes are forbidden in EVERY
instance: estate and fabric terms, identifiers of people (a work account, a
work filesystem root, a byline carrying a personal name), and the lane the
tree does not belong to. Sibling-lane names are forbidden per profile.

  desk    (buntas-tofu): allowed identity is the-pgh-cid / Matthew Haubach.
            Forbidden: estate and fabric terms, and the public-lane persona
            names (cross-lane tokens).
  buntas  (the public sister): allowed identity is buntas-tofu and the
            persona names. Forbidden: estate and fabric terms, the desk
            account name, and the public-lane ruling's model-vendor strings.

Exemptions are declarations, not conveniences:
  - any directory containing a SOURCE.json stamp (byte-stable synced copies
    of canonical content; the stamp names the source by design)
  - vendor/ (declared foreign trees, see vendor/README.md)
  - .git and the usual build/dependency directory names

Every exemption and every surviving hit must be classified LEAK or SUBJECT
MATTER (the scrub is a hypothesis; the classification is the deliverable).
Adjudicated subject-matter hits live in scripts/sanitization-allowlist.json
with a reason; the gate fails on anything unclassified.
An optional sha256 field restricts a declaration to the exact file bytes.
Changing those bytes removes that declaration's effect.

Four classes are forbidden in EVERY instance: estate and fabric terms,
identifiers of people, credentials, and the lane the tree does not belong to.
Credentials are matched by SHAPE (provider token prefixes, private key headers,
signed tokens) so a credential this list has never seen still trips.

Checks: file CONTENT (case-insensitive, word-boundary patterns plus a
no-boundary pass for whole snake_case identifier segments), FILE NAMES, and
STAGED CONTENT taken from the git index so a pre-commit run judges what git
will record rather than what the working tree happens to hold.

The scan domain is the PUBLISHED SURFACE: tracked files plus untracked files
git would include, enumerated with `git ls-files --cached --others
--exclude-standard`. A gitignored directory of local receipts carries home
paths by design, and letting it into the scan buries the handful of real
findings under a thousand true statements about the machine it ran on. When the
target is not a git worktree, for instance an unpacked package payload, the
walk covers every file; extensionless files count as text when they decode, so
a packaged licence or copyright file is read.

This script is exempt from its own scan by
declaration: it IS the token list, and copying the list into other artifacts
is exactly what the floor forbids. Exit 0 clean, 1 findings, 2 usage error.
Pure standard library.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

if __package__:
    from .windows_paths import check_windows_paths
else:
    from windows_paths import check_windows_paths

ROOT = Path(__file__).resolve().parent.parent

# estate and fabric terms: forbidden in EVERY instance
ESTATE = [
    r"\bbesaid\b", r"\bfahrenheit\b", r"tail1571d6", r"\btonberry\b",
    r"\bspira\b", r"\bfayth\b", r"\bmognet\b", r"\bmoggle\b", r"\btifa\b",
    r"\bvalefor\b", r"\bwutai\b", r"7th-heaven", r"\bauron\b",
    r"the estate", r"/home/[a-z]", r"C\.R\.E\.A\.M", r"\bhighwind\b",
    r"\bstrahl\b", r"mhaubach@gmail", r"thepghcidv",
]

PERSONA = [
    r"\bsaschi\b", r"\bspeedstars\b", r"\bbuntas\b", r"hachi", r"ae86",
    r"redrum", r"inertia-drift", r"\broku\b", r"initial d\b", r"fujiwara",
]

# Identifiers of people rather than lanes: a work account, a work filesystem
# root, and a byline that carries a personal name. The byline rule exists
# because a list of names cannot catch a name that is not on the list; the
# pattern catches the SHAPE, and every hit is classified.
PERSONAL = [
    r"\bhauba\d{3}\b",
    r"/fsx/home/[a-z]",
    r"^\s*(?:author|written by)\s*:\s*[A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+",
]

# Credentials are a class the identity lists do not carry: a token pasted into
# a doc, a key in a fixture, a signed URL in a recorded receipt. These patterns
# describe SHAPES, never values, so a new credential trips the gate instead of
# walking through a list that was written before it existed.
CREDENTIAL = [
    r"\bgh[pousr]_[A-Za-z0-9]{32,}",
    r"github_pat_[A-Za-z0-9_]{40,}",
    r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
    r"\bxox[baprs]-[A-Za-z0-9-]{20,}",
    r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}",
    r"-----BEGIN [A-Z ]{0,40}PRIVATE KEY-----",
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{15,}",
]

DESK_FORBIDDEN = ESTATE + PERSONAL + PERSONA + CREDENTIAL + [r"\bseats?(\b|_)"]
BUNTAS_FORBIDDEN = ESTATE + PERSONAL + CREDENTIAL + [
    r"the-pgh-cid", r"\bclaude\b", r"\banthropic\b", r"\bfable\b",
]

TEXT_SUFFIXES = {
    ".md", ".markdown", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".conf", ".py", ".r", ".R", ".sh", ".sql", ".sas",
    ".js", ".ts", ".html", ".css", ".xml", ".csv", ".tsv", ".thrift",
    ".bat", ".ps1", ".service", ".desktop", ".md5sum",
}
# .github is NOT skipped: a workflow is published surface, it carries paths,
# hosts and secrets, and it was the one directory this gate never read.
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv",
             "node_modules", "dist", "build"}
# extensionless files count as text when they decode, because a packaged
# licence, a copyright file and a launcher shim all arrive without a suffix.
EXTENSIONLESS_MAX_BYTES = 2 * 1024 * 1024


def looks_like_text(path: Path) -> bool:
    if path.suffix in TEXT_SUFFIXES:
        return True
    if path.suffix:
        return False
    try:
        if path.stat().st_size > EXTENSIONLESS_MAX_BYTES:
            return False
        path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return True



def load_allowlist():
    f = ROOT / "scripts" / "sanitization-allowlist.json"
    if not f.is_file():
        return []
    return json.loads(f.read_text())


def stamped_dirs(root: Path):
    """Directories under stamp control (a SOURCE.json marks the subtree)."""
    out = []
    for p in root.rglob("SOURCE.json"):
        out.append(p.parent)
    return out


def is_exempt(path: Path, root: Path, exempt: list) -> bool:
    rel = path.relative_to(root)
    parts = set(rel.parts)
    if parts & SKIP_DIRS:
        return True
    if "vendor" in parts:
        return True
    for d in exempt:
        try:
            rel.relative_to(d.relative_to(root))
            return True
        except ValueError:
            continue
    return False


def allowed(allowlist, rel, pattern, path):
    for row in allowlist:
        if re.search(row["path"], str(rel)) and row["pattern"] == pattern:
            if "sha256" in row:
                try:
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                except OSError:
                    continue
                if digest != row["sha256"]:
                    continue
            return row
    return None


def staged_findings(root: Path, compiled: list) -> list:
    """Scan content staged in the index, not only what is on disk.

    A pre-commit run otherwise reads the working tree while git records the
    index, so a line added with `git add -p` and then edited back on disk
    reaches the commit without ever being scanned.
    """
    if not (root / ".git").exists():
        return []
    try:
        listed = subprocess.run(
            ["git", "-C", str(root), "diff", "--cached", "--name-only",
             "--diff-filter=ACMR", "-z"],
            capture_output=True, check=True, timeout=30).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []
    out = []
    for rel in sorted({n for n in listed.decode("utf-8", "surrogateescape").split("\0") if n}):
        if set(Path(rel).parts) & SKIP_DIRS:
            continue
        if rel in {"scripts/check_sanitization.py",
                   "scripts/sanitization-allowlist.json"}:
            continue
        try:
            raw = subprocess.run(
                ["git", "-C", str(root), "show", ":" + rel],
                capture_output=True, check=True, timeout=30).stdout
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for p, rx in compiled:
                if rx.search(line):
                    out.append((rel, i, p + " [staged]", line.strip()[:90]))
    return out


def candidate_files(root: Path) -> list:
    """What git would publish, and nothing else.

    Scanning the whole filesystem makes a single gitignored receipts directory
    produce a thousand findings that bury the handful of real ones, and every
    one of them carries the home path the local run legitimately recorded. The
    scan domain is tracked files plus untracked files git would include, which
    is the published surface.
    """
    if (root / ".git").exists():
        try:
            listed = subprocess.run(
                ["git", "-C", str(root), "ls-files", "-z", "--cached",
                 "--others", "--exclude-standard"],
                capture_output=True, check=True, timeout=60).stdout
            names = {n for n in listed.decode("utf-8", "surrogateescape").split("\0") if n}
            return sorted((root / n) for n in names if (root / n).is_file())
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
    return sorted(p for p in root.rglob("*") if p.is_file())


def run(profile: str, root: Path) -> int:
    if profile == "desk":
        patterns = DESK_FORBIDDEN
    elif profile == "buntas":
        patterns = BUNTAS_FORBIDDEN
    else:
        print(f"error: unknown profile {profile!r}", file=sys.stderr)
        return 2
    path_status = check_windows_paths(root)
    if path_status:
        return path_status
    compiled = [(p, re.compile(p, re.I)) for p in patterns]
    nobound = [(p, re.compile(p.replace(r"\b", ""), re.I)) for p in patterns
               if r"\b" in p]
    allowlist = load_allowlist()
    exempt = stamped_dirs(root)
    findings = []
    for path in candidate_files(root):
        if not path.is_file() or is_exempt(path, root, exempt):
            continue
        rel = path.relative_to(root).as_posix()
        if str(rel) in {"scripts/check_sanitization.py",
                        "scripts/sanitization-allowlist.json"}:
            continue  # the gate and its allowlist ARE the lists; exempt from
                      # their own scan by declaration (quoted patterns would
                      # otherwise self-detect)
        # filename pass
        for p, rx in compiled:
            if rx.search(str(rel)):
                row = allowed(allowlist, rel, p, path)
                if not row:
                    findings.append((str(rel), 0, p, "FILENAME"))
        if not looks_like_text(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for p, rx in compiled:
                if rx.search(line):
                    if not allowed(allowlist, rel, p, path):
                        findings.append((str(rel), i, p, line.strip()[:90]))
            else:
                continue
        # no-boundary identifier pass (snake_case embeds the \b pass misses)
        for p, rx in nobound:
            core = p.replace(r"\b", "")
            for m in re.finditer(re.escape(core), text, re.I):
                before = text[m.start() - 1] if m.start() else ""
                after = text[m.end()] if m.end() < len(text) else ""
                # whole identifier segments only: "archimedean_spiral" is
                # not an embed of "spira" (the match continues into a word)
                if (before in ("", "_") and after in ("", "_")) \
                        and (before == "_" or after == "_"):
                    if not allowed(allowlist, rel, p, path):
                        frag = text[max(0, m.start() - 30):m.end() + 30].replace("\n", " ")
                        findings.append((str(rel), 0, p + " [nobound]", frag[:90]))
                        break
    findings.extend(staged_findings(root, compiled))
    seen = set()
    for rel, line, p, ctx in findings:
        key = (rel, p)
        if key in seen:
            continue
        seen.add(key)
        print(f"finding: [{p}] {rel}:{line}: {ctx}")
    print(f"sanitization ({profile}): {len(seen)} finding group(s), "
          f"{len(findings)} raw hit(s); exempt: "
          + ", ".join(sorted({str(d.relative_to(root)) for d in exempt}) or "-"))
    return 1 if findings else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check candidates for identity and Windows path issues.")
    parser.add_argument("profile", choices=("desk", "buntas"), nargs="?", default="desk")
    parser.add_argument("target", type=Path, nargs="?", default=ROOT)
    parser.add_argument("--paths-only", action="store_true")
    parser.add_argument("--tree", help="Check Windows paths in this Git revision")
    args = parser.parse_args()
    if args.tree is not None and not args.paths_only:
        parser.error("--tree requires --paths-only")
    root = args.target.resolve()
    if not root.is_dir():
        parser.error("target must be a directory")
    if args.paths_only:
        return check_windows_paths(root, args.tree)
    return run(args.profile, root)


if __name__ == "__main__":
    sys.exit(main())
