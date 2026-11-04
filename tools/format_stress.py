#!/usr/bin/env python3
"""Seeded FORMAT diagnostics; supplemental evidence, never a replacement gate.

Only case identities, counts and hashes persist. Complete postal-derived results
remain in memory or the external scratch used by the independent R witnesses.
"""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import date, timedelta
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import random
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'examples')]
from format_gate_common import witness
from verify_vendor_sorted_copy import ordered_equal
from saschi.emit_py import translate
from saschi.plan import compile_plan
from saschi.runtime import run_plan
from saschi.provenance import source_state

PROFILES = ('date_profile', 'picture_dates', 'groupformat', 'numeric_pictures',
            'week_callbacks', 'postal_function')
MONTHS = ('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP',
          'OCT', 'NOV', 'DEC')


def day(rng):
    value = date(1800, 1, 1) + timedelta(days=rng.randrange(146097))
    return f'{value.day:02}{MONTHS[value.month-1]}{value.year:04}'


def records(profile, n, rng):
    if profile == 'date_profile':
        return [f'{i} F {rng.randint(-100, 100)} {day(rng)} {day(rng)}'
                for i in range(n)]
    if profile == 'picture_dates':
        return [f'P{i} {day(rng)} {i}' for i in range(n)]
    if profile == 'groupformat':
        wages = sorted(rng.choices(range(0, 31), k=n))
        return [f'{i} {w} {day(rng)}' for i, w in enumerate(wages)]
    if profile == 'numeric_pictures':
        return [f'{rng.randint(-999, 999)} ABC' for _ in range(n)]
    if profile == 'week_callbacks':
        return [f'{10 + i // 12} {day(rng)} {i}' for i in range(n)]
    # Original synthetic records, including commas and escaped quotes. These
    # deliberately vary country casing and equal-key input order before SORT.
    places = [('au', '0200'), ('AU', '0299'), ('AU', '0800'), ('au', '0999'),
              ('AU', '1000'), ('AU', '1999'), ('AU', '8000'), ('au', '8999'),
              ('US', '01040'), ('us', '27511'), ('ZZ', '00000')]
    result = []
    for i in range(n):
        country, postal = rng.choice(places)
        result.append(f'{i},"Person, ""{i}""",Place,{postal},{country}')
    return result


def replace_records(source, rows):
    match = re.search(r'(?im)^ *(?:cards|datalines);\r?\n', source)
    if match is None:
        raise ValueError('diagnostic source needs one input payload')
    tail = source[match.end():]
    end = re.search(r'(?m)^;\r?\n', tail)
    if end is None:
        raise ValueError('diagnostic source needs a payload terminator')
    return source[:match.end()] + ''.join(row + '\n' for row in rows) + tail[end.start():]


def mutations(plan):
    """Single-defect portable plans, each outside an explicit shape contract."""
    for key, value in [('version', True), ('steps', ()), ('tickets', [{}]),
                       ('matched', 'not a route list')]:
        changed = deepcopy(plan)
        changed[key] = value
        yield f'root-{key}', changed
    for i, step in enumerate(plan['steps']):
        if step['kind'] == 'report_title':
            continue
        for key, value in [('line', True), ('where', 'unqualified'),
                           ('nodupkey', True), ('operations', []),
                           ('unexpected', 1)]:
            changed = deepcopy(plan)
            changed['steps'][i][key] = value
            yield f'step-{i}-{key}', changed
        for key, value in [('profile', 'unqualified'), ('unexpected', 1),
                           ('source_lines', [0])]:
            changed = deepcopy(plan)
            changed['steps'][i]['operations'][0]['args'][key] = value
            yield f'args-{i}-{key}', changed

    def leaves(value, path=()):
        if type(value) is dict:
            for key, item in value.items():
                yield from leaves(item, (*path, key))
        elif type(value) is list:
            for index, item in enumerate(value):
                yield from leaves(item, (*path, index))
        elif type(value) in (str, int, float, bool) or value is None:
            yield path

    # A container cannot stand in for a scalar at any admitted Step field.
    # Empty dicts/lists that are valid defaults are not scalar leaves.
    for path in leaves(plan['steps']):
        for kind, replacement in [('list', ['unqualified']), ('map', {'unqualified': 1})]:
            changed = deepcopy(plan)
            parent = changed['steps']
            for key in path[:-1]:
                parent = parent[key]
            parent[path[-1]] = replacement
            yield 'scalar-' + '/'.join(map(str, path)) + '-' + kind, changed


def campaign(seed, variants, destination):
    from saschi.postal_reference import load_reference, reference_path
    load_reference()
    os.environ['SASCHI_POSTAL_REFERENCE'] = str(reference_path())
    rng = random.Random(seed)
    before = source_state(ROOT)
    results = []
    started = time.monotonic()

    def save(completed):
        after = source_state(ROOT)
        report = {'status': 'Supplemental seeded repository/base-R diagnostics for maintainer review; no native SAS or new capability admission.',
                  'completed': completed, 'seed': seed, 'variants_per_profile': variants,
                  'source_before': before, 'source_after': after,
                  'source_stable': before['source_sha256'] == after['source_sha256'],
                  'elapsed_seconds': round(time.monotonic()-started, 3),
                  'cases': results, 'passed': sum(r['passed'] for r in results),
                  'failed': sum(not r['passed'] for r in results), 'human_sessions': 0}
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + '\n')
        return report

    def record(case, operation):
        try:
            details = operation() or {}
            results.append({'case': case, 'passed': True, **details})
        except Exception as exc:
            # Avoid serializing assertion payloads or subprocess stderr that
            # may contain complete reference-derived results.
            results.append({'case': case, 'passed': False,
                            'exception': type(exc).__name__})

    for profile in PROFILES:
        original = (ROOT / 'examples' / (profile + '.sas')).read_text()
        script = profile + '.R'
        maximum = 500 if profile == 'groupformat' else 1000
        sizes = [0, 1, 2, 10, 31, 100, maximum]
        sizes += [rng.randrange(1, maximum+1) for _ in range(max(0, variants-len(sizes)))]
        sources = [('original', original)]
        sources.extend((f'rows-{n}-case-{i}', replace_records(original, records(profile, n, rng)))
                       for i, n in enumerate(sizes[:variants]))
        for label, source in sources:
            def compare(source=source):
                # Qualify an independently authored R witness before asking
                # the translator for output. Agreement remains diagnostic.
                if profile == 'date_profile':
                    from verify_date_profile import witness as date_witness
                    expected, _ = date_witness(source)
                else:
                    expected, _, _ = witness(source, script)
                parsed = compile_plan(source)
                if parsed.blocked:
                    raise AssertionError('generated valid source refused')
                actual = run_plan(parsed.to_dict())
                if not ordered_equal(actual, expected):
                    raise AssertionError('runtime disagrees with independent R')
                emitted = translate(source)
                if emitted.blocked:
                    raise AssertionError('emitter refused valid source')
                namespace = {}
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exec(compile(emitted.code, '<format-stress>', 'exec'), namespace)
                if stdout.getvalue() or not ordered_equal(namespace['result'], expected):
                    raise AssertionError('emitted result disagrees with independent R')
                return {'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                        'rows': sum(len(t['rows']) for t in actual['datasets'].values()),
                        'reports': len(actual.get('reports', {}))}
            record(f'{profile}/R-runtime-emitted/{label}', compare)

        baseline = compile_plan(original).to_dict()
        oversized = replace_records(original, records(profile, maximum+1, rng))
        def refuse_source():
            if not compile_plan(oversized).blocked:
                raise AssertionError('source over its declared row bound was accepted')
        record(f'{profile}/source-refusal/row-bound-plus-one', refuse_source)
        for label, value in mutations(baseline):
            def refuse(value=value):
                try:
                    run_plan(value)
                except ValueError:
                    return
                except RuntimeError:
                    if value['tickets']:
                        return
                    raise
                raise AssertionError('malformed plan did not refuse cleanly')
            record(f'{profile}/portable-refusal/{label}', refuse)

        expected = run_plan(baseline)
        for label, changed in [('crlf', original.replace('\n', '\r\n')),
                               ('prefix-comment', '/* diagnostic */\n' + original),
                               ('suffix-comment', original + '\n/* diagnostic */\n'),
                               ('leading-lines', '\n\n' + original)]:
            def invariant(changed=changed):
                parsed = compile_plan(changed)
                if parsed.blocked or not ordered_equal(run_plan(parsed.to_dict()), expected):
                    raise AssertionError('source envelope changed the result')
            record(f'{profile}/source-invariance/{label}', invariant)
        print(json.dumps({'profile': profile, 'completed': len(results),
                          'failures': sum(not r['passed'] for r in results)}), flush=True)
        save(False)

    report = save(True)
    print(json.dumps({k: report[k] for k in ('seed', 'passed', 'failed', 'elapsed_seconds')}))
    return int(report['failed'] != 0 or not report['source_stable'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=20261103)
    parser.add_argument('--variants', type=int, choices=range(1, 65), default=16)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    raise SystemExit(campaign(options.seed, options.variants, options.output))
