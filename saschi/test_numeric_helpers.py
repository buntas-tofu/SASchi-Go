"""DS-100 fuzz boundaries, typed numeric inputs and atomic source execution."""
from copy import deepcopy
import json
import math
import unittest

from examples.verify_numeric_helpers import GATE,REFUSALS
from sas_semantics import sas_abs,sas_sign,sas_ceil,sas_floor
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .rules import route_function
from .test_do_counted import execute,job_with_inputs


class NumericHelperTests(unittest.TestCase):
    def test_independent_original_and_complete_formatted_records(self):
        GATE.qualify(REFUSALS)
        result,stdout=execute(GATE.source.read_text(),json.loads(GATE.inputs.read_text()))
        self.assertEqual(result,json.loads(GATE.expected.read_text()))
        self.assertEqual(stdout,''.join(line+'\n' for line in result['log']))

    def test_fuzz_differs_from_naive_ceiling_and_floor(self):
        above=1+2**-40;below=-1-2**-40
        self.assertEqual((sas_ceil(above),sas_floor(below)),(1,-1))
        self.assertEqual((math.ceil(above),math.floor(below)),(2,-2))
        self.assertEqual((sas_ceil(1+2**-30),sas_floor(-1-2**-30)),(2,-2))

    def test_near_zero_fuzz_and_direction_are_separate(self):
        self.assertEqual((sas_ceil(2**-40),sas_floor(-2**-40)),(0,0))
        self.assertEqual((sas_ceil(2**-39),sas_floor(-2**-39)),(1,-1))
        self.assertEqual((sas_sign(2**-40),sas_sign(-2**-40)),(1,-1))

    def test_minimum_normal_is_admitted_exactly(self):
        minimum=float.fromhex('0x1p-1022')
        self.assertEqual(sas_abs(-minimum),minimum)
        self.assertEqual((sas_sign(minimum),sas_sign(-minimum),sas_ceil(minimum),sas_floor(-minimum)),(1,-1,0,0))
        result,_=execute(f'data d;x=abs({-minimum!r});run;')
        self.assertEqual(result['datasets']['d']['rows'],[{'x':minimum}])

    def test_ordinary_missing_and_signed_zero(self):
        result,_=execute('data d;a=abs(.);b=sign(.);c=ceil(.);d=floor(.);e=sign(-0);f=abs(-0);run;')
        self.assertEqual(result['datasets']['d']['rows'],[{'a':None,'b':None,'c':None,'d':None,'e':0.,'f':0.}])

    def test_domain_edge_and_oversized_integers(self):
        for function in (sas_abs,sas_sign,sas_ceil,sas_floor):
            self.assertIsNotNone(function(2147483647))
            for value in (2147483648,10**400,-10**400):
                with self.subTest(function=function.__name__,value=value),self.assertRaises(ValueError):function(value)

    def test_subnormal_and_wrong_literal_types_refuse_when_skipped(self):
        for rhs in ("abs('1')","sign(.A)",'ceil(1e-320)','floor(1e309)','abs(2147483648)'):
            self.assertEqual(build_job('data d;if 0 then x='+rhs+';run;').code,2)

    def test_empty_inputs_still_validate_descriptors(self):
        inputs={'raw':{'schema':{'x':{'type':'character','length':4}},'rows':[]}}
        self.assertEqual(job_with_inputs('data d;set raw;if 0 then a=abs(x);run;',inputs).code,1)
        result,_=execute('data d;set raw;if 0 then a=abs(x);run;',{'raw':{'schema':{'x':'number'},'rows':[]}})
        self.assertEqual(result['datasets']['d'],{'schema':{'x':'number','a':'number'},'rows':[]})

    def test_late_subnormal_failure_is_atomic_and_skipped_values_are_lazy(self):
        inputs={'raw':{'schema':{'x':'number'},'rows':[{'x':-2},{'x':1e-320}]}}
        job=job_with_inputs("data d;set raw;a=abs(x);output;put 'row';run;",inputs)
        self.assertEqual(job.code,1);self.assertIsNone(job.result);self.assertFalse(job.receipt['accepted'])
        result,_=execute('data d;set raw;if 0 then a=abs(x);run;',inputs)
        self.assertEqual([row['a'] for row in result['datasets']['d']['rows']],[None,None])

    def test_portable_shapes_numeric_values_and_version_are_strict(self):
        original=compile_plan('data d;x=ceil(1);run;').to_dict()
        for mutation in ('bool','huge','infinity','extra','version'):
            plan=deepcopy(original);call=plan['steps'][0]['operations'][0]['args']['value']
            if mutation=='bool':call['args'][0]['value']=True
            elif mutation=='huge':call['args'][0]['value']=10**400
            elif mutation=='infinity':call['args'][0]['value']=float('inf')
            elif mutation=='extra':call['extra']=1
            else:plan['version']=2.0
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):run_plan(plan)

    def test_nested_arithmetic_and_consumers_remain_refused(self):
        for rhs in ('abs(1+2)','sign(abs(-1))','sum(ceil(1),2)','ceil(-x)'):
            self.assertIn(build_job('data d;a='+rhs+';run;').code,(1,2))

    def test_prior_profiles_array_names_and_cpp_boundaries(self):
        for name in ('abs','sign','ceil','floor'):
            result,_=execute(f'data d;array {name} a b;a=1;b=2;x={name}[2];run;')
            self.assertEqual(result['datasets']['d']['rows'][0]['x'],2.)
        for source in ('data d;retain n 0;x=abs(n);run;','data d;array z a;x=abs(a);run;','data d;set raw;where abs(a);run;'):
            self.assertIn(build_job(source).code,(1,2))
        self.assertEqual(build_job('data _null_;x=abs(1);run;',target='cpp').code,2)

    def test_stored_summary_results_compose_with_numeric_helpers(self):
        result,_=execute("data d;a=coalesce(.,-2);b=abs(a);c=mean(b,4);d=ceil(c);e=put(d,8.2);put e;run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':-2.,'b':2.,'c':3.,'d':3.,'e':'    3.00'}])
        self.assertEqual(result['log'],['3.00 '])

    def test_routes_name_numeric_helper_evidence(self):
        for name in ('abs','sign','ceil','floor'):
            self.assertEqual(route_function(f'x={name}(a);')[1],'DS-100')


if __name__=='__main__':unittest.main()
