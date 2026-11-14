"""SAS Boolean precedence and conservative validation of pure operands."""
from copy import deepcopy
import subprocess,unittest
from examples.verify_expression_booleans import GATE
from examples.wave_gate_common import decode
from .expression_test_support import ExpressionContract,execute
from .plan import compile_plan
from .runtime import run_plan
from .test_do_counted import job_with_inputs


class BooleanExpressionTests(ExpressionContract,unittest.TestCase):
    gate=GATE;phase='boolean-conditions';rule='DS-119'

    def test_independent_R_truth_grid_including_missing_zero_and_nonzero(self):
        run=subprocess.run(['Rscript',str(GATE.directory/'composition_predicate_grid.R'),str(GATE.directory)],capture_output=True,text=True,check=True,timeout=30)
        count=0
        for line in run.stdout.splitlines():
            parts=line.split('|')
            if parts[0]!='BOOL':continue
            a,b,c,wanted=map(decode,parts[1:]);inputs={'raw':{'schema':{'a':'number','b':'number','c':'number'},'rows':[{'a':a,'b':b,'c':c}]}}
            source='data d;set raw;x=(coalesce(a,.) and b or not c);run;'
            self.assertEqual(execute(source,inputs)['datasets']['d']['rows'][0]['x'],wanted)
            count+=1
        self.assertEqual(count,125)

    def test_NOT_has_SAS_group_I_precedence_and_parentheses_override(self):
        source='data d;a=2;x=(not a=2);y=not(a=2);z=(not a+1=1);run;'
        row=execute(source)['datasets']['d']['rows'][0]
        self.assertEqual(row,{'a':2,'x':0,'y':0,'z':1})
        source='data d;a=0;x=(not a=2);y=not(a=2);run;'
        row=execute(source)['datasets']['d']['rows'][0];self.assertEqual((row['x'],row['y']),(0,1))
        plan=compile_plan(source).to_dict();tree=plan['steps'][0]['operations'][2]['args']['value']
        self.assertEqual((tree['kind'],tree['left']['kind'],tree['left']['op']),('expr_compare','expr_unary','not'))

    def test_AND_precedes_OR_and_qualified_symbol_aliases_match(self):
        for rhs,wanted in [('1 or 0 and 0',1),('(1 or 0) and 0',0),('1 | 0 & 0',1),('^0',1),('~0',1),('not .',1),('not -2',0),('1 and (0 or 1)',1)]:
            prefix='data d;cue=abs(1+2);' if rhs=='not -2' else 'data d;'
            self.assertEqual(execute(prefix+'x=('+rhs+');run;')['datasets']['d']['rows'][0]['x'],wanted,rhs)
        from .plan import _compile_before_function_expressions
        legacy='data d;x=(not -2);run;'
        self.assertEqual(compile_plan(legacy).to_dict(),_compile_before_function_expressions(legacy).to_dict())

    def test_symbol_AND_preserves_the_unresolved_macro_reference_hold(self):
        for condition in ('a&b','a &b','1&b','a&abs(-1)'):
            self.assertTrue(compile_plan('data d;a=1;b=1;x=('+condition+');run;').blocked,condition)
        source="data d;a=1;b=1;x=(a & b);literal='&b';run;"
        self.assertEqual(execute(source)['datasets']['d']['rows'],[{'a':1,'b':1,'x':1,'literal':'&b'}])
        source='data d;a=1;b=1;x=(a&0);run;'
        self.assertEqual(execute(source)['datasets']['d']['rows'][0]['x'],0)

    def test_potential_function_operands_validate_even_when_logically_unneeded(self):
        source='data d;set raw;if flag or modz(a,unit)>0 then hit=1;else hit=0;put hit;run;'
        inputs={'raw':{'schema':{'a':'number','unit':'number','flag':'number'},'rows':[{'a':2,'unit':2,'flag':1},{'a':2,'unit':3,'flag':1}]}}
        self.atomic_cli(source,inputs,'power of two')
        source='data d;set raw;if flag then hit=1;else if modz(a,unit)>0 then hit=1;else hit=0;put hit;run;'
        result=execute(source,inputs)
        self.assertEqual([r['hit'] for r in result['datasets']['d']['rows']],[1,1])
        self.assertEqual(result['log'],['1 ','1 '])
        for condition in ('0 and modz(a,3)>0','1 or (abs(a)+0.5)>0','0 and 1000001'):
            bad='data d;set raw;if '+condition+' then hit=1;run;'
            empty={'raw':{'schema':{'a':'number'},'rows':[]}}
            self.assertIn(job_with_inputs(bad,empty).code,(1,2),condition)

    def test_unvisited_statement_predicates_stay_dynamic_but_static_literals_validate(self):
        inputs={'raw':{'schema':{'flag':'number','a':'number','k':'number'},'rows':[{'flag':0,'a':1,'k':0}]}}
        source='data d;set raw;hit=0;if flag then if largest(k,abs(a),1)>0 then hit=1;run;'
        self.assertEqual(execute(source,inputs)['datasets']['d']['rows'][0]['hit'],0)
        self.assertTrue(compile_plan(source.replace('largest(k,','largest(0,')).blocked)

    def test_character_boolean_operands_and_unknown_types_refuse_on_empty(self):
        for condition in ("upcase(code) and 1","not strip(code)","1 or strip(code)"):
            inputs={'raw':{'schema':{'code':{'type':'character','length':4}},'rows':[]}}
            self.assertIn(job_with_inputs('data d;set raw;x=('+condition+');run;',inputs).code,(1,2))

    def test_portable_Boolean_fields_aliases_and_non_numeric_values_refuse(self):
        original=compile_plan('data d;x=(1 and 0);run;').to_dict()
        for field,value in [('op','&'),('op',True),('op',[]),('extra',1),('left',{'kind':'number','value':True}),('right',{'kind':'character','value':'1'})]:
            plan=deepcopy(original);plan['steps'][0]['operations'][1]['args']['value'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):run_plan(plan)


if __name__=='__main__':unittest.main()
