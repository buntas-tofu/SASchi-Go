"""Eager conditional selection over typed predicates and recursive choices."""
from copy import deepcopy
import unittest
from examples.verify_expression_selectors import GATE
from .expression_test_support import ExpressionContract,execute
from .plan import compile_plan
from .job import build_job
from .runtime import run_plan
from .test_do_counted import job_with_inputs


class SelectorExpressionTests(ExpressionContract,unittest.TestCase):
    gate=GATE;phase='selector-expressions';rule='DS-120'

    def test_all_condition_outcomes_and_optional_missing_choices_match_R(self):
        cases=[];sources=[]
        for flag in (None,0,-1,1):
            text='.' if flag is None else str(flag)
            for name,choices,expressions in [('ifn',[2,3,4],['abs(-2)','sum(1,2)','max(3,4)']),('ifc',['AB','cd',''],["upcase('ab')","lowcase('CD')","strip(' ')"])]:
                for size in (2,3):
                    cases.append((name,[flag]+choices[:size]))
                    sources.append('data d;x='+name+'('+','.join([text,*expressions[:size]])+');run;')
        for source,wanted in zip(sources,GATE.r_cases(cases)):
            table=execute(source)['datasets']['d'];value=table['rows'][0]['x']
            self.assertEqual(value,wanted.ljust(200) if isinstance(wanted,str) else wanted,source)

    def test_selectors_inside_constructors_numeric_calls_and_each_other(self):
        source="data d;x=cats(ifc(not 0,upcase('ab'),strip(' ')),'-',strip(ifc(0,'Z',' q ')));y=abs(ifn(1,smallest(2,2,3),sum(1,2)));z=ifn(1,ifn(0,1,abs(-2)),0);run;"
        row=execute(source)['datasets']['d']['rows'][0]
        self.assertEqual(row,{'x':'AB-q'.ljust(200),'y':3,'z':2})
        self.assertTrue(compile_plan("data d;x=upcase(strip(dequote(ifc(1,upcase('a'),'b'))));run;").blocked)

    def test_computed_empty_choices_keep_bytes_distinct_from_stored_blank(self):
        source="data d;x=transtrn('a-b','-',ifc(1,trimn(' '),trim(' ')));y=transtrn('a-b','-',ifc(0,trimn(' '),trim(' ')));run;"
        row=execute(source)['datasets']['d']['rows'][0]
        self.assertEqual(row,{'x':'ab'.ljust(200),'y':'a b'.ljust(200)})

    def test_all_reached_unselected_arguments_are_eager_and_fault_atomically(self):
        source='data d;set raw;x=ifn(flag,abs(a),largest(k,a,b));put x;run;'
        inputs={'raw':{'schema':{'a':'number','b':'number','k':'number','flag':'number'},'rows':[{'a':2,'b':1,'k':1,'flag':1},{'a':2,'b':1,'k':0,'flag':1}]}}
        self.atomic_cli(source,inputs,'rank')
        guarded='data d;set raw;if flag then x=abs(a);else x=largest(k,a,b);put x;run;'
        self.assertEqual(execute(guarded,inputs)['log'],['2 ','2 '])

    def test_character_unselected_constructor_overflow_remains_eager(self):
        source="data d;set raw;x=ifc(flag,'Y',cats(upcase(label),'Z'));put x;run;"
        inputs={'raw':{'schema':{'label':{'type':'character','length':200},'flag':'number'},'rows':[{'label':'A','flag':1},{'label':'X'*200,'flag':1}]}}
        self.atomic_cli(source,inputs,'buffer')

    def test_literal_choice_types_and_primitive_descriptors_validate_on_empty(self):
        inputs={'raw':{'schema':{'label':{'type':'character','length':201},'flag':'number','a':'number'},'rows':[]}}
        for rhs in ("ifc(flag,label,strip(' '))",'ifn(flag,abs(a),0.5+1)',"ifc(1,upcase('Y'),abs(a))",'ifn(flag,abs(a),largest(0,a,1))'):
            self.assertIn(job_with_inputs('data d;set raw;if 0 then x='+rhs+';run;',inputs).code,(1,2),rhs)
        source="data d;set raw;x=ifc(flag,upcase(label),strip(' '));run;"
        self.assertEqual(execute(source,inputs)['datasets']['d']['rows'],[])

    def test_destination_width_is_checked_after_selection_without_coercion(self):
        self.assertEqual(build_job("data d;length x $1;x=ifc(1=1,upcase('AB'),'N');run;").code,1)
        source="data d;length x $1;set raw;x=ifc(flag=1,upcase(code),'N');put x;run;"
        inputs={'raw':{'schema':{'code':{'type':'character','length':2},'flag':'number'},'rows':[{'code':'A','flag':0},{'code':'AB','flag':1}]}}
        self.atomic_cli(source,inputs,'buffer')

    def test_portable_selector_arguments_and_control_roles_remain_exact(self):
        original=compile_plan('data d;x=ifn(abs(1),abs(-2),0);run;').to_dict()
        for args in ((),[],[{'kind':'number','value':1}],None):
            plan=deepcopy(original);plan['steps'][0]['operations'][1]['args']['value']['args']=args
            with self.assertRaises(ValueError):run_plan(plan)
        for rhs in ('largest(ifn(1,1,2),1,2)','roundz(abs(-2),ifn(1,1,2))',"catx(ifc(1,'|','-'),'A','B')"):
            self.assertTrue(compile_plan('data d;x='+rhs+';run;').blocked,rhs)


if __name__=='__main__':unittest.main()
