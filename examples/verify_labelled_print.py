#!/usr/bin/env python3
"""Independent complete-source fixtures for labelled PRINT and default MEANS."""
from copy import deepcopy
from dataclasses import asdict
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from saschi.compare import equal
from saschi.emit_py import translate
from saschi.emit_cpp import translate as translate_cpp
from saschi.plan import compile_plan
from saschi.runtime import run_plan
from saschi.formatted_program import run_program
from saschi.job import build_job
from saschi import informat_reports

ORIGINAL = HERE / 'informat_reports_capture.sas'
SOURCE_PIN = '6e867e5fa35d4ba10a8809b64f6fd567ef5a16086f326ed57d3b13911cc75b6e'
RESULT_PIN = '373f01c18b24908407c44b73df966c8d985322eda4b93952f8f01eb57a0db75e'
TRACE_PIN = 'b51ae30a2a7cf4b914bf04829fe8686ca5ca0bf1fbfa402925eee1db3e6bf4e2'
REPORT_PINS = ['02b12923dd51122a7f8e1a90981aac15547c5bc2cf7ef06d74ee6eb9f9abc5e8', 'aa6b5f11b2dc9a8ad99ebc8aa5cf843ab2f253e538e98506cb4940b40036ee2a']
ACCOUNT_NAMES = ['statements', 'definitions', 'producers', 'physical_records', 'attempts', 'observations', 'outputs', 'titles', 'prints', 'means', 'printed_rows', 'analysis_variables', 'steps']
ORIGINAL_ACCOUNT = dict(zip(ACCOUNT_NAMES, [14, 1, 1, 5, 6, 5, 5, 2, 1, 1, 5, 2, 6], strict=True))
FIRST = ('TITLE:   Intake  \n"id" "Raw word" "Score" "backup"\n'
         '"A1" "High" 4 1\n"B2" "2" 2 4\n"C3" "Low" 1 3\n"D4" "Mid" 2 2\n"E5" "High" 4 1\n')
SECOND = ('TITLE:   Intake  \nvariable n mean std min max\n'
          '"n" 5 2.60000000 1.34164079 1 4\n"backup" 5 2.20000000 1.30384048 1 4\n')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def assert_tree(actual, expected):
    assert equal(actual, expected, ordered_maps=True), (actual, expected)


def original_expected():
    schema = {'id': {'type': 'character', 'length': 8}, 'word': {'type': 'character', 'length': 4},
              'n': {'type': 'number', 'length': 8}, 'backup': {'type': 'number', 'length': 8}}
    values = [('A1', 'High', 4, 1), ('B2', '2', 2, 4), ('C3', 'Low', 1, 3), ('D4', 'Mid', 2, 2), ('E5', 'High', 4, 1)]
    rows = [{'id': a.ljust(8), 'word': b.ljust(4), 'n': float(c), 'backup': float(d)} for a, b, c, d in values]
    return {'datasets': {'sample': {'schema': schema, 'rows': rows}}, 'log': [],
            'reports': {'print_01.txt': FIRST, 'means_01.txt': SECOND}}


def original_trace():
    events = []
    for i in range(1, 7):
        events.append({'kind': 'formatted_input', 'line': 6, 'attempt': i, 'complete': i <= 5})
        if i <= 5:
            events.append({'kind': 'formatted_output', 'line': 6, 'observation': i})
    events.append('informat-title|set|' + '  Intake  '.encode().hex())
    for prefix, name, report, stats in [('labelled-print', 'print_01.txt', FIRST, []), ('default-means', 'means_01.txt', SECOND, ['n|5|13|41|13/5|9/5', 'backup|5|11|31|11/5|17/10'])]:
        events.append(prefix + '|input|sample|5')
        records = report.splitlines()
        events.append(prefix + '|title|' + records[0].encode().hex())
        events.append(prefix + '|header|' + records[1].encode().hex())
        for i, record in enumerate(records[2:]):
            if stats:
                events.append(prefix + '|stats|' + stats[i])
            events.append(prefix + '|row|' + record.encode().hex())
        events.append(prefix + '|output|' + name + '|' + str(len(report)))
    events.append('informat-title|reset')
    return events


def decode(lines):
    result, trace, account, table = {'datasets': {}, 'log': []}, [], None, None
    for line in lines:
        tag, _, value = line.partition(' ')
        if tag == 'TABLE':
            table = {'schema': {}, 'rows': []}; result['datasets'][value] = table
        elif tag == 'COL':
            name, kind, width = value.split(); table['schema'][name] = {'type': kind, 'length': int(width)}
        elif tag == 'ROW':
            fields = []
            for token in value.split('|'):
                if token.startswith('C:'): fields.append(bytes.fromhex(token[2:]).decode('ascii'))
                elif token.startswith('N:'): fields.append(float(token[2:]))
                elif token == 'M': fields.append(None)
                else: raise AssertionError(token)
            table['rows'].append(dict(zip(table['schema'], fields, strict=True)))
        elif tag == 'ENDTABLE': pass
        elif tag == 'REPORT':
            name, encoded = value.split(); result.setdefault('reports', {})[name] = bytes.fromhex(encoded).decode('ascii')
        elif tag == 'TRACE_STRING': trace.append(bytes.fromhex(value).decode('ascii'))
        elif tag == 'TRACE_INPUT':
            line_no, attempt, complete = map(int, value.split()); trace.append({'kind': 'formatted_input', 'line': line_no, 'attempt': attempt, 'complete': bool(complete)})
        elif tag == 'TRACE_OUTPUT':
            line_no, observation = map(int, value.split()); trace.append({'kind': 'formatted_output', 'line': line_no, 'observation': observation})
        elif tag == 'ACCOUNT': account = dict(zip(ACCOUNT_NAMES, map(int, value.split()), strict=True))
        else: raise AssertionError(line)
    return {'result': result, 'trace': trace, 'accounting': account}


def batch_witness(sources, mode='print'):
    with tempfile.TemporaryDirectory(prefix='informat-report-R-') as temporary:
        area = Path(temporary); paths = []
        for i, source in enumerate(sources):
            path = area / (str(i) + '.sas'); path.write_text(source); paths.append(str(path))
        manifest = area / 'paths.txt'; manifest.write_text('\n'.join(paths) + '\n')
        twin = 'labelled_print.R' if mode == 'print' else 'default_means.R'
        process = subprocess.run([shutil.which('Rscript'), str(HERE / twin), str(manifest)], cwd=ROOT, text=True, capture_output=True, timeout=180)
        assert process.returncode == 0, (process.stdout, process.stderr)
        records, current = [], None
        for line in process.stdout.splitlines():
            if line.startswith('BEGIN '): current = []
            elif line == 'END':
                records.append(None if current == ['REFUSED'] else decode(current[:-1])); current = None
            else:
                assert current is not None; current.append(line)
        assert len(records) == len(sources)
        return records


def round_witness(cases):
    """Invoke the independent limb comparator directly on exact decimal ratios."""
    with tempfile.TemporaryDirectory(prefix='informat-report-round-') as temporary:
        path = Path(temporary) / 'ratios.txt'
        path.write_text(''.join(kind + '|' + str(value.numerator) + '|' + str(value.denominator) + '\n' for kind, value in cases))
        expression = ('source(' + json.dumps(str(HERE / 'informat_reports.R')) + ');'
                      'for(line in readLines(' + json.dumps(str(path)) + ')){p<-strsplit(line,"|",fixed=TRUE)[[1L]];'
                      'cat(rfixed(p[2L],p[3L],p[1L]=="std"),"\\n",sep="")}')
        process = subprocess.run([shutil.which('Rscript'), '-e', expression], cwd=ROOT, capture_output=True, text=True, timeout=120)
        assert process.returncode == 0, process.stderr
        tokens = process.stdout.splitlines()
        assert len(tokens) == len(cases)
        return tokens


def program_witness(path=ORIGINAL, mode='print'):
    return batch_witness([Path(path).read_text()], mode)[0]


def execute(source, emitted=False):
    parsed = compile_plan(source)
    if parsed.blocked: raise ValueError(str(parsed.tickets))
    plan = parsed.to_dict(); before = deepcopy(plan); trace = []
    result = run_plan(plan); assert plan == before
    assert_tree(run_program(plan, trace=trace), result)
    if emitted:
        translated = translate(source); assert not translated.blocked
        env, stdout = {}, io.StringIO()
        with contextlib.redirect_stdout(stdout): exec(translated.code, env)
        assert stdout.getvalue() == ''
        assert_tree(env['result'], result)
    return {'result': result, 'trace': trace}


def source(values=(1, 2, 4), *, title='Original', reset=False, means_first=False, labels='raw="Raw" n="Score"'):
    prefix = ("proc format;invalue usr_grade 'Positive'=1000 'Negative'=-1000 'Zero'=0 'Mid'=2;run;\n"
              'data sample;input id $ @4 raw $8. @4 n usr_grade.;datalines;\n')
    records = ''.join('A' + str(i % 10) + ' ' + str(value).ljust(8) + '!\n' for i, value in enumerate(values))
    prefix += records + ';\nrun;\n'
    title_source = '' if title is None else 'title ' + json.dumps(title) + ';\n'
    printed = 'proc print data=sample label noobs;label ' + labels + ';run;\n'
    means = 'proc means data=sample;run;\n'
    return prefix + title_source + (means + ('title;\n' if reset else '') + printed if means_first else printed + ('title;\n' if reset else '') + means)


def wide_source(rows=1, *, width=32, means_first=False, labels_length=1):
    names = ['id'] + ['c' + str(i) for i in range(30)] + ['n']
    terms = 'id $ ' + ' '.join('@4 ' + name + ' $' + str(width) + '.' for name in names[1:-1]) + ' @4 n usr_wide.'
    return ("proc format;invalue usr_wide '" + 'X' * 32 + "'=0;run;\ndata sample;input " + terms + ';datalines;\n'
            + ('A0 ' + 'X' * 32 + '!\n') * rows + ';\nrun;\n'
            + ('proc means data=sample;run;\n' if means_first else '')
            + 'proc print data=sample label noobs;label ' + ' '.join(name + '="' + 'L' * labels_length + '"' for name in names) + ';run;\n')


def hand_cases(mode='print'):
    cases = [ORIGINAL.read_text(), source([]), source([3]), source([0, 0]), source([-1000, 1000]),
             source([0] * 511 + [1]), source([0] * 511 + [-1]), source([1, 2], title='  Exact  '),
             source([2, 4], reset=True), source([-3, 1], means_first=True, reset=True),
             source([1], title=None, labels='raw="A \\"quote\\"" n="Score"').replace('\\"', '""')]
    # Keep the explicit doubled-quote source rather than JSON/C escaping.
    cases[-1] = source([1], title=None, labels='raw="A ""quote""" n="Score"')
    return cases


def generated_cases(mode='print', count=160):
    rng = random.Random(7301 if mode == 'print' else 7302); cases = []
    for i in range(count):
        values = [rng.randint(-1000, 1000) for _ in range(rng.randint(0, 18))]
        cases.append(source(values, title=None if i % 5 == 0 else 'Case ' + str(i), reset=i % 3 == 0, means_first=i % 2 == 0,
                            labels='raw="Raw ' + str(i) + '" n="Value"'))
    return cases


def refusal_cases(mode='print'):
    base = source([])
    return [base.replace('label noobs', 'noobs'), base.replace('label noobs', 'label'),
            base.replace('label raw="Raw" n="Score";', ''), base.replace('n="Score"', 'n="Score" n="Again"'),
            base.replace('raw="Raw"', 'absent="Raw"'), base.replace('raw="Raw"', 'raw=""'),
            base.replace('raw="Raw"', 'raw=" "'), base.replace('raw="Raw"', 'raw="&x"'),
            base.replace('raw="Raw"', 'raw="' + 'X' * 65 + '"'), base.replace('n="Score"', 'n=7'),
            base.replace('proc means data=sample;', 'proc means data=sample n;'),
            base.replace('proc means data=sample;', 'proc means data=sample;var n;'),
            base.replace('proc print data=sample label noobs;', 'proc print data=sample label noobs;var n;'),
            base + 'proc print data=sample label noobs;label n="Again";run;',
            base + 'proc means data=sample;run;', base + 'proc sort data=sample;by n;run;',
            base + 'orphan;', base.replace('title "Original";', 'title "%macro";'),
            source([1001]), source(['0.5']), source(['.']), base.replace('$8.', '$33.'),
            wide_source(1), wide_source(0, labels_length=31), base.removesuffix('run;\n')]


def cli_check(source_text, expected, reports, output, *, expect_code=0):
    area = output.parent; path = area / (output.name + '.sas'); path.write_text(source_text)
    data = area / (output.name + '-data.json'); data.write_text(json.dumps(expected))
    report = area / (output.name + '-reports.json'); report.write_text(json.dumps(reports))
    process = subprocess.run([sys.executable, '-B', '-m', 'saschi', 'run', str(path), '--expect', str(data), '--expect-reports', str(report), '--output', str(output)],
                             cwd=ROOT, env={**os.environ, 'PYTHONPATH': str(ROOT), 'PYTHONDONTWRITEBYTECODE': '1'}, text=True, capture_output=True, timeout=120)
    assert process.returncode == expect_code, (process.stdout, process.stderr)
    receipt = json.loads((output / 'receipt.json').read_text())
    if expect_code:
        assert receipt['accepted'] is False and not (output / 'reports').exists()
    else:
        assert receipt['accepted'] is True and receipt['comparison'] == receipt['report_comparison'] == 'passed'
        for name, text in reports.items(): assert (output / 'reports' / name).read_bytes() == text.encode('ascii')
    return receipt


def wrong_comparators(expected):
    values = []
    for change in [lambda x: x['reports'].__setitem__('print_01.txt', x['reports']['print_01.txt'].replace('Raw word', 'raw word')),
                   lambda x: x['reports'].__setitem__('means_01.txt', x['reports']['means_01.txt'].replace('1.34164079', '1.34164078')),
                   lambda x: x['reports'].__setitem__('means_01.txt', x['reports']['means_01.txt'].split('\n', 1)[1]),
                   lambda x: x['reports'].__setitem__('print_01.txt', x['reports']['print_01.txt'].rstrip('\n')),
                   lambda x: x['reports'].__setitem__('other.txt', x['reports'].pop('print_01.txt')),
                   lambda x: x['datasets']['sample']['schema']['word'].__setitem__('length', 5)]:
        wrong = deepcopy(expected); change(wrong); values.append(wrong)
    return values


def main(mode='print'):
    original = ORIGINAL.read_text(); expected = original_expected(); witness = program_witness(mode=mode)
    assert witness is not None
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() == SOURCE_PIN
    assert digest(expected) == RESULT_PIN and digest(original_trace()) == TRACE_PIN
    assert [hashlib.sha256(text.encode()).hexdigest() for text in expected['reports'].values()] == REPORT_PINS
    assert_tree(witness['result'], expected); assert_tree(witness['trace'], original_trace()); assert witness['accounting'] == ORIGINAL_ACCOUNT
    for emitted in [False, True]:
        got = execute(original, emitted); assert_tree(got['result'], expected); assert_tree(got['trace'], original_trace())
    hands, generated, refused = hand_cases(mode), generated_cases(mode), refusal_cases(mode)
    for text, reference in zip(hands + generated, batch_witness(hands + generated, mode), strict=True):
        assert reference is not None, text
        for emitted in [False, True]:
            actual = execute(text, emitted); assert_tree(actual['result'], reference['result']); assert_tree(actual['trace'], reference['trace'])
    for text, reference in zip(refused, batch_witness(refused, mode), strict=True):
        parsed = compile_plan(text)
        blocked = parsed.blocked
        if not blocked:
            try: run_plan(parsed.to_dict())
            except (ValueError, RuntimeError): blocked = True
        assert blocked and reference is None, (text, parsed.to_dict(), reference)
    assert translate_cpp(original).blocked
    with tempfile.TemporaryDirectory(prefix='informat-report-cli-') as temporary:
        area = Path(temporary); cli_check(original, expected['datasets'], expected['reports'], area / 'accepted')
        for i, wrong in enumerate(wrong_comparators(expected)):
            assert not equal(wrong, expected, ordered_maps=True)
            cli_check(original, wrong['datasets'], wrong['reports'], area / ('wrong-' + str(i)), expect_code=1)
        late = wide_source(1, means_first=True); seen = []
        native = informat_reports.execute_means
        def observe(*args, **kwargs): seen.append('means'); return native(*args, **kwargs)
        with patch.object(informat_reports, 'execute_means', observe): job = build_job(late)
        assert not job.plan.blocked and job.result is None and job.code == 1 and seen == ['means']
        path = area / 'late.sas'; path.write_text(late); output = area / 'late'
        run = subprocess.run([sys.executable, '-B', '-m', 'saschi', 'run', str(path), '--output', str(output)], cwd=ROOT, env={**os.environ, 'PYTHONPATH': str(ROOT)}, capture_output=True, timeout=120)
        assert run.returncode == 1 and not any((output / name).exists() for name in ['reports', 'exports', 'result.json', 'observed.json'])
    print('VERIFIED: ' + ('labelled-print' if mode == 'print' else 'default-means') + ' ' + str(len(hands)) + ' hand/' + str(len(generated)) + ' generated/' + str(len(refused)) + ' shared refusals;6 actual wrong CLI comparators+late atomic; original14statements/5rows/30events,exact local-label/title/statistics evidence; no live SAS')
    return 0


if __name__ == '__main__': raise SystemExit(main())
