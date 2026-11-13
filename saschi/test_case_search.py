"""DS-096 source, portable, descriptor, scheduling and atomicity boundaries."""
import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import unittest

from examples.verify_case_search import ORIGINAL,INPUTS,EXPECTED,qualify
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .test_do_counted import execute,job_with_inputs


def catalog(values,width=4,spec=None):
    return {'raw':{'schema':{'a':spec or {'type':'character','length':width}},'rows':[{'a':v} for v in values]}}


class CaseSearchTests(unittest.TestCase):
    def test_original_hand_and_independent_r(self):
        qualify()
        result,stdout=execute(ORIGINAL.read_text(),json.loads(INPUTS.read_text()))
        self.assertEqual(result,json.loads(EXPECTED.read_text()))
        self.assertEqual(stdout,''.join(x+'\n' for x in result['log']))

    def test_new_source_provenance(self):
        plan=compile_plan("data d;x=upcase('a');run;")
        self.assertFalse(plan.blocked,plan.tickets)
        self.assertIn(('case-search','DS-096',1),plan.matched)

    def test_width_inheritance_existing_destination_and_blanks(self):
        result,_=execute("data d;length a $5;length b $2;a=' Ab ';b=upcase(a);c=lowcase(a);run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':' Ab  ','b':' A','c':' ab  '}])
        self.assertEqual(result['datasets']['d']['schema']['c'],{'type':'character','length':5})
        result,_=execute("data d;a=upcase('   ');b=lowcase(' ');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':'   ','b':' '}])

    def test_input_descriptor_and_metadata_order(self):
        spec={'type':'character','length':4,'label':'Original','format':'$CHAR4.'}
        result,_=execute('data d;set raw;b=upcase(a);run;',catalog([' x '],spec=spec))
        self.assertEqual(result['datasets']['d']['schema'],{'a':spec,'b':{'type':'character','length':4}})
        self.assertEqual(result['datasets']['d']['rows'],[{'a':' x  ','b':' X  '}])

    def test_search_positions_and_preserved_needle_padding(self):
        result,_=execute("data d;length a $4;length needle $2;a='ab';needle='b';p=index(a,needle);q=find(a,needle,'T');n=index(a,'z');run;")
        row=result['datasets']['d']['rows'][0]
        self.assertEqual((row['p'],row['q'],row['n']),(2.,2.,0.))
        result,_=execute("data d;p=index('ab','b ');q=find('ab','b ','T');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'p':0.,'q':2.}])

    def test_forward_start_both_orders_zero_and_beyond_end(self):
        result,_=execute("data d;a=find('AB AB','ab','I',2);b=find('AB AB','ab',2,'I');c=find('a','a',0);d=find('a','a',2147483647);run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':4.,'b':4.,'c':0.,'d':0.}])

    def test_empty_input_and_skipped_assignment_preserve_schema(self):
        result,_=execute('data d;set raw;if 0 then b=upcase(a);run;',catalog([]))
        self.assertEqual(result['datasets']['d'],{'schema':{'a':{'type':'character','length':4},'b':{'type':'character','length':4}},'rows':[]})
        result,_=execute('data d;set raw;if 0 then b=upcase(a);run;',catalog(['é']))
        self.assertEqual(result['datasets']['d']['rows'],[{'a':'é  ','b':'    '}])

    def test_static_types_and_literals_refuse_on_unreached_paths(self):
        sources=["data d;if 0 then x=upcase(1);run;","data d;if 0 then x=upcase('');run;",
                 "data d;if 0 then x=find('a','a','Q');run;","data d;if 0 then x=find('a','a',-1);run;",
                 "data d;if 0 then x=find('a',' ','T');run;","data d;if 0 then x=upcase(a);a='a';run;"]
        for source in sources:
            with self.subTest(source=source):self.assertIn(build_job(source).code,(1,2))
        for rows in ([],[1]):
            self.assertEqual(job_with_inputs('data d;set raw;if 0 then b=upcase(a);run;',catalog(rows,spec='number')).code,1)

    def test_nested_and_other_consumers_refuse(self):
        for source in ["data d;a=lowcase(upcase(trim(strip('a'))));run;","data d;a=length(upcase('a'));run;",
                       "data d;a=upcase('a')||'b';run;","data d;if index('a','a') then x=1;run;",
                       "data d;set raw;where index(a,'a');run;","data d;retain n 0;x=upcase('a');run;",
                       "data d;array x a;b=upcase('a');run;","data d;x=upcase('a');put _all_;run;",
                       "data d;x=find('ab','a',position);run;"]:
            with self.subTest(source=source):self.assertIn(build_job(source).code,(1,2))

    def test_prior_length_after_set_boundary_remains(self):
        prior=ORIGINAL.read_text().replace('  length short $3;\n  set raw;','  set raw;\n  length short $3;')
        plan=compile_plan(prior)
        self.assertTrue(plan.blocked)
        self.assertTrue(any(t.construct=='length' for t in plan.tickets))

    def test_simple_if_and_counted_snapshots(self):
        result,_=execute("data d;length a $2;a='a';do i=1 to 2;if i=1 then b=upcase(a);else b=lowcase(a);output;end;run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':'a ','i':1.,'b':'A '},{'a':'a ','i':2.,'b':'a '}])
        result,_=execute("data d;a=upcase('a');if 0 then output;run;")
        self.assertEqual(result['datasets']['d']['rows'],[])

    def test_source_guards_ignore_function_shaped_literals(self):
        self.assertEqual(build_job("data d;x='upcase(a)';unused='é';run;").code,0)
        for suffix in ('unused="&name";','unused="%call(x)";',"unused='é';"):
            self.assertEqual(build_job("data d;x=upcase('a');"+suffix+'run;').code,2)
        self.assertEqual(build_job("data d;x=upcase('&name %call');run;").code,0)

    def test_portable_call_shapes_and_versions(self):
        original=compile_plan("data d;x=upcase('a');run;").to_dict()
        for args in (None,(),{},[],[{}],[{'kind':'character','value':'a','extra':0}],[{'kind':'variable','value':'_n_'}],[{'kind':'number','value':True}]):
            plan=deepcopy(original);plan['steps'][0]['operations'][0]['args']['value']['args']=args
            with self.subTest(args=args),self.assertRaises(ValueError):run_plan(plan)
        plan=deepcopy(original);plan['version']=1
        with self.assertRaises(ValueError):run_plan(plan)
        plan=deepcopy(original);plan['steps'][0]['operations'][0]['args']['value']['extra']=0
        with self.assertRaises(ValueError):run_plan(plan)

    def test_late_failure_publishes_no_result_or_stdout(self):
        source='data d;set raw;b=upcase(a);put b;output;run;'
        inputs=catalog(['OK','é'])
        job=job_with_inputs(source,inputs)
        self.assertEqual(job.code,1);self.assertIsNone(job.result);self.assertFalse(job.receipt['accepted'])
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(source).code,{'inputs':inputs})
        self.assertEqual(stream.getvalue(),'')

    def test_row_scratch_reset_and_caller_nonmutation(self):
        source='data d;set raw;if 0 then before=upcase(a);b=lowcase(a);output;run;'
        inputs=catalog(['A','B']);before=deepcopy(inputs);plan=compile_plan(source).to_dict();saved=deepcopy(plan)
        result=run_plan(plan,inputs)
        self.assertEqual([r['before'] for r in result['datasets']['d']['rows']],['    ','    '])
        self.assertEqual(inputs,before);self.assertEqual(plan,saved);self.assertEqual(run_plan(plan,inputs),result)

    def test_cpp_refuses(self):
        self.assertEqual(build_job("data _null_;x=upcase('a');run;",target='cpp').code,2)

    def test_preexisting_array_names_remain_available(self):
        for name in ('upcase','lowcase','index','find'):
            result,_=execute(f'data d;array {name} a b;a=1;b=2;x={name}[2];run;')
            self.assertEqual(result['datasets']['d']['rows'],[{'a':1.,'b':2.,'x':2.}])
            self.assertIn(build_job(f"data d;array {name} a b;x={name}('a');run;").code,(1,2))

    def test_new_profile_budget_does_not_change_legacy_admission(self):
        old=compile_plan('data d;x=1;run;').to_dict()
        old['steps'][0]['operations']*=20001
        self.assertEqual(run_plan(old)['datasets']['d']['rows'],[{'x':1.}])
        selected=compile_plan("data d;x=upcase('a');run;").to_dict()
        selected['steps'][0]['operations']*=6000
        with self.assertRaisesRegex(ValueError,'container budget'):run_plan(selected)


if __name__=='__main__':unittest.main()
