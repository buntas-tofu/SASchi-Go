"""Typed character trees, contextual bytes and isolated portable execution."""
from copy import deepcopy
import contextlib
import io
import json
import unittest
from examples.verify_expression_characters import GATE
from examples.wave_gate_common import assert_result
from . import function_expressions as ex
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .wave3_test_support import FamilyContract


def source_text(value):return "'"+value.replace("'","''")+"'"


def execute(source,inputs=None):
    plan=compile_plan(source)
    if plan.blocked:raise ValueError(str(plan.tickets))
    return run_plan(plan.to_dict(),inputs)


class CharacterExpressionTests(unittest.TestCase):
    atomic_cli=FamilyContract.atomic_cli

    def original(self):return compile_plan(GATE.source.read_text()).to_dict()

    def test_complete_hand_and_independent_R_original(self):
        wanted=GATE.program_witness();inputs=json.loads(GATE.inputs.read_text());saved=deepcopy(inputs)
        plan=self.original();copy=deepcopy(plan)
        assert_result(run_plan(plan,inputs),wanted)
        self.assertEqual((inputs,plan),(saved,copy))
        self.assertEqual(plan['steps'][0]['operations'][0]['args'],{'profile':ex.PROFILE})
        self.assertIn(('character-expressions','DS-116',1),compile_plan(GATE.source.read_text()).matched)

    def test_generated_pair_trees_match_independent_R_temporaries(self):
        names=('upcase','lowcase','strip','trim','trimn','compbl','dequote','propcase')
        seeds=(' ',' A  b ','"A"','a-b',"a'b",'  q','Z9','""')
        inner=[(name,[seed]+([' -'] if name=='propcase' else [])) for name in names for seed in seeds]
        values=GATE.r_cases(inner)
        cases=[];sources=[];widths=[]
        for (name,args),value in zip(inner,values):
            child=name+'('+','.join(map(source_text,args))+')'
            for outer in names:
                cases.append((outer,[value]+([' -'] if outer=='propcase' else [])))
                sources.append('data d;x='+outer+'('+child+(",' -'" if outer=='propcase' else '')+');run;')
                widths.append(len(args[0]))
        for source,wanted,width in zip(sources,GATE.r_cases(cases),widths):
            result=execute(source)['datasets']['d']
            self.assertEqual(result['schema']['x'],{'type':'character','length':width},source)
            self.assertEqual(result['rows'],[{'x':wanted.ljust(width)}],source)

    def test_four_call_levels_and_multiple_nested_items(self):
        row=execute("data d;x=cats(substrn(upcase(strip(' abcd ')),1,3),'-',propcase(strip(' a-b '),' -'));run;")['datasets']['d']['rows'][0]
        self.assertEqual(row['x'],'ABC-A-B'.ljust(200))
        source="data d;x=upcase(lowcase(compbl(strip(dequote('a')))));run;"
        self.assertTrue(compile_plan(source).blocked)

    def test_empty_temporaries_remain_distinct_from_one_blank(self):
        row=execute("data d;x=transtrn('a-b','-',trimn(' '));y=transtrn('a-b','-',trim(' '));z=catx('|',upcase(trimn(' ')),'Z');run;")['datasets']['d']['rows'][0]
        self.assertEqual(row,{'x':'ab'.ljust(200),'y':'a b'.ljust(200),'z':'Z'.ljust(200)})

    def test_empty_input_retains_complete_metadata_and_descriptors(self):
        inputs=json.loads(GATE.inputs.read_text());inputs['raw']['rows']=[]
        result=run_plan(self.original(),inputs)
        table=result['datasets']['char_trees'];self.assertEqual(table['rows'],[])
        self.assertEqual(table['schema'],json.loads(GATE.expected.read_text())['datasets']['char_trees']['schema'])
        self.assertEqual(table['label'],'Original composition cases')
        inputs['raw']['schema']['label']='number'
        with self.assertRaises(ValueError):run_plan(self.original(),inputs)

    def test_skipped_dynamic_buffer_is_lazy_but_literals_are_checked(self):
        source="data d;set raw;if 0 then x=cats(upcase(strip(label)),'Z');run;"
        inputs={'raw':{'schema':{'label':{'type':'character','length':300}},'rows':[{'label':'a'*250}]}}
        result=execute(source,inputs);self.assertEqual(result['datasets']['d']['rows'][0]['x'],' '*200)
        bad="data d;if 0 then x=cats(upcase("+source_text('a'*200)+"),'Z');run;"
        self.assertTrue(compile_plan(bad).blocked)

    def test_late_buffer_fault_has_real_prefix_and_atomic_CLI(self):
        source="data d;set raw;x=cats(upcase(strip(label)),'Z');put x;run;"
        inputs={'raw':{'schema':{'label':{'type':'character','length':300}},'rows':[{'label':'a'},{'label':'a'*200}]}}
        self.atomic_cli(source,inputs,'buffer')

    def test_portable_exact_fields_and_marker_placement(self):
        original=self.original()
        mutations=[]
        p=deepcopy(original);p['version']=True;mutations.append(p)
        p=deepcopy(original);p['extra']=1;mutations.append(p)
        p=deepcopy(original);p['steps'][0]['line']=True;mutations.append(p)
        p=deepcopy(original);p['steps'][0]['operations'].append(deepcopy(p['steps'][0]['operations'][0]));mutations.append(p)
        p=deepcopy(original);p['steps'][0]['operations'].append(p['steps'][0]['operations'].pop(0));mutations.append(p)
        p=deepcopy(original);p['steps'][0]['operations'].pop(0);mutations.append(p)
        p=deepcopy(original);p['steps'][0]['operations'][2]['args']['value']['extra']=1;mutations.append(p)
        p=deepcopy(original);p['steps'][0]['operations'][2]['args']['value']['args']=();mutations.append(p)
        for p in mutations:
            with self.subTest(index=mutations.index(p)),self.assertRaises(ValueError):run_plan(p,{})

    def test_unnecessary_profile_and_unqualified_calls_refuse(self):
        p=compile_plan('data d;x=1;run;').to_dict()
        p['steps'][0]['operations'].insert(0,{'kind':'function_profile','line':1,'args':{'profile':ex.PROFILE}})
        with self.assertRaises(ValueError):run_plan(p)
        for tail in ('x=1*2','x=1/2','x=2**3','if x<>1 then y=1','where x=1','retain x','call missing(x)','array a{1} x'):
            source="data d;canon=upcase(compbl(strip(dequote('a'))));"+tail+';run;'
            self.assertTrue(compile_plan(source).blocked,source)

    def test_source_and_portable_cycles_depth_and_call_budgets(self):
        source="data d;x="+'upcase('*70+"'a'"+')'*70+';run;'
        self.assertTrue(compile_plan(source).blocked)
        p=self.original();p['steps'][0]['operations'][2]['args']['value']['args'].append(p)
        with self.assertRaises(ValueError):run_plan(p,{})
        def builder(n):return 'cats('+','.join("upcase(strip('a'))" for _ in range(n))+')'
        source='data d;x='+builder(31)+';y='+builder(32)+';run;'
        result=execute(source);self.assertEqual(result['datasets']['d']['rows'][0]['x'],'a'.upper()*31+' '*169)
        self.assertTrue(compile_plan(source.replace('run;',"z=upcase('b');run;")).blocked)
        p=self.original();p['steps']=p['steps']*17
        with self.assertRaises(ValueError):run_plan(p,{})
        p=self.original();p['matched']=[['x','DS-116',1]]*4097
        with self.assertRaises(ValueError):run_plan(p,{})

    def test_old_profiles_and_opaque_function_text_are_unchanged(self):
        for source,profile in [("data d;x=upcase(strip(' a '));run;",'function-consumers-v1'),("data d;x=ifn(1,7,largest(1,2,3));run;",'function-consumers-v2')]:
            plan=compile_plan(source);self.assertFalse(plan.blocked,plan.tickets)
            self.assertEqual(plan.to_dict()['steps'][0]['operations'][0]['args'],{'profile':profile})
        source="data _null_;put 'upcase(compbl(strip(dequote(x))))';run;"
        self.assertFalse(ex.claimed(compile_plan(source).to_dict()))

    def test_old_and_new_steps_interoperate_in_both_orders(self):
        new="data fresh;set raw;x=upcase(compbl(strip(dequote(code))));run;"
        old="data prior;set raw;y=upcase(strip(code));run;"
        inputs={'raw':{'schema':{'code':{'type':'character','length':8}},'rows':[{'code':' a  b '}]}}
        for source in (old+new,new+old):
            result=execute(source,inputs)
            self.assertEqual(result['datasets']['fresh']['rows'][0]['x'],'A B'.ljust(8))
            self.assertEqual(result['datasets']['prior']['rows'][0]['y'],'A  B'.ljust(8))

    def test_primitive_numeric_roots_keep_the_frozen_bound(self):
        head="data d;x=upcase(compbl(strip(dequote('a'))));"
        for tail in ('y=1000001;','if 1000001 then y=1;','if 1000001>0 then y=1;','if 0 then y=1000001;'):
            self.assertTrue(compile_plan(head+tail+'run;').blocked,tail)
        source="data d;set raw;x=upcase(compbl(strip(dequote(code))));if flag then hit=1;else hit=0;put hit;run;"
        inputs={'raw':{'schema':{'code':{'type':'character','length':8},'flag':'number'},'rows':[{'code':'a','flag':1},{'code':'b','flag':1000001}]}}
        self.atomic_cli(source,inputs,'numeric')

    def test_static_argument_domains_survive_unknown_siblings_and_empty_input(self):
        from .test_do_counted import job_with_inputs
        inputs={'raw':{'schema':{'label':{'type':'character','length':300},'a':'number','k':'number','flag':'number','unit':'number'},'rows':[]}}
        head='data d;set raw;canon=upcase(compbl(strip(dequote(label))));if 0 then x='
        choices=['largest(k,0.5,a)','modz(1e-100,unit)',"ifc(1000001,label,'N')","ifc(flag,label,'N')","transtrn(label,'-',"+source_text('X'*65)+')',"cats(label,"+source_text('X'*201)+')']
        for rhs in choices:
            self.assertIn(job_with_inputs(head+rhs+';run;',inputs).code,(1,2),rhs)

    def test_conditional_parser_budget_precedes_recursion(self):
        source="data d;x=upcase(compbl(strip(dequote('a'))));"+'if 1 then '*1100+'y=1;run;'
        plan=compile_plan(source);self.assertTrue(plan.blocked)
        self.assertTrue(any('budget' in t.reason for t in plan.tickets))
        self.assertFalse(any('recursion depth' in t.reason for t in plan.tickets))

    def test_position_controls_retain_their_separate_integer_bound(self):
        source="data d;x=upcase(compbl(strip(dequote('a'))));y=substrn(x,2147483647,1);run;"
        row=execute(source)['datasets']['d']['rows'][0]
        self.assertEqual(row,{'x':'A','y':' '})

    def test_portable_declarations_and_read_order_must_match_descriptors(self):
        source="data d;length x $8;canon=upcase(compbl(strip(dequote('a'))));x=canon;run;"
        original=compile_plan(source).to_dict();mutations=[]
        p=deepcopy(original);p['steps'][0]['operations'][1]['args']['spec']['length']=7;mutations.append(p)
        p=deepcopy(original);p['steps'][0]['lengths']['x']=7;mutations.append(p)
        p=deepcopy(original);p['steps'][0]['display_names']['x']='Y';mutations.append(p)
        p=deepcopy(original);p['steps'][0]['operations'].append(p['steps'][0]['operations'].pop(1));mutations.append(p)
        p=deepcopy(original);p['steps'][0]['operations'].pop(1);mutations.append(p)
        for index,p in enumerate(mutations):
            with self.subTest(index=index),self.assertRaises(ValueError):run_plan(p)
        p=self.original();p['steps'][0]['operations'].append(p['steps'][0]['operations'].pop(1))
        with self.assertRaises(ValueError):run_plan(p,json.loads(GATE.inputs.read_text()))

    def test_else_binds_to_nearest_unmatched_IF_at_each_level(self):
        prefix="data d;canon=upcase(compbl(strip(dequote('a'))));"
        for a in (0,1):
            for b in (0,1):
                for c in (0,1):
                    controls=f'a={a};b={b};c={c};'
                    source=prefix+controls+'if a then if b then if c then hit=1;else hit=2;else hit=3;else hit=4;run;'
                    wanted=(1 if c else 2) if a and b else 3 if a else 4
                    self.assertEqual(execute(source)['datasets']['d']['rows'][0]['hit'],wanted,source)
        source=prefix+'if 0 then hit=1;else if 1 then if 0 then hit=2;else hit=3;else hit=4;run;'
        self.assertEqual(execute(source)['datasets']['d']['rows'][0]['hit'],3)
        source=prefix+'if 0 then hit=1;else\n hit=2;put\n canon;run;'
        self.assertEqual(execute(source)['datasets']['d']['rows'][0]['hit'],2)
        self.assertTrue(compile_plan(prefix+'if 0 then hit=1;x=2;else hit=3;run;').blocked)

    def test_PUT_preserves_source_boundaries_and_special_controls(self):
        prefix="data d;canon=upcase(compbl(strip(dequote('a'))));n='X';"
        for tail in ("put 'a'n;","put 'a'/* comment */n;","_all_='X';put _all_;","_file_='X';put _file_;"):
            self.assertTrue(compile_plan(prefix+tail+'run;').blocked,tail)
        self.assertEqual(execute(prefix+"put 'a' n;run;")['log'],['aX '])
        self.assertEqual(execute(prefix+"put 'a' /* comment */n;run;")['log'],['aX '])
        p=compile_plan(prefix+'put n;run;').to_dict();p['steps'][0]['operations'][-1]['args']['items']=[{'kind':'number','value':1}]
        with self.assertRaises(ValueError):run_plan(p)

    def test_LENGTH_preserves_input_labels_formats_and_plain_copy_has_no_format(self):
        inputs={'raw':{'label':'Original metadata','schema':{'code':{'type':'character','length':4,'format':'$UPCASE10.','label':'Identifier'}},'rows':[{'code':'ab'}]}}
        source='data d;length code $2;set raw;canon=upcase(compbl(strip(dequote(code))));run;'
        table=execute(source,inputs)['datasets']['d']
        self.assertEqual(table['schema']['code'],{'type':'character','length':2,'format':'$UPCASE10.','label':'Identifier'})
        self.assertEqual(table['schema']['canon'],{'type':'character','length':2})
        self.assertEqual(table['label'],'Original metadata')
        for rows in ([],[{'code':'ab'}]):
            inputs['raw']['rows']=rows
            from .test_do_counted import job_with_inputs
            bad=source.replace('run;','put code;run;')
            self.assertEqual(job_with_inputs(bad,inputs).code,1)
            self.assertEqual(job_with_inputs(source.replace('run;','put canon;run;'),inputs).code,0)

    def test_PUT_static_buffers_validate_on_empty_input(self):
        from .test_do_counted import job_with_inputs
        inputs={'raw':{'schema':{'code':{'type':'character','length':4},'num':{'type':'number','format':'8.2'}},'rows':[]}}
        prefix='data d;set raw;canon=upcase(compbl(strip(dequote(code))));'
        for tail in ("put "+source_text('X'*65)+';','put num;'):
            self.assertEqual(job_with_inputs(prefix+tail+'run;',inputs).code,1,tail)

    def test_actual_emission_and_Cpp_refusal(self):
        source=GATE.source.read_text();inputs=json.loads(GATE.inputs.read_text())
        stream=io.StringIO();scope={'inputs':inputs}
        with contextlib.redirect_stdout(stream):exec(translate(source).code,scope)
        assert_result(scope['result'],json.loads(GATE.expected.read_text()))
        self.assertEqual(stream.getvalue(),''.join(x+'\n' for x in scope['result']['log']))
        self.assertEqual(translate(source).code,translate(source).code)
        self.assertEqual(build_job(source,target='cpp').code,2)


if __name__=='__main__':unittest.main()
