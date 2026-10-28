"""Bounded DS-026 translation and runtime evidence. No live SAS capture."""
import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

from examples.verify_do_counted import ORIGINAL_PROGRAM, PINS, REFUSALS
from sas_semantics import sas_do_counted
from saschi.emit_py import translate
from saschi.job import build_job
from saschi.plan import compile_plan
from saschi.rules import load_rulebook, route_statement
from saschi.runtime import run_plan


def execute(source, inputs=None):
    translated = translate(source)
    if translated.blocked:
        raise AssertionError(translated.tickets)
    namespace = {'inputs': inputs or {}}
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        exec(translated.code, namespace)
    return namespace['result'], stream.getvalue()


def job_with_inputs(source, inputs):
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'inputs.json'
        path.write_text(json.dumps(inputs))
        return build_job(source,inputs=path)


class CountedDoTests(unittest.TestCase):
    def test_control_pins(self):
        for controls, expected in PINS:
            self.assertEqual(sas_do_counted(*controls), expected)
        for controls in REFUSALS + [(True,2,1),(1,2,1.0),(1,2,float('inf'))]:
            with self.subTest(controls=controls), self.assertRaises(ValueError):
                sas_do_counted(*controls)

    def test_plan_seam_and_normalized_index(self):
        plan=compile_plan('data d; do InDex=+1 to 3; x=index; put index=; end; run;')
        self.assertFalse(plan.blocked,plan.tickets)
        ops=plan.to_dict()['steps'][0]['operations']
        self.assertEqual(ops[0]['args'],{'name':'index','spec':'number'})
        self.assertEqual(ops[1]['kind'],'do_counted')
        self.assertEqual(ops[1]['args'],{'index':'index','start':1,'stop':3,'by':1,'body':[
            {'kind':'assign','line':1,'args':{'name':'x','value':{'kind':'variable','value':'index'}}},
            {'kind':'put','line':1,'args':{'names':['index']}}]})
        self.assertEqual(plan.steps[0].display_names['index'],'InDex')
        self.assertIn(('do-counted','DS-026',1),plan.matched)

    def test_formerly_refused_literal_loop_is_now_directly_gated(self):
        # This exact source was the legacy emitter's bounded-loop refusal pin.
        result,stdout=execute('data _null_; do i=1 to 3; x=i; end; run;')
        self.assertEqual(result,{'datasets':{},'log':[]})
        self.assertEqual(stdout,'')
        job=build_job('data _null_; do i=1 to 3; x=i; end; run;')
        self.assertTrue(job.receipt['accepted'])
        self.assertEqual(job.result,result)
        result,_=execute('data d; do i=1 to 3; x=i; end; run;')
        self.assertEqual(result['datasets']['d']['rows'],[{'i':4.,'x':3.}])

    def test_do_and_end_scalar_assignment_names_keep_baseline_behavior(self):
        for name in ('do','end'):
            for separator in ('=',' = '):
                source=f'data d; {name}{separator}7; put {name}=; run;'
                result,stdout=execute(source)
                self.assertEqual(result['datasets']['d']['rows'],[{name:7.}])
                self.assertEqual(stdout,name+'=7\n')
                self.assertEqual(route_statement(name+separator+'7'),('unknown',''))
                job=build_job(source)
                self.assertTrue(job.receipt['accepted'])
                self.assertEqual(job.result,result)

    def test_do_and_end_assignments_inside_body_are_ordinary_variables(self):
        result,stdout=execute('data d; do i=1 to 2; end=7; do=9; put end= do=; end; run;')
        self.assertEqual(result['datasets']['d']['rows'],[{'i':3.,'end':7.,'do':9.}])
        self.assertEqual(stdout,'end=7 do=9\nend=7 do=9\n')

    def test_do_and_end_loop_index_identity_is_preserved(self):
        for name in ('do','end'):
            source=f'data d; do {name}=1 to 2; x={name}; end; run;'
            result,_=execute(source)
            self.assertEqual(result['datasets']['d']['rows'],[{name:3.,'x':2.}])
            self.assertTrue(compile_plan(f'data d; do {name}=1 to 2; {name}=7; end; run;').blocked)

    def test_default_step_and_final_index(self):
        result,stdout=execute('data d; total=0; do i=1 to 4; total=total+i; put i= _n_=; end; after=i; run;')
        self.assertEqual(result['datasets']['d']['rows'],[{'total':10.,'i':5.,'after':5.}])
        self.assertEqual(stdout,'i=1 _n_=1\ni=2 _n_=1\ni=3 _n_=1\ni=4 _n_=1\n')

    def test_descending_and_explicit_snapshots(self):
        result,_=execute(ORIGINAL_PROGRAM)
        self.assertEqual(result['datasets']['counted']['rows'],[
            {'total':5.,'i':5.,'seen':1.},{'total':8.,'i':3.,'seen':1.},
            {'total':9.,'i':1.,'seen':1.},{'total':8.,'i':-1.,'seen':1.}])

    def test_zero_trip_still_compiles_schema_and_sets_index(self):
        result,stdout=execute("data d; do i=4 to 1; c='abc'; x=9; put 'hidden'; end; after=i; run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'i':4.,'c':'   ','x':None,'after':4.}])
        self.assertEqual(result['datasets']['d']['schema']['c'],{'type':'character','length':3})
        self.assertEqual(stdout,'')

    def test_zero_trip_output_suppresses_implicit_output(self):
        result,_=execute('data d; do i=4 to 1; x=1; output; end; run;')
        self.assertEqual(result['datasets']['d']['rows'],[])
        self.assertEqual(list(result['datasets']['d']['schema']),['i','x'])

    def test_equal_bound_and_sequential_loops(self):
        result,_=execute('data d; do i=2 to 2 by -3; x=i; end; do j=-1 to 1; y=j; end; run;')
        self.assertEqual(result['datasets']['d']['rows'],[{'i':-1.,'x':2.,'j':2.,'y':1.}])

    def test_character_and_literal_put_in_body(self):
        result,stdout=execute("data _null_; do i=1 to 2; c=' hi '; put '[' c ']'; put 'ok'; end; run;")
        self.assertEqual(result['log'],['[hi ]','ok','[hi ]','ok'])
        self.assertEqual(stdout,'[hi ]\nok\n[hi ]\nok\n')

    def test_set_n_counts_data_iterations(self):
        inputs={'a':{'schema':{'x':'number'},'rows':[{'x':10.},{'x':20.}]}}
        result,stdout=execute('data d; set a; do i=1 to 2; seen=_n_; x=x+1; output; end; run;',inputs)
        self.assertEqual(result['datasets']['d']['rows'],[
            {'x':11.,'i':1.,'seen':1.},{'x':12.,'i':2.,'seen':1.},
            {'x':21.,'i':1.,'seen':2.},{'x':22.,'i':2.,'seen':2.}])
        self.assertEqual(stdout,'')

    def test_set_index_column_is_overwritten_and_next_input_is_read(self):
        inputs={'a':{'schema':{'i':'number','x':'number'},'rows':[{'i':70.,'x':5.},{'i':80.,'x':9.}]}}
        result,_=execute('data d; set a; before=i; do I=1 to 2; x=x+i; end; run;',inputs)
        self.assertEqual(result['datasets']['d']['rows'],[
            {'i':3.,'x':8.,'before':70.},{'i':3.,'x':12.,'before':80.}])

    def test_empty_and_filtered_input_keep_loop_body_schema(self):
        for rows in ([],[{'x':1.}]):
            result,_=execute("data d; set a; where x=9; do i=1 to 2; c='xx'; end; run;",
                {'a':{'schema':{'x':'number'},'rows':rows}})
            self.assertEqual(list(result['datasets']['d']['schema']),['x','i','c'])
            self.assertEqual(result['datasets']['d']['rows'],[])

    def test_character_index_refuses_even_on_empty_input(self):
        for source,inputs in [("data d; length i $3; do i=1 to 2; end; run;",{}),
            ('data d; set a; do i=1 to 2; end; run;',{'a':{'schema':{'i':{'type':'character','length':3}},'rows':[]}})]:
            job=job_with_inputs(source,inputs)
            self.assertEqual(job.code,1)
            self.assertIsNone(job.result)

    def test_boundaries_and_preexecution_refusal(self):
        result,_=execute('data d; do i=1 to 10000; end; run;')
        self.assertEqual(result['datasets']['d']['rows'],[{'i':10001.}])
        for header in ('i=0 to 10000','i=10000 to 0 by -1','i=1 to 2 by 0',
                       'i=2147483648 to 2147483648','i=1 to 2 by 2147483648',
                       'i=1.0 to 2','i=1e0 to 2','i=1 to 2 while(1)',
                       'i=1 to 2 until(1)','i=1,2','i=١ to ٢','K=1 to 2',
                       '_n_=1 to 2','_file_=1 to 2','i='+'9'*5000+' to 1'):
            with self.subTest(header=header):
                job=build_job("data d; put 'before'; do "+header+"; put 'body'; end; run;")
                self.assertEqual(job.code,2)
                self.assertIsNone(job.result)

    def test_unsupported_bodies_refuse(self):
        for body in ('I=5','i=round(3,1)','if 1 then i=3','if 1',
                     'do while(1); end','leave','continue',
                     'length x $3','retain x 0','set a','merge a b','where x=1','put _all_',
                     'output other','file log','input x'):
            with self.subTest(body=body):
                self.assertTrue(compile_plan('data d; do i=1 to 2; '+body+'; end; run;').blocked)

    def test_formerly_refused_A2_controls_and_nested_body_are_now_verified(self):
        # Preserve every promoted refusal source with stronger execution assertions.
        for header in ('i=1 to x', 'i=x to 2', 'i=1 to 2 by x'):
            source = "data d; put 'before'; do " + header + "; put 'body'; end; run;"
            job = build_job(source)
            self.assertEqual(job.code, 1)  # Uninitialized dynamic control, atomic.
            self.assertIsNone(job.result)
        source = "data d; put 'before'; do i=1 to 2 by 1+1; put 'body'; end; run;"
        result, printed = execute(source)
        self.assertEqual(result, {'datasets': {'d': {'schema': {'i': 'number'},
                         'rows': [{'i': 3.}]}}, 'log': ['before', 'body']})
        self.assertEqual(printed, 'before\nbody\n')
        result, printed = execute('data d; do i=1 to 2; do j=1 to 2; x=1; end; end; run;')
        self.assertEqual(result['datasets']['d']['rows'], [{'i': 3., 'j': 3., 'x': 1.}])
        self.assertEqual(printed, '')

    def test_formerly_refused_conditional_body_is_now_verified(self):
        # Preserve the exact old source as a value assertion under DS-031.
        result,printed=execute('data d; do i=1 to 2; if 1 then x=3; end; run;')
        self.assertEqual(result['datasets']['d']['rows'],[{'i':3.,'x':3.}])
        self.assertEqual(printed,'')

    def test_unbalanced_groups_refuse(self):
        for tail in ('run;','quit;','data e; x=1; run;','proc sort data=a; by x; run;','proc print; run;',''):
            self.assertTrue(compile_plan('data d; do i=1 to 2; x=1; '+tail).blocked,tail)
        for source in ('data d; end; run;','data d; do i=1 to 2; end; end; run;',
                       'data d; do i=1 to 2; end x; run;'):
            self.assertTrue(compile_plan(source).blocked)

    def test_null_output_and_put_all_contract_stay_closed(self):
        for body in ('do i=1 to 2; output; end','output; do i=1 to 2; end',
                     'do i=1 to 2; end; output','do i=1 to 2; end; put _all_'):
            self.assertTrue(compile_plan('data _null_; '+body+'; run;').blocked)

    def test_macro_guard_sees_nested_put(self):
        for source in ("data d; unused=\"&x\"; do i=1 to 2; c='a'; put c; end; run;",
                       'data d; do i=1 to 2; c="%x"; put c; end; run;'):
            self.assertTrue(compile_plan(source).blocked)

    def test_zero_trip_descriptor_validation_and_atomic_failure(self):
        source="data d; put 'before'; do i=2 to 1; put c; end; run;"
        # Catalog-free uninitialized PUT remains a compiler refusal.
        self.assertTrue(compile_plan(source).blocked)
        source="data d; set a; put 'before'; do i=2 to 1; put c; end; run;"
        inputs={'a':{'schema':{'c':{'type':'character','length':2,'format':'$2.'}},'rows':[]}}
        self.assertEqual(job_with_inputs(source,inputs).code,1)
        source="data d; put 'before'; do i=1 to 2; c=' '; put c; end; run;"
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):
            exec(translate(source).code,{})
        self.assertEqual(stream.getvalue(),'')
        self.assertIsNone(build_job(source).result)

    def test_runtime_revalidates_controls_and_body(self):
        original=compile_plan('data d; do i=1 to 2; x=i; end; run;').to_dict()
        for mutation in ('zero','large','type','write','nested','condition','declare','index','args','missing-declare'):
            plan=deepcopy(original); ops=plan['steps'][0]['operations']; args=ops[1]['args']
            if mutation == 'zero': args['by']=0
            elif mutation == 'large': args['stop']=10001
            elif mutation == 'type': args['start']=True
            elif mutation == 'write': args['body'][0]['args']['name']='i'
            elif mutation == 'nested': args['body']=[deepcopy(ops[1])]
            elif mutation == 'condition': args['body']=[{'kind':'subset','line':1,'args':{'condition':{}}}]
            elif mutation == 'declare': args['body']=[deepcopy(ops[0])]
            elif mutation == 'index': args['index']='_n_'
            elif mutation == 'args': args['unexpected']=0
            else: ops.pop(0)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                run_plan(plan)

    def test_cpp_refuses_loop(self):
        job=build_job('data _null_; do i=1 to 2; put i=; end; run;',target='cpp')
        self.assertEqual(job.code,2)
        self.assertIsNone(job.result)

    def test_rule_and_gate_registration(self):
        self.assertEqual(route_statement('do i=1 to 2'),('do-counted','DS-026'))
        self.assertIn('verify_do_counted.py',load_rulebook()['DS-026'].validation_test)


if __name__ == '__main__':
    unittest.main()
