#!/usr/bin/env python3
"""verify_capability.py : the capability manifest gate.

The manifest is a coverage claim, and a coverage claim that nothing checks is a
brochure. This gate is what makes it a claim instead of prose.

It asserts nine things, all of them mechanical:

1. The manifest exists and parses.
2. Every entry names a document declared in the reference frame.
3. Every entry carries a disposition from the declared vocabulary.
4. Every GATED entry names at least one gate, and every named gate is a verifier
   registered in verify_all.py. A GATED entry that names a gate nobody runs is
   the exact failure this repository forbids elsewhere.
5. Every RULE entry names at least one rule id that exists in the shipped
   rulebook. A rule reference that does not resolve is a dangling claim.
6. Every entry's document count matches the document's declared universe. A
   document that declares 108 entries and carries 90 has lost 18 silently.
7. No entry is missing a required field or duplicates a document/name pair.
8. GATED evidence declares a bounded scope and separates reference fixtures
   from source execution. Related evidence cannot satisfy a GATED claim.
9. Recorded rollups agree with the entries, including unassessed entries.

Standard library only, and it reads files by path relative to its own location,
so a copy of the tree is checked as a copy. Nothing here imports the package.

Exit 0 when every assertion holds. Exit 1 with a FAIL line naming the class of
failure otherwise.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MANIFEST = ROOT / "docs" / "capability-manifest.json"
RULEBOOK = ROOT / "docs" / "sasconversionrulebook.json"
VERIFY_ALL = ROOT / "verify_all.py"

REQUIRED_FIELDS = ("entry", "document", "disposition")


def registered_gate_names() -> set[str]:
    """Gate names from verify_all.py, read as text.

    Both registries count. verify_all.py's own comment states that a translator
    suite "carries the same weight as a fixture gate in the verdict", so a
    manifest entry proven by a suite is proven.

    Read as text rather than imported: an import would resolve through an
    editable install to the installed tree and defeat a check run against a
    copy.
    """
    text = VERIFY_ALL.read_text(encoding="utf-8")
    names: set[str] = set()
    for registry in ("VERIFIERS = [", "SUITES = ["):
        block = text.split(registry, 1)
        if len(block) != 2:
            continue
        body = block[1].split("]", 1)[0]
        names.update(re.findall(r'\(\s*"([^"]+)"\s*,', body))
    return names


def rulebook_ids() -> set[str]:
    doc = json.loads(RULEBOOK.read_text(encoding="utf-8"))
    return {r["rule_id"] for r in doc.get("rules", [])}


def main() -> int:
    problems: list[str] = []

    if not MANIFEST.exists():
        print(f"FAIL: capability manifest not found at {MANIFEST}")
        return 1
    try:
        man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL: capability manifest is not valid JSON: {exc}")
        return 1

    frame = man.get("reference_frame", {})
    documents = {d["id"]: d for d in frame.get("documents", [])}
    vocabulary = set(man.get("dispositions", []))
    entries = man.get("entries", [])

    if not documents:
        problems.append("reference frame declares no documents")
    if not vocabulary:
        problems.append("no disposition vocabulary declared")

    # 7. required fields
    seen = set()
    for e in entries:
        for f in REQUIRED_FIELDS:
            if not e.get(f):
                problems.append(f"entry {e.get('entry', '?')!r} is missing required field {f!r}")
        key = (e.get('document'), e.get('entry'))
        if key in seen:
            problems.append(f"duplicate document/entry pair {key!r}")
        seen.add(key)

    # 2 and 3
    for e in entries:
        if e.get("document") not in documents:
            problems.append(f"entry {e['entry']!r} names undeclared document {e.get('document')!r}")
        if e.get("disposition") not in vocabulary:
            problems.append(f"entry {e['entry']!r} carries undeclared disposition {e.get('disposition')!r}")

    # 6. per-document counts against the declared universe
    counts: dict[str, int] = {}
    for e in entries:
        counts[e.get("document", "")] = counts.get(e.get("document", ""), 0) + 1
    for did, doc in documents.items():
        declared = doc.get("universe")
        actual = counts.get(did, 0)
        if declared is None:
            if actual:
                problems.append(f"document {did!r} declares a null universe but carries {actual} entries")
        elif declared != actual:
            problems.append(f"document {did!r} declares {declared} entries but carries {actual}")

    # 4. GATED entries name gates that actually run
    gates = registered_gate_names()
    if not gates:
        problems.append("could not read the VERIFIERS list from verify_all.py")
    for e in entries:
        if e.get("disposition") != "GATED":
            continue
        named = e.get("gates") or []
        if not named:
            problems.append(f"GATED entry {e['entry']!r} names no gate")
            continue
        for g in named:
            if g not in gates:
                problems.append(f"GATED entry {e['entry']!r} names gate {g!r}, which is not registered in verify_all.py")

        # A registered name proves existence, not the scope of the claim.
        evidence = e.get('gate_evidence') or []
        covered = set()
        for item in evidence:
            if item.get('level') not in {'reference-fixture', 'source-execution'}:
                problems.append(f"GATED entry {e['entry']!r} has an invalid evidence level")
            if not isinstance(item.get('scope'), str) or not item['scope'].strip():
                problems.append(f"GATED entry {e['entry']!r} lacks an evidence scope")
            if not item.get('gates'):
                problems.append(f"GATED entry {e['entry']!r} has evidence without gates")
            covered.update(item.get('gates') or [])
        if not evidence or covered != set(named):
            problems.append(f"GATED entry {e['entry']!r} evidence does not cover exactly its named gates")

    # Related evidence remains resolvable, but cannot promote a disposition.
    for e in entries:
        for g in e.get('related_evidence', {}).get('gates', []):
            if g not in gates:
                problems.append(f"entry {e['entry']!r} has unregistered related gate {g!r}")

    # 5. RULE entries name rule ids that resolve
    ids = rulebook_ids()
    if not ids:
        problems.append("could not read any rule ids from the shipped rulebook")
    for e in entries:
        named = e.get("rule_ids") or []
        if e.get("disposition") == "RULE" and not named:
            problems.append(f"RULE entry {e['entry']!r} names no rule id")
            continue
        for rid in named:
            if rid not in ids:
                problems.append(f"entry {e['entry']!r} names rule {rid!r}, which is not in the shipped rulebook")

    # 9. Materialized summary counts must be derived from the same entries.
    fields = {'gated': 'GATED', 'rule': 'RULE', 'human_review': 'HUMAN-REVIEW',
              'out_of_scope': 'OUT-OF-SCOPE', 'unassessed': 'UNASSESSED'}
    for did, document in documents.items():
        if document.get('universe') is None:
            continue
        subset = [e for e in entries if e.get('document') == did]
        expected = {field: sum(e.get('disposition') == label for e in subset)
                    for field, label in fields.items()}
        expected.update(universe=len(subset), assessed=sum(
            e.get('disposition') != 'UNASSESSED' for e in subset))
        actual = man.get('rollup', {}).get(did, {})
        for field, count in expected.items():
            if actual.get(field) != count:
                problems.append(f"document {did!r} rollup {field!r}: expected {count}, got {actual.get(field)!r}")

    if problems:
        print(f"FAIL: {len(problems)} manifest problem(s)")
        for p in problems[:40]:
            print(f"  - {p}")
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more")
        return 1

    enumerated = sum(1 for d in documents.values() if d.get("universe") is not None)
    total = sum(d.get("universe") or 0 for d in documents.values())
    assessed = sum(1 for e in entries if e.get("disposition") != "UNASSESSED")
    print(f"PASS: {len(entries)} entries across {enumerated} of {len(documents)} documents; "
          f"{assessed} assessed, {total - assessed} unassessed in the enumerated set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
