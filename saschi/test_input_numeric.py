"""DS-058/059 source, forged plans, record state and complete job boundaries."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from examples.verify_inline_csv import (ORIGINAL,SOURCE_PIN,RESULT_PIN,STDOUT_PIN,
    source,execute,original_expected,program_witness,witnesses,hand_cases,refusal_cases,
    cli_check,cli_wrong_controls,range_comparator_controls)
from saschi.input_numeric import PROFILE,decode,expand_terms,parse_terms,parse_infile
from saschi.plan import compile_plan
from saschi.runtime import run_plan
from saschi.job import build_job

ROOT=Path(__file__).resolve().parents[1]


class NumericInputTests(unittest.TestCase):
    def test_comma_hand_pins_source_and_R(self):
        pins=hand_cases('csv');independent=witnesses([s for s,_ in pins])
        for (text,expected),answer in zip(pins,independent):
            self.assertEqual(execute(text,emitted=True),expected)
            self.assertIsNotNone(answer);self.assertEqual(answer[0],expected)

    def test_range_hand_pins_source_and_R(self):
        pins=hand_cases('ranges');independent=witnesses([s for s,_ in pins])
        for (text,expected),answer in zip(pins,independent):
            self.assertEqual(execute(text,emitted=True),expected)
            self.assertIsNotNone(answer);self.assertEqual(answer[0],expected)

    def test_empty_commas_collapse_and_short_records_flow(self):
        self.assertEqual(decode(['1,,2,',',3,99','4,5,6'],3,',',1),[[1.,2.,3.],[4.,5.,6.]])
        self.assertEqual(decode([',,,','  ','1','2,ignored'],2,',',1),[[1.,2.]])

    def test_firstobs_counts_physical_records_not_values(self):
        self.assertEqual(decode(['bad header','','1,2'],2,',',2),[[1.,2.]])
        self.assertEqual(decode(['bad'],1,',',10001),[])
        for text in (source(['1,'+'('*33],names='a'),source(['('*33,'1'],names='a',firstobs=2)):
            expected={'datasets':{'d':{'schema':{'a':'number'},'rows':[{'a':1.}]}},'log':[]}
            self.assertEqual(execute(text,emitted=True),expected)
            self.assertEqual(witnesses([text])[0][0],expected)
        self.assertTrue(compile_plan(source(['('*33],names='a')).blocked)
        for record in ('x'*81,'é','1\t2',';'):
            with self.assertRaises(ValueError):decode([record],1,',',10001)

    def test_consumed_blank_field_refuses_but_unused_suffix_does_not(self):
        with self.assertRaises(ValueError):decode(['1, ,2'],2,',',1)
        self.assertEqual(decode(['1, ,bad'],1,',',1),[[1.]])
        self.assertEqual(decode(['    '],1,',',1),[])

    def test_invalid_consumed_token_before_incomplete_eof_refuses(self):
        for records in (['bad'],['1','bad'],['1,2','bad']):
            with self.assertRaises(ValueError):decode(records,2,',',1)
        self.assertEqual(decode(['1,2','7'],2,',',1),[[1.,2.]])

    def test_existing_decimal_and_physical_limits_are_unchanged(self):
        self.assertEqual(decode(['+1.25,-2.5','5e-1,.'],2,',',1),[[1.25,-2.5],[.5,None]])
        for token in ('0.1','1e-15','2147483648','1234567890123456','.A','NaN','"1"'):
            with self.subTest(token=token),self.assertRaises(ValueError):decode([token],1,',',1)
        self.assertEqual(len(decode(['1']*10000,1,',',1)),10000)
        with self.assertRaises(ValueError):decode(['1']*10001,1,',',1)

    def test_range_bounds_and_final_digit_run(self):
        self.assertEqual(expand_terms(['x11-x13']),['x11','x12','x13'])
        self.assertEqual(expand_terms(['v63-v64','x99']),['v63','v64','x99'])
        self.assertEqual(parse_terms(' X1 - X2  tail ')[0],['x1-x2','tail'])
        for terms in (['x01-x02'],['x0-x1'],['x2-x1'],['x1-y2'],['x1-x65'],['x1-x33'],
                      ['x1-x2','x2'],['x1--x2'],['x1-x2','_n_'],['x19-x111'],['x999999999999999999999999-x999999999999999999999999']):
            with self.subTest(terms=terms),self.assertRaises(ValueError):expand_terms(terms)

    def test_source_ascii_checked_before_case_normalization(self):
        for name in ('K','aK','K1-K2'):
            for comma in (False,True):
                self.assertTrue(compile_plan(source(['1 2'],names=name,comma=comma)).blocked)

    def test_infile_complete_options_and_position(self):
        from saschi.rules import route_statement
        self.assertEqual(route_statement("infile datalines dlm=','"),('inline-csv','DS-058'))
        for spelling in ('input x1-x2','input\nx1-x2','input\tx1 -\n x2'):
            self.assertEqual(route_statement(spelling),('input-ranges','DS-059'))
        self.assertEqual(route_statement('input a b'),('input-list','DS-044'))
        self.assertEqual(parse_infile('INFILE CARDS FIRSTOBS=2 DLM=","'),{'delimiter':',','firstobs':2})
        for text in ("infile datalines dsd","infile datalines dlm=';'","infile datalines dlm=',' firstobs=02",
                     "infile datalines dlm=',' firstobs=2 firstobs=3","infile external dlm=','"):
            with self.subTest(text=text),self.assertRaises(ValueError):parse_infile(text)
        for prefix in ("x=1;infile datalines dlm=',';","infile datalines dlm=',';infile datalines dlm=',';"):
            self.assertTrue(compile_plan(source(['1 2'],comma=False,prefix=prefix)).blocked)

    def test_old_plain_input_shape_and_refusals_remain(self):
        p=compile_plan(source(['1 2'],names='a b',comma=False)).to_dict()
        from saschi.emit_cpp import translate as cpp_translate
        cpp_source=source(['1,2']).replace('data d;','data _null_;')
        self.assertFalse(compile_plan(cpp_source).blocked)
        cpp=cpp_translate(cpp_source);self.assertTrue(cpp.blocked)
        self.assertTrue(any(ticket.statement=='input_numeric' and 'scalar numeric pilot' in ticket.reason for ticket in cpp.tickets))
        self.assertEqual(p['steps'][0]['operations'][0],{'kind':'input_list','line':1,
                         'args':{'names':['a','b'],'records':['1 2'],'data_line':2}})
        for text in (source(['1 2'],names='a-b',comma=False),source([],prefix='infile datalines missover;',comma=False)):
            self.assertTrue(compile_plan(text).blocked)

    def test_forced_old_operation_refuses_new_metadata(self):
        for comma in (False,True):
            p=compile_plan(source(['1 2'] if not comma else ['1,2'],comma=comma)).to_dict()
            p['steps'][0]['operations'][0]['kind']='input_list'
            with self.assertRaises(ValueError):run_plan(p)

    def test_new_profile_stale_or_forged_fields_refuse_empty(self):
        original=compile_plan(source([])).to_dict()
        for key,value in (('profile','other'),('profile',None),('terms',['x1','x2']),('names',['x2','x1']),
                          ('firstobs',True),('firstobs',0),('firstobs',10002),('infile_line',True),
                          ('data_line',True),('delimiter',';'),('records',()),('unknown','ignored')):
            p=deepcopy(original);args=p['steps'][0]['operations'][0]['args'];args[key]=value
            # Explicit names still have a real comma trigger, so this is valid.
            if key=='terms':args['delimiter']=' ';args['infile_line']=None
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):run_plan(p)
        for version in (2.0,'2',True,None):
            p=deepcopy(original);p['version']=version
            with self.subTest(version=version),self.assertRaises(ValueError):run_plan(p)

    def test_exact_step_shape_and_typed_metadata_on_empty_and_skipped(self):
        for records in ([],['1,2']):
            original=compile_plan(source(records,body='if 0 then future=1;')).to_dict()
            for key,value in (('ignored_extra','lost'),('nodupkey',0),('inputs',{}),('by',()),('where',{}),
                              ('line',True),('display_names',[]),('retained',[]),('lengths',{'phantom':3})):
                p=deepcopy(original);p['steps'][0][key]=value
                with self.subTest(records=records,key=key),self.assertRaises(ValueError):run_plan(p)

    def test_reserved_retained_targets_and_dead_references_refuse(self):
        for records in ([],['1,2']):
            original=compile_plan(source(records,body='if 0 then future=x1;')).to_dict()
            for name in ('_error_','_all_','_numeric_','_character_','_infile_','_file_','_n_'):
                p=deepcopy(original);p['steps'][0]['retained'][name]={'kind':'number','value':0.}
                with self.subTest(name=name),self.assertRaises(ValueError):run_plan(p)
                p=deepcopy(original);p['steps'][0]['operations'][1]['args']['operation']['args']['name']=name
                with self.assertRaises(ValueError):run_plan(p)
                p=deepcopy(original);p['steps'][0]['operations'][1]['args']['operation']['args']['value']={'kind':'variable','value':name}
                with self.assertRaises(ValueError):run_plan(p)

    def test_deep_source_rejects_before_recursive_parser(self):
        text=source(['1 2'],comma=False,body='y='+'round('*1000+'1'+',1)'*1000+';')
        self.assertTrue(compile_plan(text).blocked)
        self.assertTrue(compile_plan(source(['1 2'],comma=False,body='y='+'1+'*1000+'1;')).blocked)

    def test_character_companion_metadata_is_preserved_and_input_stays_numeric(self):
        for records in ([],['1,2']):
            text=source(records,prefix='length c $3;',body="c='ok';")
            result=execute(text,emitted=True);schema=result['datasets']['d']['schema']
            self.assertEqual(list(schema),['c','x1','x2']);self.assertEqual(schema['c'],{'type':'character','length':3})
            self.assertEqual(result['datasets']['d']['rows'],[{'c':'ok ','x1':1.,'x2':2.}] if records else [])
            forged=compile_plan(text).to_dict();forged['steps'][0]['operations'].insert(1,deepcopy(forged['steps'][0]['operations'][0]))
            with self.assertRaises(ValueError):run_plan(forged)
            self.assertTrue(compile_plan(source(records,prefix='length x1 $3;')).blocked is False)
            with self.assertRaises(ValueError):execute(source(records,prefix='length x1 $3;'))

    def test_forged_nested_input_hidden_or_unknown_operation_refuses(self):
        original=compile_plan(source([])).to_dict();op=original['steps'][0]['operations'][0]
        p=deepcopy(original);p['steps'][0]['operations']=[{'kind':'if','line':1,'args':{'condition':{'op':'truth','left':{'kind':'number','value':0}},'operation':deepcopy(op)}}]
        with self.assertRaises(ValueError):run_plan(p)
        p=deepcopy(original);p['steps'][0]['operations'][0]['args']['extra']=True
        with self.assertRaises(ValueError):run_plan(p)
        p=deepcopy(original);p['steps'][0]['operations'].append({'kind':'future','line':1,'args':{}})
        with self.assertRaises(ValueError):run_plan(p)

    def test_static_unknown_expressions_and_d1_crossings_refuse(self):
        for body in ('if 0 then bad=sqrt(x1);','trigger=1**1;','array a{1} x;',
                     'do while(0);x1=1;end;','do until(1);x1=1;end;', 'do i=1 to 2;output;end;'):
            for records in ([],['1,2']):self.assertTrue(compile_plan(source(records,body=body)).blocked,body)

    def test_source_and_plan_caller_are_not_mutated(self):
        p=compile_plan(source(['1,2'],body='x1=99;')).to_dict();before=deepcopy(p)
        catalog={'raw':{'schema':{'z':'number'},'rows':[{'z':7}]}};saved=deepcopy(catalog)
        run_plan(p,catalog);self.assertEqual(p,before);self.assertEqual(catalog,saved)

    def test_retained_overwrite_scratch_and_snapshots(self):
        text=source(['1,2','.,4'],prefix='retain x1 9;',body='before=scratch;scratch=x1;output;x1=99;output;')
        rows=execute(text)['datasets']['d']['rows']
        self.assertEqual([r['x1'] for r in rows],[1.,99.,None,99.]);self.assertTrue(all(r['before'] is None for r in rows))
        self.assertEqual([r['scratch'] for r in rows],[1.,1.,None,None])

    def test_skipped_output_suppresses_implicit_output_on_every_read(self):
        result=execute(source(['1,2'],body='if 0 then output;'))
        self.assertEqual(result['datasets']['d']['rows'],[])

    def test_static_and_late_dynamic_failure_are_atomic_actual_cli(self):
        for text in (source(['1,2','bad'],body='put "BUFFERED";'),
                     source(['1,2','2147483647,2'],body='p=x1*x2;put p=;')):
            text='data earlier;put "EARLY";run;'+text
            job=build_job(text);self.assertNotEqual(job.code,0);self.assertIsNone(job.result)
            with tempfile.TemporaryDirectory() as directory:
                folder=Path(directory);path=folder/'bad.sas';path.write_text(text);out=folder/'out'
                process=subprocess.run([sys.executable,'-m','saschi','run',str(path),'--output',str(out)],cwd=ROOT,capture_output=True,text=True,timeout=45)
                self.assertNotEqual(process.returncode,0);self.assertNotIn('BUFFERED',process.stdout);self.assertNotIn('EARLY',process.stdout)
                self.assertFalse((out/'result.json').exists());self.assertFalse(json.loads((out/'receipt.json').read_text())['accepted'])

    def test_original_whole_source_R_emitted_and_actual_cli(self):
        expected=original_expected();self.assertEqual(execute(ORIGINAL.read_text(),emitted=True),expected)
        independent,counts=program_witness(ORIGINAL);self.assertEqual(independent,expected)
        self.assertEqual(counts,{'statements':20,'steps':['capture','ranges'],'reads':[3,2]})
        self.assertEqual(hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(),SOURCE_PIN)
        self.assertEqual(hashlib.sha256(json.dumps(expected,separators=(',',':')).encode()).hexdigest(),RESULT_PIN)
        self.assertEqual(hashlib.sha256(''.join(x+'\n' for x in expected['log']).encode()).hexdigest(),STDOUT_PIN)
        cli_check(ORIGINAL.read_text(),expected)

    def test_actual_dataset_comparator_controls(self):
        self.assertEqual(cli_wrong_controls(),9)

    def test_range_endpoint_order_padding_and_direction_comparators(self):
        self.assertEqual(range_comparator_controls(),4)

    def test_R_consumes_all_source_and_refusals(self):
        text=source(['1,2'],body='put \"A  B\" \" C\";')
        result=execute(text,emitted=True);self.assertEqual(result['log'],['A  B C'])
        self.assertEqual(witnesses([text])[0][0],result)
        original=ORIGINAL.read_text()
        for text in (original+'put "tail";',original.replace('run;','',1),original.replace('input x1-x2;','input x1-x2 @;')):
            self.assertEqual(witnesses([text]),[None])
        for mode in ('csv','ranges'):
            cases=refusal_cases(mode)
            self.assertTrue(all(answer is None for answer in witnesses(cases)))


if __name__=='__main__':unittest.main()
