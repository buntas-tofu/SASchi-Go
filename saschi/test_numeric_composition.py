"""DS-045/046 bounded composition and whole-program repository/base-R proofs."""
import contextlib
from copy import deepcopy
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from examples.verify_multiply import (PINS, REFUSALS, ORIGINAL, original_expected,
    original_accounting, array_expected, array_accounting, program_witness)
from sas_semantics import sas_multiply
from .compare import equal
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .test_do_counted import execute, job_with_inputs
from .test_parser import ROKU_CORPUS


def digest(result):
    return hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def raw(rows,schema=None):
    return {'raw':{'schema':schema or {'x':'number','y':'number'},'rows':rows}}


class NumericCompositionTests(unittest.TestCase):
    def row(self,expr):
        return execute('data d;p='+expr+';run;')[0]['datasets']['d']['rows'][0]['p']

    def test_helper_hand_pins(self):
        for left,right,expected in PINS:
            with self.subTest(left=left,right=right):self.assertEqual(sas_multiply(left,right),expected)

    def test_helper_refusals_validate_both_operands(self):
        for left,right in REFUSALS:
            with self.subTest(left=str(left)[:30],right=str(right)[:30]),self.assertRaises(ValueError):sas_multiply(left,right)

    def test_zero_is_normalized(self):
        for left,right in ((-0.,1.),(0.,-1.),(-1.,0.)):
            self.assertEqual(math.copysign(1.,sas_multiply(left,right)),1.)

    def test_operator_provenance_and_precedence(self):
        for expression,want in (('2+3*4',14.),('2*3+4',10.),('20/2*5',50.),
                                ('20*2/5',8.),('20-2*3',14.),('2*3*4',24.)):
            with self.subTest(expression=expression):self.assertEqual(self.row(expression),want)
        self.assertIn(('multiplication','DS-045',1),compile_plan('data d;p=2*3;run;').matched)

    def test_grouping_signs_and_exponent_tokens(self):
        for expression,want in (('(2+3)*4',20.),('20/(2*5)',2.),('-2*3',-6.),
                                ('2*-3',-6.),('1e-3*2',.002),('1e+1*2',20.)):
            with self.subTest(expression=expression):self.assertEqual(self.row(expression),want)
        text=execute("data d;t='2*3';p=2*3;run;")[0]['datasets']['d']['rows'][0]
        self.assertEqual(text,{'t':'2*3','p':6.})

    def test_function_argument_and_result_composition(self):
        for expression,want in (('mod(3*4,5)',2.),('sum(2,3)*4',20.),('int(3.5)*2',6.)):
            self.assertEqual(self.row(expression),want)
        row=execute('data d;tag=.A;p=2*3;formatted=put(p,8.2);run;')[0]['datasets']['d']['rows'][0]
        self.assertEqual(row,{'tag':{'missing':'A'},'p':6.,'formatted':'    6.00'})

    def test_ordinary_missing_propagates(self):
        for expression in ('.*2','2*.','.*.','0*.'):
            self.assertIsNone(self.row(expression))

    def test_boundaries_and_subnormal_products(self):
        for expression,want in (('46340*46340',2147395600.),('2147483647*1',2147483647.),
                                ('5e-324*1',5e-324),('2.2250738585072014e-308*.5',2.**-1023)):
            self.assertEqual(self.row(expression),want)
        self.assertEqual(self.row('1+5e-324'),1.)
        self.assertNotEqual(build_job('data d;p=(1+5e-324)*1;run;').code,0)

    def test_invalid_literal_products_refuse_when_skipped(self):
        for expression in ('46341*46341','1.1*1.1','5e-324*.5','.A*1','"2"*1','0*2147483648','.*2147483648'):
            for body in ('p='+expression+';','if 0 then p='+expression+';',
                         'do i=1 to 0;p='+expression+';end;'):
                with self.subTest(body=body):
                    job=build_job('data d;'+body+'run;')
                    self.assertNotEqual(job.code,0);self.assertIsNone(job.result)
        for depth in (30,31):
            expression='('*depth+'46341'+')'*depth+'*46341*0*1'
            for body in ('p='+expression+';','if 0 then p='+expression+';'):
                job=build_job('data d;'+body+'run;')
                self.assertNotEqual(job.code,0);self.assertIsNone(job.result)

    def test_empty_and_filtered_input_still_checks_static_types(self):
        for rows in ([],[{'x':'a','y':2.}]):
            for body in ('p=x*y;','if 0 then p=x*y;'):
                job=job_with_inputs('data d;set raw;'+body+'run;',raw(rows,{'x':{'type':'character','length':1},'y':'number'}))
                self.assertNotEqual(job.code,0);self.assertIsNone(job.result)

    def test_dynamic_invalid_values_cannot_hide_behind_missing_or_zero(self):
        for x,y in ((None,2147483648.),(2147483648.,None),(0.,2147483648.),(1e308,1e308)):
            for expression in ('x*y','(x+y)*0','0*(x+y)'):
                with self.subTest(x=x,y=y,expression=expression):
                    job=job_with_inputs('data d;set raw;p='+expression+';run;',raw([{'x':x,'y':y}]))
                    self.assertNotEqual(job.code,0);self.assertIsNone(job.result)

    def test_dynamic_skipped_and_filtered_products_are_lazy(self):
        values=raw([{'x':2147483648.,'y':2.}])
        result=execute('data d;set raw;if 0 then p=x*y;run;',values)[0]
        self.assertEqual(result['datasets']['d']['rows'][0]['p'],None)
        result=execute('data d;set raw;where x<0;p=x*y;run;',values)[0]
        self.assertEqual(result['datasets']['d']['rows'],[])

    def test_where_and_if_use_multiplication(self):
        result=execute('data d;set raw;where x*2>2;if y*2=8 then p=x*y;run;',
                       raw([{'x':1.,'y':4.},{'x':3.,'y':4.}]))[0]
        self.assertEqual(result['datasets']['d']['rows'],[{'x':3.,'y':4.,'p':12.}])

    def test_retained_sum_and_counted_snapshots(self):
        result,_=execute('data d;do i=1 to 3;total+i*2;output;end;run;')
        self.assertEqual([r['total'] for r in result['datasets']['d']['rows']],[2.,6.,12.])
        for control in ('do while(x*2<8);','do until(x*2=8);'):
            row=execute('data d;x=1;'+control+'x=x+1;end;run;')[0]['datasets']['d']['rows'][0]
            self.assertEqual(row['x'],4.)

    def test_array_reads_writes_and_sum_of(self):
        result,_=execute('data d;array a{2} first second;first=3;second=4;a[1]=a[1]*a[2];total=sum(of a{*});run;')
        self.assertEqual(result['datasets']['d']['rows'],[{'first':12.,'second':4.,'total':16.}])
        row=execute('data d;array a{2} x y;do i=1 to 2;a[i*1]=i*2;end;run;')[0]['datasets']['d']['rows'][0]
        self.assertEqual((row['x'],row['y']),(2.,4.))
        row=execute('data d;array a x y;x=2;y=3;do over a;a=a*2;end;run;')[0]['datasets']['d']['rows'][0]
        self.assertEqual((row['x'],row['y']),(4.,6.))

    def test_nested_counted_array_composition(self):
        result,_=execute('data d;array a{2} x y;do i=1 to 2;do j=1 to 2;a[i]=i*j;end;end;run;')
        self.assertEqual(result['datasets']['d']['rows'],[{'x':2.,'y':4.,'i':3.,'j':3.}])

    def test_counted_controls_keep_their_prior_profile(self):
        for control in ('do i=1 to 2*3;','do i=1*2 to 3;','do i=1 to 3 by 1*1;'):
            self.assertTrue(compile_plan('data d;'+control+'output;end;run;').blocked)

    def test_forged_operator_and_shape_refuse(self):
        original=compile_plan('data d;p=2*3;run;').to_dict()
        for operator in ('**','^','unknown'):
            plan=deepcopy(original);plan['steps'][0]['operations'][0]['args']['value']['op']=operator
            with self.assertRaises(ValueError):run_plan(plan,allow_partial=True)
        plan=deepcopy(original);del plan['steps'][0]['operations'][0]['args']['value']['right']
        with self.assertRaises(ValueError):run_plan(plan)
        for bad in ({'kind':'number','value':None},{'kind':'number','value':True},
                    {'kind':'number','value':'2'},{'kind':'missing','value':1}):
            plan=compile_plan('data d;if 0 then p=2*3;run;').to_dict()
            plan['steps'][0]['operations'][0]['args']['operation']['args']['value']['left']=bad
            with self.subTest(bad=bad),self.assertRaises(ValueError):run_plan(plan)

    def test_deep_and_oversized_forged_products_refuse(self):
        plan=compile_plan('data d;p=2*3;run;').to_dict();expr={'kind':'number','value':1.}
        for _ in range(500):expr={'kind':'arithmetic','op':'*','left':expr,'right':{'kind':'number','value':1.}}
        plan['steps'][0]['operations'][0]['args']['value']=expr
        with self.assertRaises(ValueError):run_plan(plan)
        self.assertTrue(compile_plan('data d;'+'p=1*1;'*129+'run;').blocked)
        shallow=compile_plan('data d;p=2*3;run;').to_dict();expr={'kind':'number','value':1.}
        for _ in range(40):expr={'kind':'arithmetic','op':'*','left':expr,'right':{'kind':'number','value':1.}}
        shallow['steps'][0]['operations'][0]['args']['value']=expr
        with self.assertRaisesRegex(ValueError,'32'):run_plan(shallow)
        wrapped=compile_plan('data d;p=2*3;run;').to_dict();expr={'kind':'number','value':2.}
        for _ in range(1500):expr={'kind':'unknown','value':expr}
        wrapped['steps'][0]['operations'][0]['args']['value']['left']=expr
        with self.assertRaises(ValueError):run_plan(wrapped)
        for metadata in ({'kind':'tagged_missing','value':expr},
                         {'kind':'format','name':expr,'w':8,'d':2}):
            plan=compile_plan('data d;p=2*3;run;').to_dict()
            plan['steps'][0]['operations'][0]['args']['value']['left']=metadata
            with self.subTest(kind=metadata['kind']),self.assertRaises(ValueError):run_plan(plan)

    def test_unsupported_operator_spellings_stay_refused(self):
        for expression in ('2//3','2^3'):
            self.assertTrue(compile_plan('data d;p='+expression+';run;').blocked)
        plan=compile_plan('data d;p=2**3;run;')
        self.assertFalse(plan.blocked)
        self.assertEqual(plan.to_dict()['steps'][0]['operations'][0]['args'], {'name':'binary64-v1'})
        self.assertEqual(run_plan(plan.to_dict())['datasets']['d']['rows'], [{'p':8.}])

    def test_known_numeric_put_keeps_its_serialized_shape(self):
        plan=compile_plan('data d;a=1;put a;run;').to_dict()
        self.assertEqual(plan['steps'][0]['operations'][-1]['args'],{'names':['a']})

    def test_output_only_discovery_has_explicit_provenance(self):
        plan=compile_plan('data d;a=1;put a c;run;')
        self.assertFalse(plan.blocked,plan.tickets)
        self.assertEqual(plan.steps[0].operations[-1].args,{'names':['a','c'],'discover':['c']})
        self.assertIn(('put-numeric-discovery','DS-046',1),plan.matched)
        result,stdout=execute("data d;put c;x=c;put x;put '[' c ']';run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'c':None,'x':None}])
        self.assertEqual(result['log'],['. ','. ','[. ]'])
        self.assertEqual(stdout,'. \n. \n[. ]\n')

    def test_skipped_discovery_is_visible_in_earlier_snapshots(self):
        result,stdout=execute('data d;output;if 0 then put c;run;')
        self.assertEqual(result['datasets']['d'],{'schema':{'c':'number'},'rows':[{'c':None}]})
        self.assertEqual(stdout,'')

    def test_discovery_preserves_order_and_duplicate_output_fields(self):
        result,stdout=execute('data d;put b a b;run;')
        self.assertEqual(list(result['datasets']['d']['schema']),['b','a'])
        self.assertEqual(result['log'],['. . . ']);self.assertEqual(stdout,'. . . \n')

    def test_discovery_in_empty_inline_input_has_static_schema(self):
        result,stdout=execute('data d;input a;put a c;datalines;\n;\nrun;')
        self.assertEqual(result,{'datasets':{'d':{'schema':{'a':'number','c':'number'},'rows':[]}},'log':[]})
        self.assertEqual(stdout,'')

    def test_discovered_scratch_resets_on_inline_rows_and_steps(self):
        text='data d;input a;put c;if a=1 then c=9;datalines;\n1\n2\n;\nrun;data e;put c;run;'
        result,stdout=execute(text)
        self.assertEqual(result['log'],['. ','. ','. ']);self.assertEqual(stdout,'. \n. \n. \n')
        self.assertEqual([r['c'] for r in result['datasets']['d']['rows']],[9.,None])
        self.assertEqual(result['datasets']['e']['rows'],[{'c':None}])

    def test_forged_discovery_shapes_and_scope_refuse(self):
        original=compile_plan('data d;put c;run;').to_dict()
        for marker in (None,[],{},['c','c'],['other'],['_n_'],['C'],[1]):
            plan=deepcopy(original);plan['steps'][0]['operations'][0]['args']['discover']=marker
            with self.subTest(marker=marker),self.assertRaises(ValueError):run_plan(plan)
        for field,value in (('version',1),('kind','sort'),('inputs',['raw'])):
            plan=deepcopy(original)
            if field=='version':plan[field]=value
            else:plan['steps'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):run_plan(plan,raw([]))
        plan=compile_plan('data d;put c d;run;').to_dict()
        plan['steps'][0]['operations'][0]['args']['discover']=['d','c']
        with self.assertRaises(ValueError):run_plan(plan)

    def test_unmarked_legacy_unknown_numeric_plan_still_refuses(self):
        plan=compile_plan('data d;put c;run;').to_dict();del plan['steps'][0]['operations'][0]['args']['discover']
        with self.assertRaises(ValueError):run_plan(plan)

    def test_character_descriptors_and_mixed_unknown_output_stay_refused(self):
        for text in ('data d;length a $3;put a c;run;','data d;put "x" c;run;'):
            self.assertTrue(compile_plan(text).blocked)
        self.assertNotEqual(build_job('data d;put c;length c $3;run;').code,0)

    def test_numeric_put_fraction_width_and_cpp_limits_remain(self):
        self.assertNotEqual(build_job('data d;a=.5;put a c;run;').code,0)
        self.assertTrue(compile_plan('data d;put '+' '.join('v'+str(i) for i in range(33))+';run;').blocked)
        for text in ('data _null_;p=2*3;put p=;run;','data _null_;put c;run;'):
            self.assertEqual(build_job(text,target='cpp').code,2)

    def test_late_dynamic_failure_publishes_no_result_or_stdout(self):
        text='data earlier;put "earlier";run;data d;set raw;p=x*y;put p=;output;run;'
        values=raw([{'x':2.,'y':3.},{'x':46341.,'y':46341.}]);job=job_with_inputs(text,values)
        self.assertEqual(job.code,1);self.assertIsNone(job.result);self.assertFalse(job.receipt['accepted'])
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(text).code,{'inputs':values})
        self.assertEqual(stream.getvalue(),'')

    def test_row_step_run_reset_and_plan_immutability(self):
        plan=compile_plan('data d;set raw;total+x*y;p=x*y;run;').to_dict();before=deepcopy(plan)
        values=raw([{'x':2.,'y':3.},{'x':4.,'y':2.}]);one=run_plan(plan,values)
        self.assertEqual(one,run_plan(plan,values));self.assertEqual(plan,before)
        self.assertEqual([r['total'] for r in one['datasets']['d']['rows']],[6.,14.])

    def check_program(self,path,expected,accounting,source_pin,result_pin,stdout_pin):
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),source_pin)
        observed,stdout=execute(path.read_text());independent,seen=program_witness(path)
        self.assertEqual(observed,expected);self.assertEqual(independent,expected);self.assertEqual(seen,accounting)
        self.assertEqual(digest(observed),result_pin);self.assertEqual(hashlib.sha256(stdout.encode()).hexdigest(),stdout_pin)

    def test_original_complete_program(self):
        self.check_program(ORIGINAL,original_expected(),original_accounting(),
            'c35ccb83772eea46cc5bc5a922e5537887dfd9cb18729227aef0e1542aa5658a',
            'd5205bb84b08a3e6de7dc3d936f3d3b5cb0f845e68dc4605d97dba42af2dcd64',
            '4ec6ca19bea3d45c44a40846f0aead89023664ac2ccd81610ec509563b27bfc6')

    def test_entire_unchanged_array_sum_program(self):
        path=ROKU_CORPUS/'sum_and_product_of_an_array.sas'
        self.check_program(path,array_expected(),array_accounting(),
            '06eca942365b06dec7e0f99b077856b4b33391e8addee0b39a44c0170987ea1a',
            '50083e57b54be2f314d78b7900011d114d447e2091b63eedcb71f4f66123ffcc',
            '891d070ad83d719883b9b10e3e2ce42bf0aaa74fa560f55281ea6e0ad178e3ca')
        print('VERIFIED corpus: sum_and_product_of_an_array.sas; complete source/result/stdout,100 squares,missing c,independent R and source/emitted/CLI; no live SAS')

    def test_actual_cli_whole_programs(self):
        for path,expected in ((ORIGINAL,original_expected()),(ROKU_CORPUS/'sum_and_product_of_an_array.sas',array_expected())):
            with tempfile.TemporaryDirectory() as directory:
                out=Path(directory)/'job';r=subprocess.run([sys.executable,'-m','saschi','run',str(path),'--output',str(out)],capture_output=True,text=True,timeout=30)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)
                self.assertEqual(json.loads((out/'result.json').read_text()),expected)
                receipt=json.loads((out/'receipt.json').read_text());self.assertTrue(receipt['accepted'])
                self.assertEqual(receipt['source_sha256'],hashlib.sha256(path.read_bytes()).hexdigest())

    def test_comparator_and_exact_log_controls(self):
        expected=original_expected();table=expected['datasets']['capture']
        for change in ('value','order','multiplicity','schema'):
            bad=deepcopy(table)
            if change=='value':bad['rows'][0]['product']=13.
            elif change=='order':bad['rows'].reverse()
            elif change=='multiplicity':bad['rows'].append(deepcopy(bad['rows'][0]))
            else:bad['schema']=dict(reversed(list(bad['schema'].items())))
            self.assertFalse(equal(table,bad,ordered_maps=True))
        self.assertNotEqual(expected['log'],['7 24 0 ','48 '])
        self.assertNotEqual(expected['log'],list(reversed(expected['log'])))

    def test_independent_R_consumes_entire_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bad.sas';path.write_text(ORIGINAL.read_text()+'proc print;run;')
            with self.assertRaises(subprocess.CalledProcessError):program_witness(path)


if __name__=='__main__':unittest.main()
