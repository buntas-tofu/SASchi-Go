"""DS-032 bounded execution/refusal evidence for maintainers, no live SAS."""
import contextlib
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from examples.verify_bitwise import PINS, refusals, program_state
from sas_semantics import (sas_bitwise, sas_band, sas_bor, sas_bxor, sas_bnot,
                           sas_blshift, sas_brshift, sas_put_all)
from .emit_py import translate
from .functions import FUNCTIONS, validate_bitwise_calls
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .test_parser import ROKU_CORPUS

SOURCE_SHA256='e774418156723a8c2aa8f6a2e6b9fac9f6c258a87ee1aff13502b8a654584799'
HELPERS={'band':sas_band,'bor':sas_bor,'bxor':sas_bxor,'bnot':sas_bnot,
         'blshift':sas_blshift,'brshift':sas_brshift}


def execute(source,inputs=None):
    plan=compile_plan(source)
    if plan.blocked:raise AssertionError(plan.tickets)
    return run_plan(plan.to_dict(),inputs)


class BitwiseTests(unittest.TestCase):
    def test_original_pins_and_named_helpers(self):
        for name,args,expected in PINS:
            with self.subTest(name=name,args=args):
                self.assertEqual(sas_bitwise(name,*args),expected)
                self.assertEqual(HELPERS[name](*args),expected)
                self.assertIs(type(HELPERS[name](*args)),int)

    def test_unsigned32_identity_and_each_shift_boundary(self):
        for value in (0,1,2147483647,2147483648,4294967295):
            self.assertEqual(sas_bnot(sas_bnot(value)),value)
            self.assertEqual(sas_band(value,4294967295),value)
            self.assertEqual(sas_bor(value,0),value)
            self.assertEqual(sas_bxor(value,value),0)
            for count in range(32):
                self.assertEqual(sas_blshift(value,count),(value*2**count)%2**32)
                self.assertEqual(sas_brshift(value,count),value//2**count)

    def test_typed_range_and_arity_refusals(self):
        for name,args,_ in refusals():
            with self.subTest(name=name,args=str(args)[:80]),self.assertRaisesRegex(ValueError,'bitwise'):
                sas_bitwise(name,*args)

    def test_dispatch_rejects_non_string_or_unknown_names(self):
        for name in (None,True,[],{},'BAND'):
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'bitwise'):
                sas_bitwise(name,1,1)

    def test_registry_arity_and_gate_provenance(self):
        for name,helper in HELPERS.items():
            spec=FUNCTIONS[name]
            self.assertEqual(spec.returns,'number')
            self.assertEqual(spec.gate,'examples/verify_bitwise.py')
            self.assertEqual((spec.min_args,spec.max_args),(1,1) if name=='bnot' else (2,2))

    def test_synthetic_program_runs_all_six_calls(self):
        source='data d; a=7; b=12; c=band(a,b); d=bor(a,b); e=bxor(a,b); f=bnot(a); g=blshift(a,2); h=brshift(b,2); run;'
        table=execute(source)['datasets']['d']
        self.assertEqual(table['schema'],{name:'number' for name in 'abcdefgh'})
        self.assertEqual(table['rows'],[dict(zip('abcdefgh',[7.,12.,4.,15.,11.,4294967288.,28.,3.]))])

    def test_calls_compose_with_numeric_calls_arithmetic_and_predicates(self):
        source='data d; x=bor(band(12,10),1)+1; y=max(bnot(4294967295),3); if brshift(2147483648,31)=1 then flag=1; run;'
        self.assertEqual(execute(source)['datasets']['d']['rows'],[{'x':10.,'y':3.,'flag':1.}])

    def test_function_shaped_variable_names_keep_numeric_identity(self):
        self.assertEqual(execute('data d; band=5; bnot=band; x=band(bnot,3); run;')['datasets']['d']['rows'],
                         [{'band':5.,'bnot':5.,'x':1.}])

    def test_dynamic_numeric_columns_and_unsigned_results(self):
        inputs={'raw':{'schema':{'a':'number','s':'number'},'rows':[{'a':0,'s':31},{'a':2147483648,'s':1}]}}
        table=execute('data d; set raw; x=bnot(a); y=brshift(a,s); run;',inputs)['datasets']['d']
        self.assertEqual(table['rows'],[{'a':0.,'s':31.,'x':4294967295.,'y':0.},
                                        {'a':2147483648.,'s':1.,'x':2147483647.,'y':1073741824.}])

    def test_empty_numeric_input_retains_schema(self):
        table=execute('data d; set raw; x=band(a,1); run;',{'raw':{'schema':{'a':'number'},'rows':[]}})['datasets']['d']
        self.assertEqual(table,{'schema':{'a':'number','x':'number'},'rows':[]})

    def test_where_calls_use_driving_input_and_validate_without_rows(self):
        source='data d; set raw; where band(a,1)=1; run;'
        table=execute(source,{'raw':{'schema':{'a':'number'},'rows':[{'a':2},{'a':3}]}})['datasets']['d']
        self.assertEqual(table['rows'],[{'a':3.}])
        with self.assertRaisesRegex(ValueError,'bitwise'):
            execute(source,{'raw':{'schema':{'a':{'type':'character','length':1}},'rows':[]}})

    def test_character_descriptors_refused_on_empty_and_filtered_inputs(self):
        for rows,predicate in (([],''),([{'a':'Q'}],'where 0;')):
            for expr in ('band(a,1)','blshift(1,a)','bnot(a)'):
                with self.subTest(expr=expr,rows=rows),self.assertRaisesRegex(ValueError,'bitwise'):
                    execute('data d; set raw; '+predicate+' x='+expr+'; run;',
                            {'raw':{'schema':{'a':{'type':'character','length':1}},'rows':rows}})

    def test_static_invalid_literals_refuse_empty_false_and_zero_trip(self):
        for expr in ('band(-1,1)','bnot(4294967296)','bor(.,1)','bxor(.A,1)',
                     "band('1',1)",'blshift(1,32)','brshift(1,1.5)'):
            for prefix,suffix in (('',''),('if 0 then',''),('do i=2 to 1;','end;')):
                source='data d; '+prefix+' x='+expr+'; '+suffix+' run;'
                with self.subTest(source=source),self.assertRaisesRegex(ValueError,'bitwise'):execute(source)
            with self.assertRaisesRegex(ValueError,'bitwise'):
                execute('data d; set raw; where 0; x='+expr+'; run;',{'raw':{'schema':{'a':'number'},'rows':[]}})

    def test_valid_calls_keep_zero_trip_static_schema(self):
        table=execute('data d; do i=2 to 1; x=band(3,1); end; run;')['datasets']['d']
        self.assertEqual(table['schema'],{'i':'number','x':'number'})
        self.assertEqual(table['rows'],[{'i':2.,'x':None}])

    def test_source_call_arity_and_hex_literal_syntax_stay_tickets(self):
        for expr in ('band(1)','bnot(1,2)','brshift(1,1,1)','bor()','band(0Fx,1)'):
            self.assertTrue(compile_plan('data d; x='+expr+'; run;').blocked,expr)

    def test_handwritten_malformed_calls_have_clear_refusals(self):
        for args in ([],None,[{'kind':'number','value':1}],['1','2']):
            with self.assertRaisesRegex(ValueError,'bitwise'):
                validate_bitwise_calls({'kind':'call','name':'band','args':args},{})
        plan=compile_plan('data d; x=band(1,1); run;').to_dict()
        plan['matched']=[];plan['tickets']=[]
        plan['steps'][0]['operations'][0]['args']['value']['args'][0]={'kind':'number','value':-1}
        with self.assertRaisesRegex(ValueError,'bitwise'):run_plan(plan,allow_partial=True)

    def test_safe_small_put_all_calls_preserve_error_zero_contract(self):
        result=execute('data _null_; a=band(7,3); b=bnot(4294967295); put _all_; run;')
        self.assertEqual(result,{'datasets':{},'log':['a=3 b=0 _ERROR_=0 _N_=1 ']})
        for expr in ('bnot(.)','band(1,.A)','blshift(1,32)'):
            self.check_atomic("data prior; put 'earlier'; run; data _null_; x="+expr+'; put _all_; run;')

    def test_late_dynamic_failure_is_atomic_in_emitter_and_job(self):
        source="data prior; put 'earlier'; run; data d; set raw; x=blshift(a,s); put 'row'; output; run;"
        for value in (None,-1,32,1.5,{'missing':'A'}):
            inputs={'raw':{'schema':{'a':'number','s':'number'},'rows':[{'a':1,'s':0},{'a':1,'s':value}]}}
            self.check_atomic(source,inputs)

    def check_atomic(self,source,inputs=None):
        output=io.StringIO();ns={'inputs':inputs or {}}
        with contextlib.redirect_stdout(output),self.assertRaisesRegex(ValueError,'bitwise'):
            exec(translate(source).code,ns)
        self.assertEqual(output.getvalue(),'');self.assertNotIn('result',ns)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'input.json';path.write_text(json.dumps(inputs or {}))
            with contextlib.redirect_stdout(output):job=build_job(source,path)
        self.assertEqual(job.code,1);self.assertIsNone(job.result);self.assertFalse(job.receipt['accepted'])
        self.assertEqual(output.getvalue(),'')

    def test_cpp_remains_outside_bitwise_backend_scope(self):
        self.assertEqual(build_job('data _null_; x=band(7,3); run;',target='cpp').code,2)


class BitwiseControlIntegrationTests(unittest.TestCase):
    def test_all_branch_calls_have_route_and_plan_provenance(self):
        from .rules import route_function
        source='data d; if 0 then x=band(6,3); else if 1 then x=bor(4,1); else x=bxor(3,1); run;'
        plan=compile_plan(source)
        self.assertFalse(plan.blocked,plan.tickets)
        self.assertEqual(route_function('x=bnot(0);'),('bitwise','DS-032'))
        self.assertEqual(sum(item[:2]==('bitwise','DS-032') for item in plan.matched),3)
        self.assertEqual(run_plan(plan.to_dict())['datasets']['d']['rows'],[{'x':5.}])

    def test_conditional_loop_calls_use_current_pdv_values(self):
        source='data d; do i=0 to 3; if mod(i,2)=0 then x=blshift(1,i); else x=bnot(4294967295); output; end; run;'
        self.assertEqual(execute(source)['datasets']['d']['rows'],[
            {'i':float(i),'x':float(value)} for i,value in enumerate((1,0,4,0))])

    def test_skipped_false_branch_literals_validate_on_empty_input(self):
        source='data d; set raw; if 1 then x=band(1,1); else x=brshift(1,32); run;'
        inputs={'raw':{'schema':{'a':'number'},'rows':[]}}
        with self.assertRaisesRegex(ValueError,'bitwise'):
            run_plan(compile_plan(source).to_dict(),inputs)

    def test_handwritten_false_branch_keeps_numeric_validation(self):
        plan=compile_plan('data d; if 1 then x=1; else x=band(1,1); run;').to_dict()
        expr=plan['steps'][0]['operations'][0]['args']['otherwise']['args']['value']
        expr['args'][0]={'kind':'character','value':'1'}
        plan['tickets']=[];plan['matched']=[]
        with self.assertRaisesRegex(ValueError,'bitwise'):
            run_plan(plan,allow_partial=True)


class BitwiseCorpusRefusalTests(unittest.TestCase):
    def test_unmodified_corpus_calls_work_then_width_refuses_atomically(self):
        path=ROKU_CORPUS/'bitwise_operations.sas'
        if not path.is_file():self.skipTest('Roku corpus not present')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),SOURCE_SHA256)
        source=path.read_text();translation=translate(source)
        self.assertFalse(translation.blocked,translation.tickets)
        width,independent=program_state(path)
        self.assertEqual(width,67);self.assertEqual(len(independent),8)
        observed=[]
        def capture(fields):
            observed.append(deepcopy(fields))
            return sas_put_all(fields)
        output=io.StringIO();ns={}
        with patch('saschi.runtime.sas_put_all',side_effect=capture),contextlib.redirect_stdout(output),self.assertRaisesRegex(ValueError,'beyond 64 columns'):
            exec(translation.code,ns)
        self.assertTrue(observed)
        self.assertEqual(observed[-1],independent)
        self.assertEqual(len(''.join(field['name']+'='+str(int(field['value']))+' ' for field in independent)+'_ERROR_=0 _N_=1 '),width)
        self.assertEqual(output.getvalue(),'');self.assertNotIn('result',ns)
        with contextlib.redirect_stdout(output):job=build_job(source)
        self.assertEqual(job.code,1);self.assertIsNone(job.result);self.assertFalse(job.receipt['accepted'])
        self.assertEqual(job.receipt['source_sha256'],SOURCE_SHA256)
        self.assertIn('beyond 64 columns',job.receipt['error']);self.assertEqual(job.receipt['tickets'],[])
        self.assertEqual(output.getvalue(),'')
        print('VERIFIED corpus refusal: bitwise_operations.sas; source hash and independent R PDV agree,67-column PUT_ALL refused atomically under64-column profile; no successful whole-program proof or live SAS')


if __name__=='__main__':unittest.main()
