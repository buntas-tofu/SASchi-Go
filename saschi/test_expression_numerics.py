"""Recursive numeric calls and exact integer arithmetic at every boundary."""
from copy import deepcopy
import json,random,unittest
from unittest.mock import patch
from . import function_expressions as ex
from examples.verify_expression_numerics import GATE
import sas_semantics as sem
from .expression_test_support import ExpressionContract,execute
from .plan import compile_plan
from .runtime import run_plan
from .test_do_counted import job_with_inputs


def lit(value):return '.' if value is None else repr(value)


class NumericExpressionTests(ExpressionContract,unittest.TestCase):
    gate=GATE;phase='numeric-expressions';rule='DS-117'

    def test_old_and_new_step_terminators_use_lexical_semicolons(self):
        new='data fresh;set raw;x=abs(a-b);run /* ; quoted-looking terminator */;'
        old='data prior;set raw;control=1;run /* ; quoted-looking terminator */;'
        inputs={'raw':{'schema':{'a':'number','b':'number'},'rows':[{'a':3,'b':1}]}}
        for source in (old+new,new+old):
            result=execute(source,inputs)
            self.assertEqual(result['datasets']['fresh']['rows'],[{'a':3,'b':1,'x':2}])
            self.assertEqual(result['datasets']['prior']['rows'],[{'a':3,'b':1,'control':1}])

    def test_generated_nested_numeric_calls_match_independent_R(self):
        inner=[('abs',[-3]),('abs',[None]),('sign',[-2]),('ceilz',[-1.5]),('floorz',[-1.5]),('intz',[-2.25]),('roundz',[2.5,1]),('modz',[5.5,2]),('min',[None,3,-1]),('max',[None,2,-1]),('sum',[None,-2,3]),('coalesce',[None,4]),('n',[None,2]),('nmiss',[None,2]),('largest',[1,2,3]),('smallest',[2,2,3])]
        values=GATE.r_cases(inner);calls=[];sources=[]
        for (name,args),value in zip(inner,values):
            child=name+'('+','.join(map(lit,args))+')'
            for outer in ('abs','sign','ceilz','floorz','intz','min','max','sum','coalesce','n','nmiss','largest','smallest','roundz','modz'):
                if outer in ('largest','smallest') and value is not None and int(value)!=value:continue
                prefix=[1] if outer in ('largest','smallest') else []
                suffix=[2] if outer in ('min','max','sum','coalesce','n','nmiss','largest','smallest','roundz','modz') else []
                calls.append((outer,prefix+[value]+suffix))
                sources.append('data d;x='+outer+'('+','.join([*map(lit,prefix),child,*map(lit,suffix)])+');run;')
        for source,wanted in zip(sources,GATE.r_cases(calls)):
            self.assertEqual(execute(source)['datasets']['d']['rows'],[{'x':wanted}],source)

    def test_exact_integer_arithmetic_and_missing_hand_pins(self):
        for op,values,wanted in [('+',[1,2],3),('-',[1,2],-1),('+',[-1000000,1000000],0),('-',[None,2],None),('+',[None,None],None),('-',[3],-3),('+',[-3],-3),('-',[None],None)]:
            self.assertEqual(sem.sas_expression_arithmetic(op,values),wanted)
        for rhs,wanted in [('abs(1+2)',3),('abs(1-4)',3),('sum(abs(.),2)',2),('sum(abs(.),.)',None),('abs(.+2)',None),('-abs(-2)',-2),('+abs(-2)',2),('abs((4-3)-2)',1),('sum(abs(0.5),0.5)',1)]:
            self.assertEqual(execute('data d;x='+rhs+';run;')['datasets']['d']['rows'],[{'x':wanted}])

    def test_each_integer_operand_validates_before_missing_propagation(self):
        for values in ([None,0.5],[None,1000001],[1000000,1],[True,1],[float('inf'),None]):
            with self.subTest(values=values),self.assertRaises(ValueError):sem.sas_expression_arithmetic('+',list(values))
        for rhs in ('abs(.+0.5)','abs(1000000+1)','abs((1000000+1)-1)','sum(abs(0.0001),a)','abs(a+1000001)','abs(a+0.5)'):
            self.assertTrue(compile_plan('data d;set raw;if 0 then x='+rhs+';run;').blocked,rhs)
        source='data d;set raw;x=abs(a+.);put x;run;'
        self.atomic_cli(source,{'raw':{'schema':{'a':'number'},'rows':[{'a':1},{'a':0.5}]}},'integer')

    def test_sum_missing_policy_grid_and_intermediate_bounds(self):
        self.assertIsNone(sem.sas_expression_call('sum',[None,None]))
        self.assertEqual(sem.sas_expression_call('sum',[1/1024,None,1/1024]),1/512)
        for values in ([1e6,1],[0.0001,None],[1000001,None]):
            with self.assertRaises(ValueError):sem.sas_expression_call('sum',list(values))
        source='data d;set raw;x=sum(abs(a),b);put x;run;'
        self.atomic_cli(source,{'raw':{'schema':{'a':'number','b':'number'},'rows':[{'a':1,'b':2},{'a':1000000,'b':1}]}},'numeric')

    def test_rank_zero_fuzz_and_primitive_control_roles(self):
        for rhs in ('largest(abs(1),1,2)','roundz(abs(2),abs(1))',"substrn('ab',abs(1),1)",'largest(k,abs(a),0.5)','modz(abs(1e-100),unit)'):
            source='data d;set raw;if 0 then x='+rhs+';run;'
            inputs={'raw':{'schema':{'a':'number','k':'number','unit':'number'},'rows':[]}}
            self.assertIn(job_with_inputs(source,inputs).code,(1,2),rhs)
        source='data d;set raw;x=abs(a-b);put x;run;'
        self.atomic_cli(source,{'raw':{'schema':{'a':'number','b':'number'},'rows':[{'a':3,'b':1},{'a':1000000,'b':-1}]}},'numeric')

    def test_portable_arithmetic_shapes_and_types_refuse(self):
        original=compile_plan('data d;x=abs(1+2);run;').to_dict()
        for field,value in [('op','*'),('op',True),('op',[]),('extra',1),('left',{'kind':'number','value':True}),('right',{'kind':'character','value':'1'}),('right',{'kind':'number','value':10**400})]:
            plan=deepcopy(original);node=plan['steps'][0]['operations'][1]['args']['value']['args'][0];node[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):run_plan(plan)

    def test_fractional_calls_keep_separate_policies_from_integer_operators(self):
        self.assertEqual(execute('data d;x=roundz(abs(-2.5),1);run;')['datasets']['d']['rows'],[{'x':2}])
        self.assertTrue(compile_plan('data d;x=abs(-2.5)+1;run;').blocked)
        with patch.object(ex,'STAGE',2):
            for source in ('data d;if abs(-1) then x=1;run;','data d;if -abs(-1) then x=1;run;','data d;if abs(-1)+0 then x=1;run;','data d;x=abs(1)>0;run;','data d;x=ifn(1,abs(-1),0);run;'):
                self.assertTrue(compile_plan(source).blocked,source)


if __name__=='__main__':unittest.main()
