"""Comparison values, numeric function truth and typed character bridges."""
from copy import deepcopy
from pathlib import Path
import subprocess,sys,unittest
from examples.verify_expression_comparisons import GATE
from examples.wave_gate_common import decode
import sas_semantics as sem
from .expression_test_support import ExpressionContract,execute
from .plan import compile_plan
from .runtime import run_plan
from .test_do_counted import job_with_inputs


class ComparisonExpressionTests(ExpressionContract,unittest.TestCase):
    gate=GATE;phase='comparisons-and-truth';rule='DS-118'

    def test_shared_helper_imports_in_an_isolated_process_without_fixture_paths(self):
        code='from saschi.expression_test_support import assert_new_expression;assert callable(assert_new_expression)'
        run=subprocess.run([sys.executable,'-B','-c',code],cwd=GATE.directory.parent,capture_output=True,text=True,timeout=30)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)

    def test_independent_R_missing_order_and_function_truth_grid(self):
        script=GATE.directory/'composition_predicate_grid.R'
        run=subprocess.run(['Rscript',str(script),str(GATE.directory)],capture_output=True,text=True,check=True,timeout=30)
        aliases={'eq':'=','ne':'^=','lt':'<','le':'<=','gt':'>','ge':'>='}
        count=0
        for line in run.stdout.splitlines():
            parts=line.split('|')
            if parts[0]=='CMP':
                a,b,wanted=decode(parts[1]),decode(parts[2]),decode(parts[4]);op=parts[3]
                source='data d;set raw;x=(coalesce(a,.) '+aliases[op]+' b);run;'
                inputs={'raw':{'schema':{'a':'number','b':'number'},'rows':[{'a':a,'b':b}]}}
                self.assertEqual(execute(source,inputs)['datasets']['d']['rows'][0]['x'],wanted)
                self.assertEqual(sem.sas_expression_compare(op,a,b),wanted);count+=1
            elif parts[0]=='TRUTH':
                a,wanted=decode(parts[1]),decode(parts[2]);inputs={'raw':{'schema':{'a':'number'},'rows':[{'a':a}]}}
                row=execute('data d;set raw;if coalesce(a,.) then hit=1;else hit=0;run;',inputs)['datasets']['d']['rows'][0]
                self.assertEqual(row['hit'],wanted)
        self.assertEqual(count,150)

    def test_function_truth_can_wrap_numeric_expressions_at_stage3(self):
        for condition,wanted in (('-abs(-1)',1),('abs(-1)+0',1),('-abs(.)',0)):
            source='data d;if '+condition+' then hit=1;else hit=0;run;'
            self.assertEqual(execute(source)['datasets']['d']['rows'],[{'hit':wanted}])

    def test_character_padding_empty_temporary_and_swapped_operands(self):
        for rhs,wanted in [("strip(' ')=trimn(' ')",1),("upcase('a')='A '",1),("'A '=upcase('a')",1),("strip(' ')=trim(' ')",1),("upcase('z')<lowcase('A')",1),("lowcase('A') eq 'A'",0)]:
            self.assertEqual(execute('data d;x=('+rhs+');run;')['datasets']['d']['rows'],[{'x':wanted}],rhs)
        self.assertEqual(execute('data d;x=(1=1);y=(0>1);run;')['datasets']['d']['rows'],[{'x':1,'y':0}])
        for alias in ('=','EQ','^=','~=','NE','<','LT','<=','LE','>','GT','>=','GE'):
            source='data d;x=(abs(-1) '+alias+' 1);run;'
            self.assertFalse(compile_plan(source).blocked,source)

    def test_computed_bridge_values_and_empty_controls(self):
        source="data d;a=lengthn(strip(' '));b=length(trimn(' '));c=missing(strip(' '));d=cmiss(strip(' '),abs(.),'A');e=verify(upcase(strip(' a ')),'A');f=anyalpha(strip(' '));g=notalnum(upcase(strip(' a1 ')));run;"
        self.assertEqual(execute(source)['datasets']['d']['rows'],[{'a':0,'b':1,'c':1,'d':2,'e':0,'f':0,'g':0}])
        for rhs in ("verify(upcase('a'),upcase('a'))","anyalpha(upcase('a'),abs(1))"):
            self.assertTrue(compile_plan('data d;x='+rhs+';run;').blocked,rhs)

    def test_incompatible_or_unknown_descriptors_refuse_on_empty_and_skipped_paths(self):
        for source in ("data d;set raw;if 0 then x=(upcase(code)=a);run;","data d;set raw;if strip(code) then x=1;run;","data d;set raw;x=(coalesce(a,0)>1000001);run;","data d;set raw;x=(lengthn(strip(future))>0);run;"):
            inputs={'raw':{'schema':{'a':'number','code':{'type':'character','length':4}},'rows':[]}}
            self.assertIn(job_with_inputs(source,inputs).code,(1,2),source)

    def test_chains_prefixes_missing_tags_and_where_operators_remain_held(self):
        for rhs in ('abs(a)<b<c','(abs(a)<b)<c',"upcase(code)=:'A'",'abs(a) in (1,2)','abs(a)<>b','abs(a)=.A'):
            self.assertTrue(compile_plan('data d;set raw;x=('+rhs+');run;').blocked,rhs)

    def test_portable_predicate_fields_operator_types_and_domains(self):
        original=compile_plan('data d;x=(abs(-2)>1);run;').to_dict()
        for field,value in [('op','<>'),('op',True),('op',[]),('extra',1),('left',{'kind':'number','value':1000001}),('right',{'kind':'character','value':'1'})]:
            plan=deepcopy(original);plan['steps'][0]['operations'][1]['args']['value'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):run_plan(plan)

    def test_dynamic_function_domain_failure_is_atomic_after_valid_prefix(self):
        source='data d;set raw;if largest(k,abs(a),abs(b))>=limit then hit=1;else hit=0;put hit;run;'
        inputs={'raw':{'schema':{'a':'number','b':'number','k':'number','limit':'number'},'rows':[{'a':2,'b':1,'k':1,'limit':0},{'a':2,'b':1,'k':0,'limit':0}]}}
        self.atomic_cli(source,inputs,'rank')


if __name__=='__main__':unittest.main()
