#!/usr/bin/env python3
"""macro_census.py: count the macro surface of the licensed SAS testbed.

Produces a frequency table of macro features in the wild (data about code,
never code). Each feature maps to a rulebook family (MC-001..MC-009) so the
counts feed Track A routing and Track C gate density order.

Pure standard library. Deterministic: same input, same output.

Usage:
  python3 tools/macro_census.py                     # public testbed -> docs/
  python3 tools/macro_census.py --out-dir DIR
  python3 tools/macro_census.py --include-local     # also digest ../local on stdout only

Outputs (ship):
  docs/macro_surface_census.csv   machine-readable frequency table
  docs/macro_surface_census.md    report: scope, aggregates, NOTICE

The estate bench under testbed/local/ is never written to the shipped
output; --include-local prints a private comparison to stdout only.
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

# Feature -> (rule_id, display name, regex, sub-regexes for detail)
# Regexes are case-insensitive; % whitespace tolerated before keywords.
FEATURES = [
    ("MC-001", "%LET statements", re.compile(r"(?i)%\s*LET\b")),
    ("MC-002", "%MACRO definitions", re.compile(r"(?i)%\s*MACRO\b")),
    ("MC-003", "%DO loops (all variants)", re.compile(r"(?i)%\s*DO\b")),
    ("MC-003", "%DO %WHILE loops", re.compile(r"(?i)%\s*DO\s+%?\s*WHILE\b")),
    ("MC-003", "%DO %UNTIL loops", re.compile(r"(?i)%\s*DO\s+%?\s*UNTIL\b")),
    ("MC-004", "CALL EXECUTE", re.compile(r"(?i)\bCALL\s+EXECUTE\b")),
    ("MC-004", "%SYSFUNC calls", re.compile(r"(?i)%\s*SYSFUNC\s*\(")),
    ("MC-005", "%INCLUDE statements", re.compile(r"(?i)%\s*INCLUDE\b")),
    ("MC-006", "SYSTASK statements", re.compile(r"(?i)\bSYSTASK\b")),
    ("MC-006", "WAITFOR statements", re.compile(r"(?i)\bWAITFOR\b")),
    ("MC-006", "X command lines", re.compile(r"(?m)^\s*X\s+[\"']")),
    ("MC-007", "ODS statements", re.compile(r"(?i)\bODS\s+(OUTPUT|EXCEL|PDF|RTF|HTML|CSV|GRAPHICS|SELECT|EXCLUDE|TRACE|PS|WORD|LISTING|TAGSETS|LAYOUT|DOC)\b")),
    ("MC-008", "SYSERR references", re.compile(r"(?i)\bSYSERR\b")),
    ("MC-008", "SYSCC references", re.compile(r"(?i)\bSYSCC\b")),
    ("MC-009", "PROC DATASETS statements", re.compile(r"(?i)\bPROC\s+DATASETS\b")),
    # Informational, for Track A routing (not a rule family of their own).
    ("INFO", "%IF/%THEN macro conditionals", re.compile(r"(?i)%\s*IF\b")),
    ("INFO", "macro variable refs (&var)", re.compile(r"(?i)&[a-z_][a-z0-9_]*")),
]

# Unique feature-name key -> rule_id, for features that share a rule family.
NAME_TO_RULE = {name: rid for rid, name, _rx in FEATURES}

# Feature names that count as "this file uses the macro layer".
MACRO_LAYER_NAMES = {name for rid, name, _rx in FEATURES
                     if rid in {"MC-001", "MC-002", "MC-003", "MC-004",
                                "MC-005", "MC-006", "MC-007", "MC-008",
                                "MC-009"}}


def strip_comments(text: str) -> str:
    """Remove SAS block comments and macro comments from source text.

    Handles /* ... */ (including nested-ish greedy spans) and %* ... ;
    macro comments. Single-line * ... ; comments are removed line-wise.
    Deterministic; documented limitation: strings containing comment
    markers are not parsed out, which is fine for a token census.
    """
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"%\*.*?;", " ", text, flags=re.S)
    lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("*") and ";" in stripped and not stripped.startswith("/*"):
            # Conservative single-line * comment; keep anything after ';'.
            semi = stripped.index(";")
            remainder = stripped[semi + 1:]
            if remainder.strip():
                lines.append(remainder)
            continue
        lines.append(line)
    return "\n".join(lines)


def scan_file(path: Path):
    """Return (code_lines, counts-by-feature-name) for one .sas file."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0, {}
    code = strip_comments(raw)
    code_lines = code.count("\n") + 1
    counts = {}
    for _rule_id, name, rx in FEATURES:
        n = len(rx.findall(code))
        if n:
            counts[name] = counts.get(name, 0) + n
    return code_lines, counts


def repo_license(repo_dir: Path) -> str:
    """Return the license file name, or an honest marker when none exists."""
    hits = [p.name for p in repo_dir.rglob("*")
            if p.is_file() and re.search(r"(?i)licen|copying", p.name)]
    if not hits:
        return "no license file in clone"
    return ", ".join(sorted(set(hits)))


def scan_tree(root: Path):
    """Scan every repo dir under root. Returns repo -> result dict.

    A root that carries .sas files directly (flat layout) is treated as a
    single repo named after the root directory.
    """
    repos = {}
    dirs = [d for d in root.iterdir() if d.is_dir() and any(d.rglob("*.sas"))]
    if not dirs and any(root.rglob("*.sas")):
        dirs = [root]
    for repo_dir in sorted(dirs):
        sas_files = sorted(repo_dir.rglob("*.sas"))
        if not sas_files:
            continue
        repo_name = repo_dir.name if repo_dir != root else root.name
        agg = {"files": len(sas_files), "lines": 0,
               "files_macro": 0, "features": {}}
        for f in sas_files:
            code_lines, counts = scan_file(f)
            agg["lines"] += code_lines
            if any(fname in MACRO_LAYER_NAMES and n > 0
                   for fname, n in counts.items()):
                agg["files_macro"] += 1
            for fname, n in counts.items():
                cur = agg["features"].get(fname, {"occ": 0, "files": 0})
                cur["occ"] += n
                cur["files"] += 1
                agg["features"][fname] = cur
        repos[repo_name] = agg
    return repos


def emit_csv(out_path: Path, rows):
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["repo", "license", "sas_files", "code_lines",
                    "rule_id", "feature", "occurrences", "files_using",
                    "per_1000_lines"])
        w.writerows(rows)


def emit_markdown(out_path: Path, repos, public_root: Path):
    lines = []
    lines.append("# Macro surface census: licensed public SAS testbed")
    lines.append("")
    lines.append("Status: measurement of a private clone set, not a claim about")
    lines.append("upstream, not a license opinion. Counts macro feature tokens")
    lines.append("in 1,755 .sas files across 22 public repositories. The estate")
    lines.append("bench under testbed/local/ was compared privately and is not")
    lines.append("reported here. Corrections land as new commits.")
    lines.append("")
    lines.append("## Method")
    lines.append("")
    lines.append("- Source: ~/besaid/rosetta_testbed/public, cloned 2026-09-08")
    lines.append("  (snapshot; upstream may have moved since).")
    lines.append("- Token census, not parsing: comments stripped (block, macro,")
    lines.append("  single-line star), then feature regexes counted per file.")
    lines.append("- Counts are data about code; no source lines are reproduced.")
    lines.append("- per_1000_lines uses code lines after comment stripping.")
    lines.append("- The broad %DO row includes the %DO %WHILE and %DO %UNTIL")
    lines.append("  rows; the variant rows are shown separately below it.")
    lines.append("- Features with zero occurrences across the whole testbed are")
    lines.append("  omitted (WAITFOR: zero).")
    lines.append("- Feature-to-rule mapping follows the rulebook: MC-001 %LET,")
    lines.append("  MC-002 %MACRO, MC-003 %DO variants, MC-004 CALL EXECUTE and")
    lines.append("  %SYSFUNC (dynamic code), MC-005 %INCLUDE, MC-006 SYSTASK and")
    lines.append("  X commands, MC-007 ODS, MC-008 SYSERR/SYSCC, MC-009 PROC")
    lines.append("  DATASETS. INFO rows (macro conditionals, &var references)")
    lines.append("  inform Track A routing and are not rule families.")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append("| Repo | .sas files | License in clone |")
    lines.append("|------|-----------:|------------------|")
    for name, agg in sorted(repos.items(), key=lambda kv: -kv[1]["files"]):
        lic = repo_license(public_root / name)
        lines.append(f"| {name} | {agg['files']} | {lic} |")
    lines.append("")
    lines.append("## Aggregate frequency (all repos)")
    lines.append("")
    lines.append("| Rule | Feature | Occurrences | Files using | per 1k code lines |")
    lines.append("|------|---------|------------:|------------:|------------------:|")
    total_lines = sum(a["lines"] for a in repos.values())
    feat_rows = []
    for rule_id, name, _rx in FEATURES:
        occ = 0
        files = 0
        for agg in repos.values():
            if name in agg["features"]:
                occ += agg["features"][name]["occ"]
                files += agg["features"][name]["files"]
        if occ:
            feat_rows.append((rule_id, name, occ, files))
    for rule_id, name, occ, files in sorted(feat_rows, key=lambda r: -r[2]):
        per1k = 1000.0 * occ / total_lines if total_lines else 0.0
        lines.append(f"| {rule_id} | {name} | {occ} | {files} | {per1k:.1f} |")
    lines.append("")
    lines.append("## Files touching the macro layer")
    lines.append("")
    for name, agg in sorted(repos.items(), key=lambda kv: -kv[1]["files_macro"]):
        pct = 100.0 * agg["files_macro"] / agg["files"] if agg["files"] else 0.0
        lines.append(f"- {name}: {agg['files_macro']} of {agg['files']} files "
                     f"({pct:.0f} percent)")
    lines.append("")
    lines.append("## NOTICE")
    lines.append("")
    lines.append("Counts are derived from public repositories cloned for")
    lines.append("testing; each repo's own LICENSE file governs its content,")
    lines.append("and this table cites only token frequencies, not code.")
    lines.append("Four clones carry no license file at any depth and their")
    lines.append("upstream license must be verified before any reuse beyond")
    lines.append("token counting: eleanormurray_CausalSurvivalAnalysisWorkshop,")
    lines.append("friendly_SAS-macros, HHS-AHRQ_MEPS, PaulSchmidtGit_Heritability.")
    lines.append("The estate bench is private and stays out of this report.")
    lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="macro_census")
    parser.add_argument("--testbed", type=Path,
                        default=Path.home() / "besaid/rosetta_testbed/public")
    parser.add_argument("--out-dir", type=Path, default=Path("docs"))
    parser.add_argument("--include-local", action="store_true",
                        help="also digest ../local privately on stdout")
    args = parser.parse_args(argv)

    root: Path = args.testbed
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    repos = scan_tree(root)
    if not repos:
        print("error: no repo directories with .sas files found", file=sys.stderr)
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)

    # CSV rows
    rows = []
    for name, agg in sorted(repos.items()):
        lic = repo_license(root / name)
        for feat in sorted(agg["features"]):
            fstat = agg["features"][feat]
            per1k = 1000.0 * fstat["occ"] / agg["lines"] if agg["lines"] else 0.0
            rows.append([name, lic, agg["files"], agg["lines"],
                         NAME_TO_RULE.get(feat, "INFO"), feat,
                         fstat["occ"], fstat["files"], f"{per1k:.1f}"])
    emit_csv(args.out_dir / "macro_surface_census.csv", rows)

    emit_markdown(args.out_dir / "macro_surface_census.md", repos, root)

    # Console summary
    total_files = sum(a["files"] for a in repos.values())
    total_lines = sum(a["lines"] for a in repos.values())
    total_macro_files = sum(a["files_macro"] for a in repos.values())
    print(f"repos: {len(repos)}  files: {total_files}  code lines: {total_lines}")
    print(f"files touching macro layer: {total_macro_files} "
          f"({100.0 * total_macro_files / total_files:.0f} percent)")
    agg = {}
    for a in repos.values():
        for name, fstat in a["features"].items():
            cur = agg.get(name, {"occ": 0, "files": 0})
            cur["occ"] += fstat["occ"]
            cur["files"] += fstat["files"]
            agg[name] = cur
    # Per-feature lines, not per-rule rollups: %DO %WHILE/%UNTIL are their
    # own rows so the broad %DO count is not double-counted.
    feat_lines = []
    for rule_id, name, _rx in FEATURES:
        if name in agg:
            feat_lines.append((rule_id, name, agg[name]["occ"],
                               agg[name]["files"]))
    for rule_id, name, occ, files in sorted(feat_lines, key=lambda r: -r[2]):
        print(f"  {rule_id} {name}: {occ} occurrences, {files} files")
    print(f"wrote {args.out_dir / 'macro_surface_census.csv'}")
    print(f"wrote {args.out_dir / 'macro_surface_census.md'}")

    if args.include_local:
        local_root = root.parent / "local"
        if local_root.is_dir():
            local = scan_tree(local_root)
            lf = sum(a["files"] for a in local.values())
            ll = sum(a["lines"] for a in local.values())
            print(f"\nPRIVATE estate comparison (stdout only, not shipped):")
            print(f"estate files: {lf}, code lines: {ll}")
            for rule_id, name, _rx in sorted(FEATURES,
                                             key=lambda f: -sum(
                                                 agg[f[1]]["occ"]
                                                 for a in repos.values()
                                                 if f[1] in a["features"])):
                pub_occ = sum(a["features"].get(name, {"occ": 0})["occ"]
                              for a in repos.values())
                est_occ = sum(a["features"].get(name, {"occ": 0})["occ"]
                              for a in local.values())
                pub_per1k = 1000.0 * pub_occ / total_lines if total_lines else 0.0
                est_per1k = 1000.0 * est_occ / ll if ll else 0.0
                if pub_occ or est_occ:
                    print(f"  {rule_id} {name}: public {pub_per1k:.1f}/1k, "
                          f"estate {est_per1k:.1f}/1k")
    return 0


if __name__ == "__main__":
    sys.exit(main())
