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

Checks: file CONTENT (case-insensitive, word-boundary patterns plus a
no-boundary pass for whole snake_case identifier segments) and FILE NAMES
(the published surface). This script is exempt from its own scan by
declaration: it IS the token list, and copying the list into other artifacts
is exactly what the floor forbids. Exit 0 clean, 1 findings, 2 usage error.
Pure standard library.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

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

DESK_FORBIDDEN = ESTATE + PERSONAL + PERSONA + [r"\bseats?\b"]
BUNTAS_FORBIDDEN = ESTATE + PERSONAL + [
    r"the-pgh-cid", r"\bclaude\b", r"\banthropic\b", r"\bfable\b",
]

TEXT_SUFFIXES = {
    ".md", ".markdown", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".conf", ".py", ".r", ".R", ".sh", ".sql", ".sas",
    ".js", ".ts", ".html", ".css", ".xml", ".csv", ".tsv", ".thrift",
    ".bat", ".ps1",
}
SKIP_DIRS = {".git", ".github", "__pycache__", ".venv", "venv",
             "node_modules", "dist", "build"}


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


def run(profile: str, root: Path) -> int:
    if profile == "desk":
        patterns = DESK_FORBIDDEN
    elif profile == "buntas":
        patterns = BUNTAS_FORBIDDEN
    else:
        print(f"error: unknown profile {profile!r}", file=sys.stderr)
        return 2
    compiled = [(p, re.compile(p, re.I)) for p in patterns]
    nobound = [(p, re.compile(p.replace(r"\b", ""), re.I)) for p in patterns
               if r"\b" in p]
    allowlist = load_allowlist()
    exempt = stamped_dirs(root)
    findings = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or is_exempt(path, root, exempt):
            continue
        rel = path.relative_to(root)
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
        if path.suffix not in TEXT_SUFFIXES:
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
    profile = sys.argv[1] if len(sys.argv) > 1 else "desk"
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT
    if profile.startswith("-"):
        print("check_sanitization.py : the token gate for the sanitization floor.")
        print("usage: check_sanitization.py [desk|buntas] [target_dir]")
        return 2
    return run(profile, target.resolve())


if __name__ == "__main__":
    sys.exit(main())
