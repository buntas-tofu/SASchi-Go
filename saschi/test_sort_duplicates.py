"""Source, portable, lineage and report boundaries for the dual-output family."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from .plan import compile_plan
from .runtime import run_plan
from .emit_py import translate
from .emit_cpp import translate as cpp_translate
from .job import build_job
from . import sort_duplicates as duplicate
from . import mixed_reports, sort_options
from .report_artifacts import (read_expected_reports, report_manifest,
                               MIXED_REPORT_CONTRACT, DUPLICATE_REPORT_CONTRACT)

ROOT = Path(__file__).resolve().parents[1]
CARDS = ['B,2,1', 'A,1,2', 'B,2,3', 'A,.,4', 'A,1,5']


def source(cards=CARDS, *, replace=False, prints=0):
    text = ('data raw;\ninfile datalines dsd;\ninput z :$2. n serial;\ndatalines4;\n'
            + ''.join(row + '\n' for row in cards) + ';;;;\nrun;\n')
    if replace:
        text += 'proc sort data=raw out=ranked;by z n;run;\n'
    table = 'ranked' if replace else 'raw'
    text += ('proc sort data=' + table + ('' if replace else ' out=kept')
             + ' dupout=removed nodupkey;by z n;run;\n')
    for _ in range(prints):
        text += 'proc print data=removed;run;\n'
    return text


def plan(text=None):
    value = compile_plan(source() if text is None else text)
    if value.blocked:
        raise AssertionError([(t.line, t.reason) for t in value.tickets])
    return value.to_dict()


class DuplicateTests(unittest.TestCase):
    def blocked(self, text):
        value = compile_plan(text)
        self.assertTrue(value.blocked)
        with self.assertRaises(RuntimeError):
            run_plan(value.to_dict())

    def reject(self, mutate):
        value = plan()
        mutate(value)
        with self.assertRaises((ValueError, TypeError)):
            run_plan(value)

    def test_complete_identity_partition_and_sorted_removed_order(self):
        value = plan(); trace = []
        actual = duplicate.run_program(value, trace=trace)
        self.assertEqual([r['serial'] for r in actual['datasets']['kept']['rows']], [4, 2, 1])
        self.assertEqual([r['serial'] for r in actual['datasets']['removed']['rows']], [5, 3])
        event = trace[-1]
        self.assertEqual(event['source_ordinals'], [4, 2, 5, 1, 3])
        self.assertEqual(event['kept_ordinals'], [4, 2, 1])
        self.assertEqual(event['removed_ordinals'], [5, 3])
        self.assertEqual(sorted(event['kept_ordinals'] + event['removed_ordinals']), list(range(1, 6)))

    def test_equal_payload_duplicates_keep_multiplicity_and_identity(self):
        value = plan(source(['A,1,7'] * 4)); trace = []
        result = duplicate.run_program(value, trace=trace)
        self.assertEqual(len(result['datasets']['removed']['rows']), 3)
        self.assertEqual(trace[-1]['kept_ordinals'], [1])
        self.assertEqual(trace[-1]['removed_ordinals'], [2, 3, 4])

    def test_empty_input_preserves_both_complete_schemas(self):
        result = run_plan(plan(source([])))
        self.assertEqual(result['datasets']['kept']['rows'], [])
        self.assertEqual(result['datasets']['removed']['rows'], [])
        self.assertEqual(list(result['datasets']['removed']['schema']), ['z', 'n', 'serial'])

    def test_partition_is_pure_and_outputs_do_not_alias(self):
        value = plan(); raw = run_plan(value)['datasets']['raw']; before = deepcopy(raw)
        tables = {'raw': raw}; output = duplicate.execute_partition(value['steps'][-1], tables)
        output['kept']['schema']['z']['length'] = 64
        output['kept']['rows'][0]['serial'] = 99
        self.assertEqual(raw, before)
        self.assertEqual(output['removed']['schema']['z']['length'], 2)

    def test_old_catalog_and_portable_plan_are_not_mutated(self):
        value = plan(); before = deepcopy(value); catalog = {}
        run_plan(value, catalog)
        self.assertEqual(value, before); self.assertEqual(catalog, {})

    def test_fractional_sort_domain_is_separate_from_print_domain(self):
        result = run_plan(plan(source(['A,0.5,1', 'A,-0.5,2', 'A,.,3'])))
        self.assertEqual([r['serial'] for r in result['datasets']['kept']['rows']], [3, 2, 1])
        job = build_job(source(['A,0.5,1', 'A,0.5,2'], prints=1))
        self.assertFalse(job.plan.blocked); self.assertEqual(job.code, 1); self.assertIsNone(job.result)

    def test_blank_padding_and_case_are_preserved(self):
        result = run_plan(plan(source([',1,1', 'a,1,2', 'A,1,3', 'A ,1,4'])))
        self.assertEqual([r['serial'] for r in result['datasets']['kept']['rows']], [1, 3, 2])
        self.assertEqual(result['datasets']['removed']['rows'][0]['z'], 'A ')

    def test_owned_replacement_preserves_original(self):
        result = run_plan(plan(source(replace=True)))
        self.assertEqual(len(result['datasets']['raw']['rows']), 5)
        self.assertEqual(len(result['datasets']['ranked']['rows']), 3)
        self.assertEqual(len(result['datasets']['removed']['rows']), 2)

    def test_original_producer_is_not_replaceable(self):
        self.blocked(source().replace(' out=kept', ''))

    def test_dupo_side_output_does_not_acquire_replacement_ownership(self):
        self.blocked(source() + 'proc sort data=removed dupout=again nodupkey;by z;run;')

    def test_prior_dual_survivor_can_be_replaced_again(self):
        text = source() + 'proc sort data=kept dupout=second nodupkey;by z;run;'
        result = run_plan(plan(text))
        self.assertEqual(len(result['datasets']['kept']['rows']), 2)
        self.assertEqual(len(result['datasets']['second']['rows']), 1)

    def test_explicit_out_equal_to_input_is_refused(self):
        self.blocked(source().replace('out=kept', 'out=raw'))

    def test_all_destination_collisions_refuse_even_empty(self):
        for before, after in [('dupout=removed', 'dupout=raw'), ('dupout=removed', 'dupout=kept')]:
            with self.subTest(after=after): self.blocked(source([]).replace(before, after))
        self.blocked(source([]) + 'proc sort data=raw out=kept dupout=fresh nodupkey;by z;run;')

    def test_nonduplicate_joins_cannot_replace_in_this_family(self):
        self.blocked(source() + 'proc sort data=raw;by z;run;')

    def test_directed_prior_sort_is_admitted(self):
        text = source(replace=True).replace('out=ranked;by z n', 'out=ranked;by z descending n')
        trace = []
        result = duplicate.run_program(plan(text), trace=trace)
        self.assertEqual(next(event for event in trace if event.get('event') == 'sort')['source_ordinals'], [2, 5, 4, 1, 3])
        self.assertEqual([r['serial'] for r in result['datasets']['ranked']['rows']], [4, 2, 1])

    def test_projection_and_all_column_joins_stay_refused(self):
        for text in [source().replace('data=raw out=kept', 'data=raw(keep=z n) out=kept'),
                     source() + 'proc sort data=raw out=allrows nodupkey;by _all_;run;']:
            with self.subTest(text=text): self.blocked(text)

    def test_unsupported_header_options_and_directed_dupo_refuse(self):
        for text in [source().replace(' nodupkey;', ';'), source().replace('nodupkey;', 'noduprecs;'),
                     source().replace('nodupkey;', 'nodupkey noequals;'),
                     source().replace('by z n;', 'by z descending n;')]:
            with self.subTest(text=text): self.blocked(text)

    def test_unknown_and_duplicate_by_refuse_on_empty(self):
        for by in ['absent', 'z z', '_all_', 'z n serial z']:
            with self.subTest(by=by): self.blocked(source([]).replace('by z n;', 'by ' + by + ';'))

    def test_missing_or_non_character_producer_cannot_select_family(self):
        self.blocked('proc sort data=raw out=kept dupout=removed nodupkey;by z;run;')
        self.blocked(source().replace('z :$2.', 'z'))

    def test_comment_literal_and_opaque_markers_do_not_select_family(self):
        base = 'data raw;infile datalines dsd;input z :$32. n;datalines4;\ndupout=shadow,1\n;;;;\nrun;\n'
        for text in [base, base + 'title "dupout=shadow";proc print data=raw;run;',
                     '/* proc sort data=raw dupout=shadow nodupkey; */' + base]:
            value = plan(text)
            self.assertFalse(any(s['kind'] in duplicate.KINDS for s in value['steps']))

    def test_old_program_with_dataset_named_dupout_keeps_old_routing(self):
        text = source().split('proc sort')[0].replace('data raw;', 'data dupout;')
        text += 'proc sort data=dupout out=plain;by z;run;'
        value = plan(text)
        self.assertFalse(any(s['kind'] in duplicate.KINDS for s in value['steps']))

    def test_plain_old_family_keeps_inplace_behavior(self):
        text = source().split('proc sort')[0] + 'proc sort data=raw;by z;run;'
        self.assertFalse(compile_plan(text).blocked)
        self.assertEqual(len(run_plan(plan(text))['datasets']['raw']['rows']), 5)

    def test_three_new_reports_have_distinct_contract_and_basenames(self):
        job = build_job(source(prints=3))
        self.assertEqual(job.code, 0)
        self.assertEqual(job.receipt['report_contract'], DUPLICATE_REPORT_CONTRACT)
        self.assertEqual(list(job.result['reports']), ['print_01.txt', 'print_02.txt', 'print_03.txt'])
        self.assertEqual(len(job.receipt['reports']), 3)

    def test_old_mixed_renderer_and_manifest_still_reject_third_report(self):
        value = plan(source(prints=3)); step = deepcopy(value['steps'][-1])
        step['kind'] = step['operations'][0]['kind'] = 'mixed_print'
        step['operations'][0]['args']['profile'] = mixed_reports.PRINT_PROFILE
        tables = run_plan(value)['datasets']
        with self.assertRaises(ValueError): mixed_reports.execute_print(step, tables, ordinal=3)
        with self.assertRaises(ValueError): report_manifest(run_plan(value)['reports'], contract=MIXED_REPORT_CONTRACT)

    def test_fourth_report_and_excess_titles_refuse(self):
        self.blocked(source(prints=4))
        self.blocked(source() + 'title "x";' * 33)

    def test_title_snapshot_and_reset_persist_through_replacement(self):
        text = source(replace=True).replace('proc sort data=ranked',
                    'title "Before";proc print data=ranked;run;proc sort data=ranked')
        text += 'title;proc print data=ranked;run;'
        result = run_plan(plan(text)); reports = result['reports']
        self.assertIn('5 "B" 2 3\n', reports['print_01.txt'])
        self.assertTrue(reports['print_01.txt'].startswith('TITLE: Before\n'))
        self.assertFalse(reports['print_02.txt'].startswith('TITLE:'))

    def test_emitted_result_and_cpp_refusal(self):
        text = source(prints=3); namespace = {}; emitted = translate(text)
        self.assertFalse(emitted.blocked); exec(emitted.code, namespace)
        self.assertEqual(namespace['result'], run_plan(plan(text)))
        self.assertTrue(cpp_translate(text).blocked)

    def test_preflight_never_executes_sort_or_partition(self):
        with patch.object(duplicate, 'execute_partition', side_effect=AssertionError('preflight partition')), \
             patch.object(sort_options, 'execute_sort', side_effect=AssertionError('preflight sort')):
            value = plan(source(replace=True)); duplicate.validate_program(value)

    def test_each_actual_sort_executes_once(self):
        value = plan(source(replace=True))
        with patch.object(duplicate, 'execute_partition', wraps=duplicate.execute_partition) as part, \
             patch.object(sort_options, 'execute_sort', wraps=sort_options.execute_sort) as sort:
            run_plan(value)
        self.assertEqual(part.call_count, 1); self.assertEqual(sort.call_count, 1)

    def test_new_report_markers_alone_cannot_select_portable_family(self):
        value = plan(source(prints=1)); value['steps'].pop(1)
        with self.assertRaises(ValueError): run_plan(value)

    def test_nonempty_or_nonplain_catalog_refuses(self):
        value = plan()
        for catalog in [{'external': {}}, [], False]:
            with self.subTest(catalog=catalog), self.assertRaises(ValueError): run_plan(value, catalog)

    def test_exact_version_and_plain_step_types(self):
        for version in [True, 1, 2.0, '2']:
            with self.subTest(version=version): self.reject(lambda v: v.update(version=version))
        self.reject(lambda v: v['steps'][-1].update(line=True))
        self.reject(lambda v: v['steps'][-1].update(inputs=('raw',)))

    def test_extra_fields_or_wrong_operation_line_refuse(self):
        self.reject(lambda v: v['steps'][-1].update(unexpected=1))
        self.reject(lambda v: v['steps'][-1]['operations'][0].update(line=1))
        self.reject(lambda v: v['steps'][-1]['operations'][0]['args'].update(extra=1))

    def test_legacy_metadata_and_wrong_kind_refuse(self):
        for key, value in [('by', ['z']), ('nodupkey', True), ('where', {}), ('retained', {'x': 1}),
                           ('lengths', {'z': 2}), ('display_names', {'z': 'Z'})]:
            with self.subTest(key=key): self.reject(lambda v: v['steps'][-1].update({key: value}))
        self.reject(lambda v: v['steps'][-1]['operations'][0].update(kind='sort'))

    def test_by_list_and_replace_flag_plain_types(self):
        for by in [[], ['z', 'z'], ['absent'], [True], ('z',), ['_all_']]:
            with self.subTest(by=by): self.reject(lambda v: v['steps'][-1]['operations'][0]['args'].update(by=by))
        self.reject(lambda v: v['steps'][-1]['operations'][0]['args'].update(replace=0))
        self.reject(lambda v: v['steps'][-1]['operations'][0]['args'].update(replace=True))

    def test_portable_provenance_must_be_plain_ordered_lines(self):
        for lines in [[True, 3], [], [99, 1], [0, 0], [1, 2, 3], (20, 21)]:
            with self.subTest(lines=lines): self.reject(lambda v: v['steps'][-1]['operations'][0]['args'].update(source_lines=lines))

    def test_cyclic_and_hidden_markers_refuse_before_legacy_dispatch(self):
        value = plan(); value['matched'].append(value)
        with self.assertRaises(ValueError): run_plan(value)
        for marker in [{'kind': duplicate.KIND}, {'kind': duplicate.PRINT_KIND}, {'profile': duplicate.PROFILE}]:
            old = compile_plan('data x;x=1;output;run;').to_dict()
            old['steps'][0]['operations'][0]['args']['hidden'] = marker
            with self.subTest(marker=marker), self.assertRaises(ValueError): run_plan(old)

    def test_shared_acyclic_container_is_not_a_cycle(self):
        value = plan(); shared = ['ordinary', 'metadata']; value['matched'].extend([shared, shared])
        self.assertIsNotNone(duplicate.validate_program(value))

    def test_invalid_all_original_cells_cannot_hide_in_removed_rows(self):
        value = plan(); value['steps'][0]['operations'][0]['args']['records'][2] = 'B,nan,3'
        with self.assertRaises(ValueError): run_plan(value)
        self.blocked(source(['B,2,1', 'B,2,9999999999999999999999999999999']))

    def test_table_validation_rejects_boolean_cells_and_invalid_excluded_tables(self):
        value = plan(); raw = run_plan(value)['datasets']['raw']; raw['rows'][0]['n'] = True
        with self.assertRaises(ValueError): duplicate.execute_partition(value['steps'][-1], {'raw': raw})
        raw = run_plan(value)['datasets']['raw']
        with self.assertRaises(ValueError): duplicate.execute_partition(value['steps'][-1], {'raw': raw, 'unused': {'schema': {}, 'rows': []}})

    def test_64_step_boundary_and_extra_step_refusal(self):
        text = source([]) + ''.join('proc sort data=raw out=t' + str(i) + ';by z;run;' for i in range(62))
        self.assertEqual(len(plan(text)['steps']), 64)
        self.blocked(text + 'proc sort data=raw out=overflow;by z;run;')

    def test_expected_report_contract_has_distinct_entry_and_byte_caps(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'expected.json'; path.write_text(json.dumps({f'print_0{i}.txt': 'x\n' for i in range(1, 4)}))
            self.assertEqual(len(read_expected_reports(path, contract=DUPLICATE_REPORT_CONTRACT)[0]), 3)
            with self.assertRaises(ValueError): read_expected_reports(path, contract=MIXED_REPORT_CONTRACT)
            path.write_text(json.dumps({'print_01.txt': 'x' * 2200000}))
            read_expected_reports(path, contract=DUPLICATE_REPORT_CONTRACT)
            with self.assertRaises(ValueError): read_expected_reports(path, contract=MIXED_REPORT_CONTRACT)
            path.write_text(json.dumps({'print_01.txt': 'x' * 4200000}))
            with self.assertRaises(ValueError): read_expected_reports(path, contract=DUPLICATE_REPORT_CONTRACT)

    def test_report_step_shapes_ordinals_and_artifact_validation(self):
        value = plan(source(prints=1)); step = value['steps'][-1]; tables = run_plan(value)['datasets']
        for ordinal in [True, 0, 4]:
            with self.subTest(ordinal=ordinal), self.assertRaises(ValueError): duplicate.execute_print(step, tables, ordinal=ordinal)
        bad = deepcopy(value); bad['steps'][-1]['inputs'] = ['raw']
        with self.assertRaises(ValueError): run_plan(bad)
        for reports in [{}, {'print_03.txt': 'obs z\n'}, {'print_01.txt': 'bad\n'}]:
            with self.subTest(reports=reports), self.assertRaises(ValueError): duplicate.validate_reports(reports)

    def test_real_late_third_report_failure_publishes_no_job_result(self):
        text = source(prints=3); renderer = duplicate.execute_print; observed = []
        def fail(step, tables, title=None, ordinal=1, version=2, **kwargs):
            if ordinal == 3: raise ValueError('owned late third report fault')
            result = renderer(step, tables, title, ordinal, version, **kwargs); observed.append(ordinal); return result
        with patch.object(duplicate, 'execute_print', fail): job = build_job(text)
        self.assertEqual(observed, [1, 2]); self.assertEqual(job.code, 1); self.assertIsNone(job.result)
        self.assertFalse(job.receipt['accepted'])

    def test_actual_cli_three_reports_and_failed_comparison_atomicity(self):
        with tempfile.TemporaryDirectory() as folder:
            area = Path(folder); src = area / 'job.sas'; src.write_text(source(prints=3))
            output = area / 'accepted'
            command = [sys.executable, '-B', '-m', 'saschi', 'run', str(src), '--output', str(output)]
            run = subprocess.run(command, cwd=ROOT, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(sorted(p.name for p in (output / 'reports').iterdir()), ['print_01.txt', 'print_02.txt', 'print_03.txt'])
            expected = area / 'wrong.json'; expected.write_text(json.dumps({'print_01.txt': 'wrong\n'}))
            failed = area / 'failed'; command[-1] = str(failed); command += ['--expect-reports', str(expected)]
            run = subprocess.run(command, cwd=ROOT, capture_output=True)
            self.assertEqual(run.returncode, 1); self.assertFalse((failed / 'reports').exists())
            self.assertFalse((failed / 'result.json').exists())


if __name__ == '__main__':
    unittest.main()
