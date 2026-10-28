#!/usr/bin/env python3
"""Reproduce gate counts and classify corpus diagnostics without copying source.

The classifier is an analyst heuristic for planning, not SAS interpretation.
It preserves every compiler ticket with a stable ordinal and statement hash.
Procedure/macro ownership groups cascading diagnostics under their enclosing
feature. No diagnostics are removed and no compile result is promoted to proof.
Run from a source checkout with --corpus, --receipt and --output paths.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from saschi.parser import Kind, split_statements
from saschi.plan import compile_plan
from saschi.provenance import source_state
from saschi.rules import family_counts, load_rulebook
from verify_all import SUITES, VERIFIERS


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def ownership(source):
    """Lexical ownership, deliberately independent of compiler acceptance."""
    result, proc, macro = {}, None, False
    for st in split_statements(source):
        unquoted = ' '.join(t.text for t in st.tokens if t.kind != Kind.STRING)
        low = unquoted.lower()
        if re.search(r'%macro\b', low):
            macro = True
        match = re.match(r'proc\s+(\w+)', low)
        if match:
            proc = match[1]
        # DS2 can contain DATA blocks after RUN, until the procedure ends.
        if re.match(r'data\b', low) and proc != 'ds2':
            proc = None
        result[(st.line, st.text)] = (proc, macro, low)
        if re.search(r'%mend\b', low):
            macro = False
        if low == 'quit' or low == 'run' and proc != 'ds2':
            proc = None
    return result


def classify(filename, ticket, owner):
    """Return a primary family and the evidence used for that judgment."""
    proc, macro, text = owner.get((ticket.line, ticket.statement), (None, False, ticket.statement.lower()))
    if ((filename == 'palindrome_detection.sas' and ticket.line in (8, 46, 54)) or
            filename == 'strip_a_set_of_characters_from_a_string.sas' and ticket.line == 15):
        return 'corpus-quality', 'Reviewed prose/printed output embedded as executable input'
    if proc:
        return 'procedure:' + proc, 'Lexical enclosing PROC, including downstream clause diagnostics'
    if macro or re.search(r'%[a-z_]|&[a-z_]', text):
        return 'macro', 'Lexical macro body, invocation or unresolved macro reference'
    if ticket.statement.startswith('<inline-data>') or re.match(r'(input|infile|cards|datalines)\b', text):
        return 'input-records', 'Inline/external record ingestion statement or opaque payload'
    if re.match(r'array\b', text) or re.match(r'\w+\s*[({\[][^=]*[)}\]]\s*=', text):
        return 'arrays', 'Array declaration or indexed assignment'
    if re.match(r'(keep|drop)\b', text):
        return 'projection', 'Output variable projection statement'
    if re.match(r'(file|filename)\b', text):
        return 'external-io', 'FILE/FILENAME destination, including email engine'
    if re.match(r'(goto|link|return|stop)\b|\w+\s*:', text):
        return 'unstructured-control', 'Label, GOTO/LINK/RETURN or STOP'
    if re.match(r'call\b', text):
        return 'call-side-effects', 'CALL routine needs its own state/side-effect contract'
    if re.match(r'(attrib|label|format|informat|options|title)\b', text):
        return 'descriptor-environment', 'Declaration, display or environment setting'
    if ticket.construct == 'unknown':
        if ticket.reason == 'statement is outside a supported step':
            return 'step-context-cascade', 'Downstream diagnostic after rejected DATA header/options'
        return 'needs-triage', 'Unclassified diagnostic, must be reviewed before ranking'
    if ticket.construct in ('do-counted', 'do-if', 'do-until', 'do-while', 'do-over', 'if'):
        return 'control-composition', 'Rejected control form/action or cascading closure'
    if ticket.construct == 'put' or ticket.construct.startswith('put-'):
        return 'output-profile', 'Output typing, formatting or item profile'
    if ticket.construct in ('assignment', 'sum-func', 'sum-statement', 'int', 'mod-int', 'substr'):
        return 'expression-profile', 'Unsupported numeric/character expression or function composition'
    return 'other-routed:' + ticket.construct, 'Existing named compiler route'


def inventory_bucket(entry):
    """Planning bins do not change dispositions or close the reference scope."""
    name = entry['entry']
    if entry['document'] == 'dso':
        return 'data-set-option-contracts'
    if re.match(r'(INPUT|INFILE|INFORMAT|CARDS|DATALINES|LOSTCARD)', name):
        return 'input-records'
    if re.match(r'(KEEP|DROP|RENAME)', name):
        return 'projection'
    if re.match(r'(DO |CONTINUE|LEAVE|GOTO|Label:|LINK|RETURN|STOP|SELECT)', name):
        return 'control-composition'
    if re.match(r'(PUT |PUTLOG|PAGE|SKIP|LIST |RESETLINE)', name):
        return 'output-profile'
    if re.match(r'(ATTRIB|LABEL|OPTIONS|TITLE|FOOTNOTE)', name):
        return 'descriptor-environment'
    if re.match(r'(FILENAME|FILE |LIBNAME|CATNAME|SASFILE|X |LOCK|DM |DISPLAY|WINDOW|SYSECHO)', name):
        return 'external-environment-review'
    return 'separate-scope-review'


def build(corpus, receipt_path):
    before = source_state(ROOT)
    receipt_raw = receipt_path.read_bytes()
    receipt = json.loads(receipt_raw)
    if not receipt['all_passed'] or not receipt['source_stable']:
        raise ValueError('a successful stable-source verification receipt is required')
    proofs, tests = set(), 0
    for check in receipt['constructs']:
        if check['kind'] == 'suite':
            tests += int(re.search(r'Ran (\d+) tests?', check['stdout'] + '\n' + check['stderr'])[1])
        proofs.update(re.findall(r'^VERIFIED corpus: ([^;]+);', check['stdout'], re.M))
    files, primary, unknown, routed = [], Counter(), Counter(), Counter()
    for path in sorted(corpus.glob('*.sas')):
        raw = path.read_bytes()
        source = raw.decode('utf-8')
        plan = compile_plan(source)
        owners = ownership(source)
        rows = []
        for ordinal, ticket in enumerate(plan.tickets):
            category, basis = classify(path.name, ticket, owners)
            primary[category] += 1
            routed[ticket.construct] += 1
            if ticket.construct == 'unknown':
                unknown[category] += 1
            # Never serialize external code or inline record values.
            rows.append({'ordinal': ordinal, 'line': ticket.line,
                         'statement_sha256': digest(ticket.statement.encode()),
                         'construct': ticket.construct, 'reason': ticket.reason,
                         'category': category, 'basis': basis})
        files.append({'file': path.name, 'sha256': digest(raw),
                      'compile_clean': not plan.blocked,
                      'complete_program_proof_in_receipt': path.name in proofs,
                      'tickets': rows,
                      'categories': dict(sorted(Counter(r['category'] for r in rows).items()))})
    if not files:
        raise ValueError('empty corpus')
    clean = {f['file'] for f in files if f['compile_clean']}
    if not proofs <= clean:
        raise ValueError('receipt proof files are absent or no longer compile clean')
    after = source_state(ROOT)
    if before != after:
        raise ValueError('source changed during census')
    manifest = json.loads((ROOT / 'docs/capability-manifest.json').read_text())
    dispositions = Counter(e['disposition'] for e in manifest['entries'])
    evidence = Counter()
    for entry in manifest['entries']:
        if entry['disposition'] == 'GATED':
            levels = {e['level'] for e in entry['gate_evidence']}
            evidence['source-execution' if 'source-execution' in levels else 'reference-only'] += 1
    rules = load_rulebook()
    unassessed = [{'document': e['document'], 'entry': e['entry'],
                   'planning_bucket': inventory_bucket(e)} for e in manifest['entries']
                  if e['disposition'] == 'UNASSESSED']
    return {
        'status': 'Repository measurements and heuristic diagnostic classification for principal/maintainer planning. No live SAS, execution claim for compile-only files or whole-SAS coverage denominator.',
        'source': before, 'source_stable': True,
        'verification': {'receipt': str(receipt_path), 'sha256': digest(receipt_raw),
                         'git_commit': receipt['source']['git_commit'],
                         'current_source_files_match': before['files'] == receipt['source']['files'],
                         'unit_tests': tests, 'complete_program_proofs': sorted(proofs)},
        'registered': {'fixture_runners': len(VERIFIERS), 'suite_runners': len(SUITES),
                       'synthesis_runners': 1, 'rules': len(rules), 'rule_families': family_counts(rules)},
        'manifest': {'entries': len(manifest['entries']), 'dispositions': dict(sorted(dispositions.items())),
                     'gated_evidence': dict(evidence),
                     'unassessed_planning_buckets': dict(Counter(e['planning_bucket'] for e in unassessed)),
                     'unassessed_entries': unassessed,
                     'unenumerated_documents': [d['id'] for d in manifest['reference_frame']['documents'] if d['universe'] is None]},
        'corpus': {'files': len(files), 'compile_clean': len(clean), 'blocked': len(files)-len(clean),
                   'tickets': sum(primary.values()), 'unknown_tickets': sum(unknown.values()),
                   'routing_counts': dict(routed.most_common()), 'category_counts': dict(primary.most_common()),
                   'unknown_category_counts': dict(unknown.most_common()),
                   'compile_clean_without_proof': sorted(clean-proofs), 'programs': files},
        'classification_limits': [
            'Categories are explicit analyst heuristics, not automatic evidence of implementability.',
            'An enclosing PROC/macro category includes cascading tickets; occurrences are not distinct capabilities.',
            'Compile-clean inputs can still refuse at runtime or require unprovided input catalogues.',
            'A candidate program needs whole-file execution, descriptors, outputs and independent comparison before promotion.']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus', required=True, type=Path)
    p.add_argument('--receipt', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    report = build(args.corpus, args.receipt)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    c = report['corpus']
    print(json.dumps({k: c[k] for k in ('files', 'compile_clean', 'blocked', 'tickets', 'unknown_tickets', 'unknown_category_counts')}))
    return 1 if 'needs-triage' in c['category_counts'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
