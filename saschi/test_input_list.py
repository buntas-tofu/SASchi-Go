"""DS-044 source, portable plans, complete programs and refusal controls."""
import contextlib
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from examples.verify_input_list import (PINS, REFUSALS, ORIGINAL, source, rrun,
    original_expected, comparison_expected, program_witness)
from sas_semantics import sas_input_number, sas_input_records
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .rules import route_statement
from .test_do_counted import execute
from .test_parser import ROKU_CORPUS


def digest(result):
    return hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class InputListTests(unittest.TestCase):
    def test_hand_pins_and_refusals(self):
        for records,width,expected in PINS:self.assertEqual(sas_input_records(records,width),expected)
        for records,width in REFUSALS:
            with self.subTest(records=records),self.assertRaises(ValueError):sas_input_records(records,width)

    def test_reference_types_and_bounds(self):
        for token in (None,True,1,{},[], '', '0'*33):
            with self.assertRaises(ValueError):sas_input_number(token)
        for records,width in (((),1),(None,1),([None],1),(['1'],True),(['1'],1.0),(['1'],0),(['1'],33),(['1']*10001,1)):
            with self.assertRaises(ValueError):sas_input_records(records,width)
        self.assertEqual(len(sas_input_records(['1']*10000,1)),10000)
        self.assertEqual(sas_input_records(['1'+' '*79],1),[[1.]])
        self.assertEqual(sas_input_records([' '.join(['1']*32)],32),[[1.]*32])

    def test_aliases_case_and_source_provenance(self):
        self.assertEqual(route_statement('input a b','data')[0],'input-list')
        for keyword in ('CARDS','datalines'):
            p=compile_plan(source(['1 2'],['A','B'],header=keyword));self.assertFalse(p.blocked,p.tickets)
            op=p.steps[0].operations[0];self.assertEqual(op.kind,'input_list')
            self.assertEqual(op.args,{'names':['a','b'],'records':['1 2'],'data_line':2})
            self.assertIn(('input-list','DS-044',1),p.matched)
            self.assertEqual(execute(source(['1 2'],header=keyword))[0]['datasets']['d']['rows'],[{'a':1.,'b':2.}])

    def test_source_names_require_ascii_before_normalizing_case(self):
        for name in ('K','aK','İ','ſ','ı'):
            with self.subTest(name=name):
                self.assertTrue(compile_plan(source(['1'],names=[name])).blocked)
        plan=compile_plan(source(['1 2 3'],names=['A','Input','_value']))
        self.assertFalse(plan.blocked,plan.tickets)
        self.assertEqual(plan.steps[0].operations[0].args['names'],['a','input','_value'])
        self.assertEqual(run_plan(plan.to_dict())['datasets']['d']['rows'],[{'a':1.,'input':2.,'_value':3.}])

    def test_crlf_and_blank_records(self):
        text=source(['','1','','2','']).replace('\n','\r\n')
        self.assertEqual(execute(text)[0]['datasets']['d']['rows'],[{'a':1.,'b':2.}])

    def test_flowover_release_and_eof_are_distinct(self):
        result,_=execute(source(['1','2 77','3 4 55','6'],body='seq=_n_;'))
        self.assertEqual(result['datasets']['d']['rows'],[{'a':1.,'b':2.,'seq':1.},{'a':3.,'b':4.,'seq':2.}])

    def test_empty_input_has_complete_skipped_schema(self):
        result,stdout=execute(source([],body='if 0 then extra=1;put a=;'))
        self.assertEqual(result,{'datasets':{'d':{'schema':{'a':'number','b':'number','extra':'number'},'rows':[]}},'log':[]})
        self.assertEqual(stdout,'')

    def test_static_types_checked_even_on_empty_input(self):
        for records in ([],['1 2']):
            self.assertEqual(build_job(source(records,prefix='length a $3;')).code,1)
            self.assertEqual(build_job(source(records,body="if 0 then a='x';")).code,1)

    def test_predicate_types_refuse_on_empty_and_skipped_paths(self):
        bodies=("if a='x' then output;", "if 'x'=a then output;", "if 'x' then output;",
                "if a='x';", "if 'x';", "if 1 then output;else if a='x' then output;",
                "if c=a then output;", "if c then output;")
        for records in ([],['1 2']):
            for body in bodies:
                with self.subTest(records=records,body=body):
                    job=build_job(source(records,prefix='length c $3;',body=body))
                    self.assertEqual(job.code,1);self.assertIsNone(job.result)
                    self.assertFalse(job.receipt['accepted'])

    def test_operand_types_refuse_on_empty_and_skipped_paths(self):
        expressions=("a+'x'", "mod(a,'x')", "sum(a,'x')", "min(a,'x')", "max(a,'x')",
                     "round(a,'x')", "count(a,'x')", "input(a)", "put('x',8.2)")
        for records in ([],['1 2']):
            for expr in expressions:
                for body in (f'x={expr};',f'if 0 then x={expr};',f'if 1 then output;else x={expr};'):
                    with self.subTest(records=records,body=body):
                        job=build_job(source(records,body=body))
                        self.assertIn(job.code,(1,2));self.assertIsNone(job.result)
                        self.assertFalse(job.receipt['accepted'])

    def test_static_types_preserve_explicit_conversion_and_character_composition(self):
        body=("c='12';parsed=input(c);ordinary=input(.);width=length(a);hits=count(c,'1');"
              "formatted=put(a,8.2);backward=reverse(c);total=sum(a,b);if c='12' then output;")
        for records in ([],['1 2']):
            job=build_job(source(records,prefix='length c $3;',body=body))
            self.assertEqual(job.code,0,job.receipt.get('error'))
            rows=job.result['datasets']['d']['rows']
            if not records:self.assertEqual(rows,[])
            else:self.assertEqual(rows,[{'c':'12 ','a':1.,'b':2.,'parsed':12.,'ordinary':None,
                                        'width':12.,'hits':1.,'formatted':'    1.00','backward':' 21','total':3.}])
            tagged=build_job(source(records,body='tagged=.A;if tagged=.A then output;'))
            self.assertEqual(tagged.code,0,tagged.receipt.get('error'))
            self.assertEqual(tagged.result['datasets']['d']['rows'],
                             [{'a':1.,'b':2.,'tagged':{'missing':'A'}}] if records else [])

    def test_forged_empty_predicate_and_expression_shapes_refuse(self):
        original=compile_plan(source([],body='if a>0;')).to_dict()
        bad_tests=({}, {'op':'truth'}, {'op':[],'left':{'kind':'number','value':1}},
                   {'op':'other','left':{'kind':'number','value':1}},
                   {'op':'truth','left':{'kind':'character','value':'x'}},
                   {'op':'=','left':{'kind':'variable','value':'a'},'right':{'kind':'character','value':'x'}},
                   {'op':'truth','left':{'kind':'unknown','value':1}},
                   {'op':'truth','left':{'kind':'number','value':True}},
                   {'op':'truth','left':{'kind':'call','name':'sum','args':[]}},
                   {'op':'truth','left':{'kind':'call','name':'sum','args':[{'kind':'character','value':'x'}]}},
                   {'op':'truth','left':{'kind':'call','name':'sum','args':[{'kind':'format','name':'','w':8,'d':2}]}},
                   {'op':'truth','left':{'kind':'variable','value':[]}},
                   {'op':'truth','left':{'kind':'automatic','value':'unknown'}},
                   {'op':'truth','left':{'kind':'tagged_missing','value':{'missing':'bad'}}})
        for test in bad_tests:
            p=deepcopy(original);p['steps'][0]['operations'][1]['args']['condition']=test
            with self.subTest(test=test),self.assertRaises(ValueError):run_plan(p)
        formatted=compile_plan(source([],body='x=put(a,8.2);')).to_dict()
        for key,value in (('w',0),('w',32768),('d',-1),('d',True),('name','yymmdd')):
            p=deepcopy(formatted);p['steps'][0]['operations'][1]['args']['value']['args'][1][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):run_plan(p)
        rounded=compile_plan(source([],body='x=round(a,b);')).to_dict()
        del rounded['steps'][0]['operations'][1]['args']['unit']
        with self.assertRaises(ValueError):run_plan(rounded)
        declared=compile_plan(source([],prefix='length c $3;')).to_dict()
        for key,value in (('name','_n_'),('name',[]),('spec',{'type':'character','length':0})):
            p=deepcopy(declared);p['steps'][0]['operations'][0]['args'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):run_plan(p)

    def test_forged_empty_retain_initializers_refuse(self):
        original=compile_plan(source([])).to_dict()
        for initial in ({'kind':'character','value':'x'}, {'kind':'variable','value':'a'},
                        {'kind':'number','value':True}, {'kind':'number','value':float('inf')},
                        {'kind':'missing','value':0}, {'kind':'number','value':1,'extra':True}):
            p=deepcopy(original);p['steps'][0]['retained']={'x':initial}
            with self.subTest(initial=initial),self.assertRaises(ValueError):run_plan(p)
        p=deepcopy(original);p['steps'][0]['retained']={'_n_':{'kind':'number','value':7}}
        with self.assertRaises(ValueError):run_plan(p)

    def test_input_overwrites_retained_target_and_resets_scratch(self):
        result,_=execute(source(['1 2','3 4'],prefix='retain a 7;',body='before=scratch;scratch=a;a=99;'))
        self.assertEqual(result['datasets']['d']['rows'],[{'a':99.,'b':2.,'before':None,'scratch':1.},
                                                                     {'a':99.,'b':4.,'before':None,'scratch':3.}])

    def test_row_run_step_reset_and_plan_immutability(self):
        text=source(['1 2','3 4'],body='total+a;seq=_n_;')+source(['5 6'],body='total+a;seq=_n_;').replace('data d;','data e;')
        p=compile_plan(text).to_dict();before=deepcopy(p);a=run_plan(p);b=run_plan(p)
        self.assertEqual(a,b);self.assertEqual(p,before)
        self.assertEqual(a['datasets']['d']['rows'][-1]['total'],4.)
        self.assertEqual(a['datasets']['e']['rows'],[{'a':5.,'b':6.,'total':5.,'seq':1.}])

    def test_explicit_output_snapshots_and_suppression(self):
        result,_=execute(source(['1 2','3 4'],body='output;a=9;output;'))
        self.assertEqual([r['a'] for r in result['datasets']['d']['rows']],[1.,9.,3.,9.])
        result,_=execute(source(['1 2'],body='if 0 then output;'))
        self.assertEqual(result['datasets']['d']['rows'],[])

    def test_subset_and_lag_schedule_use_completed_input_rows(self):
        result,_=execute(source(['1 2','3 4','5'],body='previous=lag(a);if a>1;seq=_n_;'))
        self.assertEqual(result['datasets']['d']['rows'],[{'a':3.,'b':4.,'previous':1.,'seq':2.}])

    def test_missing_and_numeric_formats_keep_existing_put_bounds(self):
        result,stdout=execute(source(['. 2','3 .'],body="put a b;put '[' a b ']';"))
        self.assertEqual(result['log'],['. 2 ','[. 2 ]','3 . ','[3 . ]']);self.assertEqual(stdout,'\n'.join(result['log'])+'\n')
        self.assertEqual(build_job(source(['.5 1'],body='put a b;')).code,1)

    def test_opaque_unused_fields_never_become_code_or_tickets(self):
        result,_=execute(source(['1 2 /* _ERROR_ " &macro %run',"3 4 'unterminated"],body='put a= b=;'))
        self.assertEqual(result['log'],['a=1 b=2','a=3 b=4'])
        self.assertEqual(len(result['datasets']['d']['schema']),2)

    def test_consumed_invalid_and_incomplete_bad_final_read_refuse(self):
        for records in (['1 x'],['1 2','x'],['1 2','0.1'],['1 2','7','x']):
            job=build_job(source(records));self.assertEqual(job.code,2);self.assertIsNone(job.result)
        self.assertEqual(build_job(source(['1 2','7'])).code,0)

    def test_input_position_names_and_forms_refuse(self):
        variants=['input;','input a a;','input a A;','input a $ b;','input a 8. b;','input a @;','input a @@;',
                  'input a-b;','input a=;','input (a b) (8.);','input _n_;','if 0 then input a b;','input a b;input c;']
        for variant in variants:
            with self.subTest(variant=variant):self.assertTrue(compile_plan(source(['1 2']).replace('input a b;',variant)).blocked)
        self.assertTrue(compile_plan(source(['1 2'],prefix='x=1;')).blocked)
        self.assertTrue(compile_plan(source(['1 2'],names=[f'x{i}' for i in range(33)])).blocked)

    def test_inline_declarations_and_outside_tail_refuse(self):
        variants=[source(['1 2'],header='lines'),source(['1 2'],header='cards4').replace(';\nrun;',';;;;\nrun;'),
                  'data d;input a b;run;', 'data d;cards;\n1 2\n;\nrun;',
                  source(['1 2']).replace('datalines;\n','datalines; 1 2\n'),
                  source(['1 2']).replace(';\nrun;',';\nx=4;run;'),
                  source(['1 2'])+'datalines;\n3 4\n;\n',
                  source(['1 2']).replace(';\nrun;','run;')]
        for text in variants:
            with self.subTest(text=text):self.assertTrue(compile_plan(text).blocked)

    def test_external_input_and_control_compositions_refuse(self):
        for body in ('set raw;','merge raw;by a;','where a>1;','infile datalines missover;',
                     'array z a b;','do i=1 to 2;output;end;','do until(a>1);a=a+1;end;','put _all_;'):
            with self.subTest(body=body):self.assertTrue(compile_plan(source(['1 2'],body=body)).blocked)
        self.assertEqual(build_job(source(['1 2']),target='cpp').code,2)

    def test_serialized_plan_shapes_validate_without_source_compiler(self):
        original=compile_plan(source([])).to_dict()
        bad_args=[{},None,[],{'names':['a']}, {'names':['a'],'records':[],'data_line':2,'extra':True}]
        for args in bad_args:
            p=deepcopy(original);p['steps'][0]['operations'][0]['args']=args
            with self.assertRaises(ValueError):run_plan(p)
        for key,values in {'names':[[],['a','a'],['A'],['_n_'],['a',3],('a',)],
                           'records':[None,(),[3],['0.1'],['1']*10001],
                           'data_line':[0,1,True,2.5,'2']}.items():
            for value in values:
                p=deepcopy(original);p['steps'][0]['operations'][0]['args'][key]=value
                with self.subTest(key=key,value=str(value)[:40]),self.assertRaises(ValueError):run_plan(p)

    def test_forged_version_scope_and_nested_read_refuse(self):
        original=compile_plan(source([])).to_dict()
        for change in ('version','kind','line','duplicate','if','unknown','prior','where','inputs'):
            p=deepcopy(original);step=p['steps'][0];op=step['operations'][0]
            if change=='version':p['version']=1
            elif change=='kind':step['kind']='merge'
            elif change=='line':op['line']=True
            elif change=='duplicate':step['operations'].append(deepcopy(op))
            elif change in ('if','unknown'):step['operations']=[{'kind':change,'line':1,'args':{'condition':{'left':{'kind':'number','value':0},'op':'truth'},'operation':op}}]
            elif change=='prior':step['operations'].insert(0,{'kind':'put_literal','line':1,'args':{'literals':["'x'"]}})
            elif change=='where':step['where']={'left':{'kind':'number','value':0},'op':'truth'}
            else:step['inputs']=['raw']
            with self.subTest(change=change),self.assertRaises(ValueError):run_plan(p)

    def test_late_step_and_row_failure_publish_no_stdout_or_result(self):
        text="data earlier;x=1;put x=;run;"+source(['1 2','.5 3'],body='put a b;output;')
        job=build_job(text);self.assertEqual(job.code,1);self.assertIsNone(job.result);self.assertFalse(job.receipt['accepted'])
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(text).code,{})
        self.assertEqual(stream.getvalue(),'')

    def test_partial_mode_cannot_accept_invalid_input(self):
        text=source(['0.1 2']);translated=translate(text,allow_partial=True)
        self.assertTrue(translated.blocked)
        with self.assertRaises(ValueError):exec(translated.code,{})

    def check_cli(self,path,expected):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'out'
            p=subprocess.run([sys.executable,'-m','saschi','run',str(path),'--output',str(out)],capture_output=True,text=True,timeout=30)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            self.assertEqual(json.loads((out/'result.json').read_text()),expected)
            receipt=json.loads((out/'receipt.json').read_text());self.assertTrue(receipt['accepted'])
            self.assertEqual(receipt['source_sha256'],hashlib.sha256(path.read_bytes()).hexdigest())

    def test_original_whole_program_hand_R_emitted_CLI(self):
        self.assertEqual(hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(),'86eca29a62b7672013c29d31d5ed3f664561bc3538100048d4100dcaa618edaf')
        result,stdout=execute(ORIGINAL.read_text());independent,accounting=program_witness(ORIGINAL)
        self.assertEqual(result,original_expected());self.assertEqual(independent,result)
        self.assertEqual(accounting,{'statements':13,'steps':['capture'],'reads':[3]})
        self.assertEqual(stdout,'total=1 seq=1\ntotal=1 seq=2\ntotal=5 seq=3\n')
        self.assertEqual(digest(result),'df9454f43db2e0546118993f66d9843610b1242a3b00ffe33a8ec12b263774ba')
        self.assertEqual(hashlib.sha256(stdout.encode()).hexdigest(),'66b5baec970c71d09eda39dbd16da8501f5b173278c03d76b573ada7bdf69d31')
        self.check_cli(ORIGINAL,result)

    def test_comparator_value_order_schema_multiplicity_controls(self):
        for change in ('value','order','schema','multiplicity'):
            expected=original_expected()['datasets'];table=expected['capture']
            if change=='value':table['rows'][0]['a']=9
            elif change=='order':table['rows'].reverse()
            elif change=='schema':table['schema']=dict(reversed(list(table['schema'].items())))
            else:table['rows'].append(deepcopy(table['rows'][0]))
            with tempfile.TemporaryDirectory() as d:
                path=Path(d)/'expected.json';path.write_text(json.dumps(expected))
                job=build_job(ORIGINAL.read_text(),expect=path)
            self.assertEqual(job.code,1);self.assertFalse(job.receipt['accepted']);self.assertEqual(job.result,original_expected())

    def test_entire_unchanged_integer_comparison_program(self):
        path=ROKU_CORPUS/'integer_comparison.sas'
        if not path.is_file():self.skipTest('Roku corpus not present')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),'bfe81fc2f69fbf081a4687c63ff1732f8cc3e2e4a495330dc9583a20ccab2497')
        expected=comparison_expected();result,stdout=execute(path.read_text());independent,accounting=program_witness(path)
        self.assertEqual(result,expected);self.assertEqual(independent,expected)
        self.assertEqual(digest(result),'cdde22b438ef225e6c0113b14f6d9eba102e183968b1068d4bfa7cd32bf9691f')
        self.assertEqual(hashlib.sha256(stdout.encode()).hexdigest(),'9de674d4d85a9a8f3ff66e3f93269d2e37df804d85a15b4c186a53c887e18c3a')
        self.assertEqual(accounting,{'statements':18,'steps':['_null_'],'reads':[3]})
        self.assertEqual(len(result['log']),23);self.assertEqual(stdout,'\n'.join(expected['log'])+'\n')
        job=build_job(path.read_text());self.assertEqual(job.code,0);self.assertEqual(job.result,expected)
        self.check_cli(path,expected)
        for wrong in (expected['log'][::-1],expected['log'][:-1],expected['log']*2,expected['log'][1:]):self.assertNotEqual(result['log'],wrong)
        print('VERIFIED corpus: integer_comparison.sas; complete source/result/stdout pins, hand truth table, independent base R and source/emitted/CLI; no live SAS')

    def test_independent_R_consumes_entire_program_and_rejects_mutations(self):
        original=ORIGINAL.read_text()
        for text in (original+'put "tail";',original.replace('run;',''),original.replace('input a b;','input a b @;'),
                     original.replace('2 999','x 999'),original.replace('output;','unknown;',1)):
            with tempfile.TemporaryDirectory() as d:
                path=Path(d)/'bad.sas';path.write_text(text)
                with self.assertRaises(subprocess.CalledProcessError):rrun('program',path)


if __name__=='__main__':unittest.main()
