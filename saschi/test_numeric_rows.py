"""Independent C1/C2 source, imported-domain, descriptor and state boundaries."""
from copy import deepcopy
import contextlib
import io
import math
import unittest

from examples.verify_numeric_rows import (ORIGINAL, incoming, original_expected,
    original_accounting, program_witness, execute, c1_source, c1_expected,
    c2_pins, naive_controls, cli_check)
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan


class NumericRowsTests(unittest.TestCase):
    def test_c1_marker_is_distinct_and_output_option_keeps_header_line(self):
        plan=compile_plan('data d(keep=q);q=1/3;p=1**1;run;')
        self.assertFalse(plan.blocked,plan.tickets)
        operations=plan.to_dict()['steps'][0]['operations']
        self.assertEqual(operations[0],{'kind':'numeric_profile','line':1,'args':{'name':'binary64-rows-v1'}})
        self.assertEqual(operations[1]['kind'],'projection')
        self.assertEqual(operations[1]['line'],operations[0]['line'])

    def test_c2_marker_and_old_profile_shapes_remain_distinct(self):
        for source,profile in [('data d;p=1**1;run;','binary64-v1'),
            ('data d;set incoming;p=1**1;run;','binary64-rows-v1')]:
            p=compile_plan(source);self.assertFalse(p.blocked,p.tickets)
            self.assertEqual(p.steps[0].operations[0].args,{'name':profile})
        ordinary=compile_plan('data d(keep=a);a=1;run;').to_dict()
        self.assertFalse(any(o['kind']=='numeric_profile' for o in ordinary['steps'][0]['operations']))

    def test_c1_three_projection_forms_keep_pdv_and_earlier_snapshots(self):
        for mode in range(3):self.assertEqual(execute(c1_source(1.,mode),emitted=True),c1_expected(1.))

    def test_c1_skipped_output_suppresses_implicit_and_discovers_future(self):
        table=execute('data d(keep=future);p=1**1;if 0 then future=2;if 0 then output;run;')['datasets']['d']
        self.assertEqual(table,{'schema':{'future':'number'},'rows':[]})

    def test_old_profile_cannot_be_forged_to_admit_composition(self):
        for source in ('data d(keep=p);p=1**1;run;','data d;set incoming;p=1**1;run;'):
            p=compile_plan(source).to_dict();p['steps'][0]['operations'][0]['args']['name']='binary64-v1'
            with self.assertRaises(ValueError):run_plan(p,incoming())

    def test_rows_marker_requires_composition_and_actual_executable_trigger(self):
        p=compile_plan('data d;p=1**1;run;').to_dict()
        p['steps'][0]['operations'][0]['args']['name']='binary64-rows-v1'
        with self.assertRaises(ValueError):run_plan(p)
        p=compile_plan('data d(keep=p);p=1**1;run;').to_dict()
        p['steps'][0]['operations'][-1]['args']['value']={'kind':'number','value':1.}
        with self.assertRaises(ValueError):run_plan(p)

    def test_original_three_steps_independent_source_and_accounting(self):
        independent,accounting=program_witness()
        self.assertEqual(accounting,original_accounting())
        self.assertEqual(independent,original_expected())
        self.assertEqual(execute(ORIGINAL.read_text(),incoming(),True),original_expected())

    def test_input_projection_then_numeric_reference_creates_fresh_scratch(self):
        source='data d(keep=before c);set incoming(drop=excluded);p=1**1;before=excluded;if key=1 then excluded=7;c=excluded;run;'
        rows=execute(source,incoming())['datasets']['d']['rows']
        self.assertEqual(rows,[{'before':None,'c':7.},{'before':None,'c':None},{'before':None,'c':None}])

    def test_imported_missing_replaces_previously_modified_input(self):
        source,catalog,expected=c2_pins()[5]
        self.assertEqual(execute(source,catalog),expected)

    def test_imported_sum_target_is_overwritten_including_missing(self):
        source,catalog,expected=c2_pins()[-1]
        self.assertEqual(execute(source,catalog),expected)
        source='data d(keep=total);set incoming(drop=total);p=1**1;total+x;run;'
        self.assertEqual(execute(source,catalog)['datasets']['d']['rows'],[{'total':1.},{'total':3.}])

    def test_input_scratch_and_retained_state_have_separate_row_lifetimes(self):
        source='data d(keep=s total);retain total 0;set incoming;p=1**1;if key=1 then s=5;total+x;run;'
        self.assertEqual(execute(source,incoming())['datasets']['d']['rows'],[
            {'total':1.,'s':5.},{'total':3.,'s':None},{'total':6.,'s':None}])

    def test_selected_input_values_validate_eagerly_in_all_consumer_paths(self):
        for tail in ('carry=0;','if 0;','if 0 then output;','drop carry;'):
            for value in (2147483648.,2.**-1074,{'missing':'A'}):
                supplied=incoming();supplied['incoming']['rows'][-1]['carry']=value
                source='data d;set incoming;p=1**1;'+tail+'run;'
                with self.subTest(tail=tail,value=value),self.assertRaises(ValueError):execute(source,supplied)

    def test_selected_character_descriptor_refuses_even_without_observations(self):
        for rows in (False,True):
            supplied=incoming(rows);supplied['incoming']['schema']['carry']={'type':'character','length':4}
            for row in supplied['incoming']['rows']:row['carry']='x'
            with self.assertRaises(ValueError):execute('data d;set incoming;p=1**1;run;',supplied)

    def test_excluded_legal_generic_columns_do_not_gain_binary64_limits(self):
        for spec,value in [('number',2147483648.),('number',{'missing':'A'}),
                           ({'type':'character','length':4},'text')]:
            supplied=incoming();supplied['incoming']['schema']['excluded']=spec
            for row in supplied['incoming']['rows']:row['excluded']=deepcopy(value)
            result=execute('data d(keep=q);set incoming(drop=excluded);p=1**1;q=x/3;run;',supplied)
            self.assertEqual(result['datasets']['d']['rows'],[{'q':1/3},{'q':2/3},{'q':1.}])

    def test_excluded_column_does_not_hide_malformed_generic_catalog(self):
        for damage in ('value','row','metadata','descriptor'):
            supplied=incoming()
            if damage=='value':supplied['incoming']['rows'][0]['excluded']='bad'
            elif damage=='row':supplied['incoming']['rows'][0].pop('excluded')
            elif damage=='metadata':supplied['incoming']['label']=2
            else:supplied['incoming']['schema']['excluded']={'type':'number','length':4}
            with self.subTest(damage=damage),self.assertRaises(ValueError):
                execute('data d;set incoming(drop=excluded);p=1**1;run;',supplied)

    def test_metadata_order_private_zero_and_catalog_nonmutation(self):
        supplied=incoming();supplied['incoming']['rows'][0]['x']=-0.
        source='data d(keep=x key);set incoming(keep=x key);p=1**1;run;'
        before=deepcopy(supplied);plan=compile_plan(source).to_dict();saved=deepcopy(plan)
        result=run_plan(plan,supplied)
        self.assertEqual(supplied,before);self.assertEqual(plan,saved)
        self.assertEqual(math.copysign(1.,supplied['incoming']['rows'][0]['x']),-1.)
        self.assertEqual(math.copysign(1.,result['datasets']['incoming']['rows'][0]['x']),-1.)
        self.assertEqual(math.copysign(1.,result['datasets']['d']['rows'][0]['x']),1.)
        self.assertEqual(list(result['datasets']['d']['schema']),['key','x'])
        self.assertEqual(result['datasets']['d']['schema']['key'],supplied['incoming']['schema']['key'])
        result['datasets']['d']['schema']['key']['label']='changed'
        self.assertEqual(supplied,before)

    def test_empty_source_preserves_static_selected_schema_and_metadata(self):
        source='data d(keep=future key);set incoming(keep=key);p=1**1;if 0 then future=2;run;'
        table=execute(source,incoming(False))['datasets']['d']
        self.assertEqual(list(table['schema']),['key','future']);self.assertEqual(table['rows'],[])
        self.assertEqual(table['encoding'],'latin-1');self.assertEqual(table['label'],'numeric source')

    def test_format_metadata_transports_but_numeric_put_remains_refused(self):
        supplied=incoming();supplied['incoming']['schema']['x']={'type':'number','length':8,'format':'8.2','label':'formatted'}
        source='data d(keep=x);set incoming(keep=x);p=1**1;run;'
        self.assertEqual(execute(source,supplied)['datasets']['d']['schema']['x'],supplied['incoming']['schema']['x'])
        with self.assertRaises(ValueError):execute(source.replace('run;','put x;run;'),supplied)

    def test_dead_invalid_literals_and_unknown_selection_refuse_on_empty_source(self):
        for source in ('data d(keep=key);set incoming;p=1**1;if 0 then bad=sin(4);run;',
            'data d(keep=absent);set incoming;p=1**1;run;',
            'data d;set incoming(keep=absent);p=1**1;run;'):
            with self.assertRaises((ValueError,AssertionError)):execute(source,incoming(False))

    def test_projection_marker_forgery_cannot_change_read_timing(self):
        p=compile_plan('data d(keep=q);set incoming(keep=x);q=x/3;p=1**1;run;').to_dict()
        for edit in ('option_first','read_late','scope','duplicate'):
            forged=deepcopy(p);ops=forged['steps'][0]['operations']
            if edit=='option_first':ops[0],ops[1]=ops[1],ops[0]
            elif edit=='read_late':ops.insert(2,ops.pop(-1))
            elif edit=='scope':ops[2]['args']['scope']='output'
            else:ops.append(deepcopy(ops[2]))
            with self.subTest(edit=edit),self.assertRaises(ValueError):run_plan(forged,incoming(False))

    def test_unproved_input_and_control_forms_stay_blocked(self):
        for clause in ('set incoming;by key;','set incoming;where x>0;',
            'merge incoming other;by key;','if _n_=1 then set config;set incoming;',
            'input x;datalines;\n1\n;\n','array a{1} x;','do while(0);x=1;end;',
            'do until(1);x=1;end;'):
            source='data d(keep=q);'+clause+'q=1**1;run;'
            parsed=compile_plan(source)
            if clause in ('array a{1} x;','do while(0);x=1;end;','do until(1);x=1;end;'):
                from .numeric_pipeline import PROFILE as PIPELINE_PROFILE
                from examples.verify_numeric_pipeline import witnesses as pipeline_witnesses
                self.assertFalse(parsed.blocked,parsed.tickets)
                serialized=parsed.to_dict()
                self.assertEqual(serialized['steps'][0]['operations'][0]['args'],{'name':PIPELINE_PROFILE})
                from examples.verify_numeric_rows import batch_witness as old_profile_witnesses
                self.assertEqual(old_profile_witnesses([(source,{})]),[None])
                independent=pipeline_witnesses([(source,{})])[0];self.assertIsNotNone(independent)
                self.assertEqual(run_plan(serialized),independent[0])
                serialized['steps'][0]['operations'][0]['args']['name']='binary64-rows-v1'
                with self.assertRaises(ValueError):run_plan(serialized)
            else:self.assertTrue(parsed.blocked,clause)

    def test_legacy_exact_arithmetic_and_text_limits_remain(self):
        for source in ('data d;q=1/3;run;','data d;q=1.1*1.1;run;'):
            with self.assertRaises(ValueError):execute(source)
        with self.assertRaises(ValueError):execute('data d(keep=q);p=1**1;q=0.00001;put q;run;')

    def test_bad_late_import_and_hidden_calculation_publish_nothing(self):
        sources=[('data earlier;put "EARLIER";run;data d(keep=q);set incoming;q=1**1;carry=0;run;',incoming()),
            ('data earlier;put "EARLIER";run;data d(keep=q);q=1**1;z=0;put q;hidden=1/z;run;',{})]
        sources[0][1]['incoming']['rows'][-1]['carry']=2147483648.
        for source,supplied in sources:
            # Job evidence uses actual CLI input serialization and emitted buffering.
            cli_check(source,supplied)
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(source).code,{'inputs':supplied})
            self.assertEqual(stream.getvalue(),'')

    def test_six_competing_interpretations_are_detected(self):
        self.assertEqual(naive_controls(),6)
        self.assertEqual(naive_controls('projection'),6)

    def test_counted_budget_resets_per_supplied_observation(self):
        supplied=incoming();supplied['incoming']['rows']=supplied['incoming']['rows'][:2]
        result=execute('data d(keep=q);set incoming(keep=key);trigger=1**1;q=0;do i=1 to 10000;q=q+1;end;run;',supplied)
        self.assertEqual(result['datasets']['d']['rows'],[{'q':10000.},{'q':10000.}])


if __name__=='__main__':unittest.main()
