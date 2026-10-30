"""D1 converter, exact controls, rounded array state and loop composition."""
from copy import deepcopy
import contextlib
import io
import math
import unittest

from .numeric_pipeline import (PROFILE,validate_step,evaluate,array_index,array_set,array_current_set,array_sum)
from .plan import compile_plan
from .runtime import run_plan
from .emit_py import translate
from .job import build_job
from examples.verify_numeric_pipeline import (ORIGINAL,original_expected,pins,witnesses,execute,inline_source,naive_controls,cli_check,cli_wrong_controls)


def number(value):return {'kind':'missing' if value is None else 'number','value':value}
def binary(op,left,right):return {'kind':'arithmetic','op':op,'left':left,'right':right}
def operation(kind,args):return {'kind':kind,'line':1,'args':args}
def step():
    return {'kind':'data','name':'d','line':1,'inputs':[],'by':[],'operations':[
        operation('numeric_profile',{'name':PROFILE}),operation('array_declare',{'name':'a','lower':1,'names':['x','y']}),
        operation('assign',{'name':'trigger','value':binary('**',number(1.),number(1.))})],
        'nodupkey':False,'where':None,'retained':{},'lengths':{},'display_names':{}}


class NumericPipelinePrimitiveTests(unittest.TestCase):
    def test_array_sum_order_missing_and_domain(self):
        self.assertIsNone(array_sum([None,None]))
        self.assertEqual(array_sum([1e9,.1,-1e9]),.10000002384185791)
        self.assertEqual(array_sum([None,1/3,2/3]),1.)
        for values in ([],None,[True],[5e-324],[{'missing':'A'}],[2147483647.,1.],list(range(1025))):
            with self.subTest(values=str(values)[:50]),self.assertRaises(ValueError):array_sum(values)

    def test_declared_aliases_use_rounded_values_and_exact_indices(self):
        arrays=validate_step(step())['arrays'];row={'x':1.,'y':2.}
        array_set({'name':'a','index':number(1.),'value':binary('/',number(1.),number(3.))},row,arrays)
        self.assertEqual(row['x'],1/3)
        self.assertEqual(evaluate({'kind':'array_get','name':'a','index':number(1.)},row,arrays),1/3)
        row['y']=2/3;self.assertEqual(evaluate({'kind':'array_sum','name':'a'},row,arrays),1.)
        for index in (number(None),number(0.),number(3.),number(1.5),binary('+',number(1.),number(.1))):
            with self.assertRaises(ValueError):array_index('a',index,row,arrays)

    def test_current_binding_is_internal_and_validated(self):
        arrays={'a':{'name':'a','lower':1,'names':['x','y'],'mode':'implicit'}};row={'x':1.,'y':2.}
        array_current_set({'name':'a','value':binary('/',number(1.),number(3.))},row,arrays,{'a':1})
        self.assertEqual(row['y'],1/3);self.assertEqual(set(row),{'x','y'})
        for current in ({},{'a':True},{'a':-1},{'a':2}):
            with self.assertRaises(ValueError):array_current_set({'name':'a','value':number(1.)},row,arrays,current)

    def test_distinct_marker_requires_real_feature_and_trigger(self):
        self.assertIsNotNone(validate_step(step()))
        p=step();p['operations'][0]['args']['name']='binary64-v1';self.assertIsNone(validate_step(p))
        p=step();p['operations'].pop(1)
        with self.assertRaises(ValueError):validate_step(p)
        p=step();p['operations'][-1]['args']['value']=number(1.)
        with self.assertRaises(ValueError):validate_step(p)

    def test_profile_version_requires_an_exact_integer(self):
        for version in (2.0,'2',True,False,None):
            with self.subTest(version=version),self.assertRaises(ValueError):validate_step(step(),version)

    def test_index_and_scalar_nodes_share_the_numeric_step_budget(self):
        def balanced(values):
            while len(values)>1:
                values=[binary('+',values[i],values[i+1]) if i+1<len(values) else values[i] for i in range(0,len(values),2)]
            return values[0]
        p=step();index=balanced([number(1.)]+[number(0.)]*30)
        p['operations'].append(operation('assign',{'name':'z','value':{'kind':'array_get','name':'a','index':index}}))
        p['operations'].append(operation('assign',{'name':'q','value':balanced([number(0.)]*101)}))
        with self.assertRaisesRegex(ValueError,'128'):validate_step(p)

    def test_implicit_array_indexing_remains_refused_outside_current_loop(self):
        p=step();p['operations'][1]['args']['mode']='implicit'
        p['operations'].append(operation('assign',{'name':'z','value':{'kind':'array_get','name':'a','index':number(1.)}}))
        with self.assertRaises(ValueError):validate_step(p)

    def test_malformed_marker_duplicate_metadata_and_cycles(self):
        for change in ('line','position','duplicate','metadata','cycle'):
            p=step()
            if change=='line':p['operations'][0]['line']=True
            elif change=='position':p['operations'].reverse()
            elif change=='duplicate':p['operations'].append(deepcopy(p['operations'][0]))
            elif change=='metadata':p['display_names']['hidden']=deepcopy(p['operations'][0])
            else:p['display_names']['cycle']=p
            with self.subTest(change=change),self.assertRaises(ValueError):validate_step(p)

    def test_combined_numeric_and_exact_index_depth_has_one_budget(self):
        p=step();index=number(1.)
        for _ in range(24):index=binary('+',index,number(0.))
        value={'kind':'array_get','name':'a','index':index}
        for _ in range(24):value=binary('+',value,number(0.))
        p['operations'].append(operation('assign',{'name':'result','value':value}))
        with self.assertRaisesRegex(ValueError,'32'):validate_step(p)

    def test_hidden_do_over_indexed_write_remains_refused(self):
        p=step();p['operations'][1]['args']['mode']='implicit'
        p['operations'].insert(2,operation('array_declare',{'name':'b','lower':1,'names':['z']}))
        child=operation('array_set',{'name':'b','index':number(1.),'value':{'kind':'array_current','name':'a'}})
        p['operations'].append(operation('do_over',{'name':'a','body':[operation('if',{'condition':{'op':'truth','left':number(1.)},'operation':child})]}))
        with self.assertRaisesRegex(ValueError,'DO OVER'):validate_step(p)

    def test_declaration_order_retention_and_name_collisions(self):
        p=step();p['retained']={'x':number(0.)}
        with self.assertRaises(ValueError):validate_step(p)
        p=step();p['operations'].insert(1,operation('assign',{'name':'before','value':{'kind':'array_sum','name':'a'}}))
        with self.assertRaises(ValueError):validate_step(p)
        p=step();p['operations'][1]['args']['names']=['a','x']
        with self.assertRaises(ValueError):validate_step(p)

    def test_static_index_errors_refuse_even_skipped(self):
        p=step();bad=operation('array_set',{'name':'a','index':number(0.),'value':number(1.)})
        p['operations'].append(operation('if',{'condition':{'op':'truth','left':number(0.)},'operation':bad}))
        with self.assertRaises(ValueError):validate_step(p)
        bad['args']['index']={'kind':'variable','value':'i'}
        self.assertIsNotNone(validate_step(p))

    def test_schema_checks_are_static_and_nonmutating(self):
        p=step();schema={'x':'number','y':'number','trigger':'number'};before=deepcopy((p,schema))
        validate_step(p,schema=schema);self.assertEqual((p,schema),before)
        schema['x']={'type':'character','length':1}
        with self.assertRaises(ValueError):validate_step(p,schema=schema)

    def test_inactive_new_literal_domain_failures_are_static(self):
        p=step();bad=operation('assign',{'name':'bad','value':{'kind':'call','name':'sin','args':[number(4.)]}})
        p['operations'].append(operation('do_while',{'condition':{'op':'truth','left':number(0.)},'body':[bad]}))
        with self.assertRaises(ValueError):validate_step(p)


class NumericPipelineSourceTests(unittest.TestCase):
    def test_three_separate_profiles_and_R_hand_pins(self):
        for mode in ('input','arrays','loops'):
            hand=pins(mode);seen=witnesses([(s,c) for s,c,_ in hand])
            for (source,catalog,expected),witness in zip(hand,seen):
                self.assertEqual(execute(source,catalog,True),expected);self.assertEqual(witness[0],expected)
                profile=compile_plan(source).steps[0].operations[0]
                self.assertEqual(profile.args,{'name':PROFILE})

    def test_complete_measurement_stream_R_runtime_emitted_and_CLI(self):
        source=ORIGINAL.read_text();expected=original_expected()
        self.assertEqual(execute(source,emitted=True),expected)
        independent,accounting=witnesses([(source,{})])[0]
        self.assertEqual(independent,expected)
        self.assertEqual(accounting,{'statements':32,'steps':[{'name':'pipeline','iterations':3,'trips':15},{'name':'fresh','iterations':1,'trips':0}]})
        cli_check(source,expected)

    def test_input_converter_and_eof_contract_are_unchanged(self):
        for token in ('0.1','.A','1e16','1\t2'):
            with self.assertRaises((ValueError,AssertionError)):execute(inline_source([token]))
        table=execute(inline_source(['1','3 99','2 4','7'],names='x den',body='q=x/den;'))['datasets']['d']
        self.assertEqual([r['q'] for r in table['rows']],[1/3,.5])

    def test_empty_and_incomplete_input_still_discovers_array_loop_schema(self):
        source=ORIGINAL.read_text().replace('1 0\n. .\n3 10\n','1\n')
        table=execute(source)['datasets']['pipeline']
        self.assertEqual(table['rows'],[])
        self.assertEqual(list(table['schema']),list(original_expected()['datasets']['pipeline']['schema']))

    def test_while_pretest_until_posttest_and_missing_tests(self):
        for kind,count in (('while',0),('until',1)):
            source=f'data d;trigger=1**1;n=0;do {kind}(n<0);n=n+1;output;end;run;' if kind=='while' else 'data d;trigger=1**1;n=0;do until(n>=0);n=n+1;output;end;run;'
            self.assertEqual(len(execute(source)['datasets']['d']['rows']),count)
        source='data d;trigger=1**1;n=0;do while(.);n=n+1;end;run;'
        self.assertEqual(execute(source)['datasets']['d']['rows'][0]['n'],0.)

    def test_rounded_loop_predicates_Pi_power_trig_and_empty_static_checks(self):
        for source,catalog,expected in pins('loops')[2:]:
            self.assertEqual(execute(source,catalog,True),expected);cli_check(source,expected)
        for kind in ('while','until'):
            empty=f'data d;input x;do {kind}(x<constant("pi"));x=x+1;end;datalines;\n;\nrun;'
            self.assertEqual(execute(empty)['datasets']['d'],{'schema':{'x':'number'},'rows':[]})
            self.assertEqual(witnesses([(empty,{})])[0][0],execute(empty))
            invalid=empty.replace('x<constant("pi")','sin(4)>0')
            with self.assertRaises((ValueError,AssertionError)):execute(invalid)
            self.assertEqual(witnesses([(invalid,{})]),[None])

    def test_conditional_loop_budget_preserves10000_and_refuses10001(self):
        template='data d;trigger=1**1;n=0;do while(n<LIMIT);n=n+1;end;run;'
        self.assertEqual(execute(template.replace('LIMIT','10000'))['datasets']['d']['rows'][0]['n'],10000.)
        with self.assertRaises(ValueError):execute(template.replace('LIMIT','10001'))

    def test_dynamic_index_laziness_and_exact_subscript_grammar(self):
        source='data d;array a{2} x y;trigger=1**1;i=0;if 0 then a{i}=1/3;run;'
        execute(source)
        with self.assertRaises(ValueError):execute(source.replace('if 0 then ',''))
        with self.assertRaises((ValueError,AssertionError)):execute(source.replace('a{i}','a{1/1}'))

    def test_original_retained_import_collision_scratch_and_snapshot_masks(self):
        rows=execute(ORIGINAL.read_text())['datasets']['pipeline']['rows']
        self.assertEqual(rows[2]['total'],0.)
        self.assertEqual(rows[2]['accumulated'],rows[1]['accumulated'])
        self.assertIsNone(rows[2]['early']);self.assertIsNone(rows[2]['rolling'])
        self.assertIsNone(rows[4]['early']);self.assertEqual(len(rows),6)

    def test_array_sum_all_missing_differs_from_retained_sum(self):
        table=execute('data d;array a{2} x y;trigger=1**1;s=sum(of a{*});total+s;run;')['datasets']['d']
        self.assertIsNone(table['rows'][0]['s']);self.assertEqual(table['rows'][0]['total'],0.)

    def test_older_markers_and_exact_array_contract_stay_strict(self):
        source='data d;array a{2} x y;x=.1;y=.2;s=sum(of a{*});run;'
        with self.assertRaises(ValueError):execute(source)
        pipeline=compile_plan(source.replace('x=.1;','trigger=1**1;x=.1;')).to_dict()
        for marker in ('binary64-v1','binary64-rows-v1'):
            forged=deepcopy(pipeline);forged['steps'][0]['operations'][0]['args']['name']=marker
            with self.assertRaises(ValueError):run_plan(forged)

    def test_supplied_set_keeps_eager_domain_and_array_scratch_contract(self):
        source='data d;array a{2} first second;set raw;trigger=1**1;a{1}=x/3;s=sum(of a{*});run;'
        raw={'raw':{'schema':{'x':'number'},'rows':[{'x':1.},{'x':2.}]}}
        rows=execute(source,raw)['datasets']['d']['rows'];self.assertEqual([r['s'] for r in rows],[1/3,2/3])
        raw['raw']['schema']['bad']='number'
        for row in raw['raw']['rows']:row['bad']=2147483648.
        with self.assertRaises(ValueError):execute(source,raw)

    def test_failures_publish_no_accepted_partial_result_or_stdout(self):
        source='data earlier;x=1;put x;run;'+inline_source(['1','2'],body='q=1/(2-x);put q;')
        job=build_job(source);self.assertNotEqual(job.code,0);self.assertIsNone(job.result);self.assertFalse(job.receipt['accepted'])
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(source).code,{})
        self.assertEqual(stream.getvalue(),'')

    def test_no_new_function_or_domain_or_loop_nesting_is_admitted(self):
        for body in ('x=sqrt(4);','x=log(2);','x=sin(4);','do while(0);do until(1);end;end;'):
            with self.assertRaises((ValueError,AssertionError)):execute(inline_source(['1'],body=body))

    def test_R_word_comparators_never_split_truth_identifiers(self):
        prefix='data d;array a{1} x;trigger=1**1;'
        cases=[]
        for name in ('sequel','money','altitude','ledger','longterm','edge','within','sinus','atan_value','input_value','arrayed'):
            for value in ('1','.'):
                cases.append(prefix+name+'='+value+';if '+name+' then output;run;')
        for operator in ('eq','ne','lt','le','gt','ge','^=','~=','<>'):
            cases.append(prefix+'money=1;if money '+operator+' 0 then output;run;')
        seen=witnesses([(source,{}) for source in cases])
        for source,result in zip(cases,seen):
            self.assertIsNotNone(result,source);self.assertEqual(execute(source),result[0],source)

    def test_R_inherited_INT_ELSE_whitespace_bounds_and_computed_controls(self):
        prefix='data d;array a{1} x;trigger=1**1;'
        cases=[prefix+'x=int(1.5);run;',prefix+'q=1.5;x=int(q);run;',
            prefix+'if 0 then x=2/3;else x=1/3;run;',
            'data\td;array a{1} x;trigger=1**1;x=1/3;run;',
            'data d;array a{-1:0} x y;trigger=1**1;a{-1}=1/3;run;',
            prefix+'n=2;do i=1 to n;x=i/3;end;run;',
            'data d;array a{1024} x1-x1024;trigger=1**1;s=sum(of a{*});run;']
        seen=witnesses([(source,{}) for source in cases])
        for source,result in zip(cases,seen):
            self.assertIsNotNone(result,source);self.assertEqual(execute(source),result[0],source)

    def test_R_predeclared_SET_array_members_keep_typed_source_metadata(self):
        source='data d;array a{2} x y;set raw;trigger=1**1;y=x/3;s=sum(of a{*});run;'
        supplied={'raw':{'encoding':'ascii','label':'numeric input',
            'schema':{'x':{'type':'number','length':8,'label':'X source'},'z':'number'},
            'rows':[{'x':3.,'z':9.},{'x':6.,'z':10.}]}}
        independent=witnesses([(source,supplied)])[0]
        self.assertIsNotNone(independent)
        self.assertEqual(execute(source,supplied,True),independent[0])
        self.assertEqual(independent[0]['datasets']['d']['schema']['x'],supplied['raw']['schema']['x'])
        supplied['raw']['schema']['x'].update(label='',format='')
        printed=source.replace('run;','put x;run;')
        empty_metadata=witnesses([(printed,supplied)])[0]
        self.assertIsNotNone(empty_metadata)
        self.assertEqual(execute(printed,supplied,True),empty_metadata[0])

    def test_eight_actual_cli_expected_table_failures_leave_observed_artifacts(self):
        self.assertEqual(cli_wrong_controls(),8)

    def test_naive_comparator_controls_remain_visible(self):
        self.assertEqual(naive_controls(),9)


if __name__=='__main__':unittest.main()
