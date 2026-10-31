"""Source, portable, pure-buffer and physical publication D2b regression checks."""
from argparse import Namespace
from copy import deepcopy
import contextlib
import io
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from saschi.cli import main as cli_main
from saschi.emit_cpp import translate as cpp_translate
from saschi.emit_py import translate
from saschi.job import build_job
from saschi.plan import compile_plan
from saschi.runtime import run_plan
from saschi.numeric_exchange import (PROFILE,MAX_EVENTS,expand_terms,parse_terms,destination,
                                    validate_step,execute_step,export_manifest,validate_exports,
                                    read_expected_exports)
from examples.verify_numeric_exchange import (ORIGINAL,CORPUS,source,execute,witnesses,original_expected,
                                              corpus_expected,assert_original,cli_check,trace_accounting)


class NumericExchangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original=ORIGINAL.read_text()
        cls.corpus=CORPUS.read_text() if CORPUS.exists() else None
        cls.witnesses=witnesses([cls.original]+([cls.corpus] if cls.corpus is not None else []))

    def plan(self,text=None):
        p=compile_plan(text or source(['1,2,3'],filename='out.csv',name='_null_'))
        self.assertFalse(p.blocked,[vars(t) for t in p.tickets]);return p.to_dict()

    def refuses(self,text):
        parsed=compile_plan(text)
        if not parsed.blocked:
            with self.assertRaises(ValueError):run_plan(parsed.to_dict())

    def test_original_whole_source_hand_R_emitted_and_schedules(self):
        assert_original(self.original,original_expected(),self.witnesses[0])

    def test_unchanged_csv_whole_source_hand_R_emitted_and_CLI(self):
        self.assertIsNotNone(self.corpus,'run with the sibling corpus path configured')
        assert_original(self.corpus,corpus_expected(),self.witnesses[1],corpus=True)
        cli_check(self.corpus,corpus_expected())

    def test_file_before_every_input_attempt_and_terminal_EOF(self):
        info=trace_accounting(self.corpus)[0]
        self.assertEqual((info['reads'],info['attempts'],info['opens'],info['writes']),(4,5,5,5))
        self.assertEqual(execute(self.corpus)['exports']['output.csv'].count('\n'),5)

    def test_empty_open_file_and_no_successful_header_are_distinct(self):
        for records,firstobs in (([],1),(['HEADER'],2),(['1,2'],1),(['HEADER'],10001)):
            text=source(records,filename='empty.csv',header=True,firstobs=firstobs,name='_null_')
            self.assertEqual(execute(text),{'datasets':{},'log':[],'exports':{'empty.csv':''}})
            self.assertEqual(export_manifest(execute(text)['exports'])['empty.csv']['records'],0)
            self.assertEqual(trace_accounting(text)[0]['attempts'],1)

    def test_partial_EOF_preserves_prior_records_without_partial_or_extra_header(self):
        text=source(['1,2,3','4,5'],filename='partial.csv',header=True,name='_null_')
        self.assertEqual(execute(text)['exports'],{'partial.csv':'HEADER\n1,2,3,6\n'})
        self.assertEqual(trace_accounting(text)[0]['opens'],2)

    def test_opaque_skipped_header_and_discarded_tail_are_not_code(self):
        for records,firstobs in ((['1,'+'('*33],1),(['('*33,'1'],2),(['1,BAD'],1)):
            text=source(records,width=1,filename='opaque.csv',firstobs=firstobs,name='_null_')
            result=execute(text);answer,=witnesses([text]);self.assertEqual(answer[0],result)
            self.assertEqual(result['exports']['opaque.csv'],'1,1\n')

    def test_consumed_invalid_and_incomplete_invalid_refuse_atomically(self):
        for records in (['1,BAD'],['1,2,BAD'],['1,2,3','4,BAD'],['1, ,3']):
            self.refuses(source(records,filename='bad.csv',header=True,name='_null_'))

    def test_range_grammar_full_expansion_overlap_and_ASCII(self):
        self.assertEqual(parse_terms('Z62 - Z64 s'),(['z62-z64','s'],['z62','z63','z64','s']))
        self.assertEqual(expand_terms(['x1-x64']),['x'+str(i) for i in range(1,65)])
        for terms in (['x0-x1'],['x1-x65'],['x01-x02'],['x2-x1'],['x1-y2'],['x1-x3','x2'],['x1--x2'],['x1:'],['K1-K2'],['x1-x64','y']):
            with self.assertRaises(ValueError):expand_terms(terms)
        with self.assertRaises(ValueError):parse_terms('K1-K2')

    def test_integer_rendering_log_trailing_blank_and_csv_separator_are_separate(self):
        body='x1=1;x2=.;s=sum(of x1-x2);put x1-x2 s;'
        self.assertEqual(execute(source(None,body=body))['log'],['1 . 1 '])
        self.assertEqual(execute(source(None,filename='Out.CSV',body=body,name='_null_'))['exports'],{'Out.CSV':'1,.,1\n'})

    def test_all_missing_sum_and_ordered_intermediate_bounds(self):
        text=source(['.,.,.'],filename='missing.csv',name='_null_')
        self.assertEqual(execute(text)['exports']['missing.csv'],'.,.,.,.\n')
        self.refuses(source(None,body='x1=2147483647;x2=1;x3=-1;s=sum(of x1-x3);'))
        self.refuses(source(None,body='x1=0.1;x2=0.2;s=sum(of x1-x2);'))

    def test_retained_import_overwrite_scratch_reset_and_earlier_snapshots(self):
        text=source(['1,2,3','.,4,5'],prefix='retain x1 9;',filename='state.csv',body='if _n_=1 then scratch=.;before=scratch;scratch=x1;s=sum(of x1-x3);put x1-x3 s;output;x1=99;output;')
        result=execute(text);rows=result['datasets']['d']['rows']
        self.assertEqual([r['x1'] for r in rows],[1.,99.,None,99.])
        self.assertEqual([r['before'] for r in rows],[None]*4)
        self.assertEqual(result['exports']['state.csv'],'1,2,3,6\n.,4,5,9\n')

    def test_skipped_explicit_output_suppresses_implicit_rows_and_validates_body(self):
        text=source(['1,2,3'],filename='empty-table.csv',body='if 0 then output;total=sum(of x1-x3);put x1-x3 total;')
        result=execute(text);self.assertEqual(result['datasets']['d']['rows'],[])
        self.assertEqual(result['exports']['empty-table.csv'],'1,2,3,6\n')
        self.refuses(text.replace('output;','x1=sqrt(1);'))

    def test_static_domains_are_checked_on_dead_and_empty_paths(self):
        for expr in ('2147483647+1','(2147483647+1)*0','1/3','1/(2-2)'):
            self.refuses(source(None,body='x1=1;x2=2;if 0 then z='+expr+';s=sum(of x1-x2);'))
            self.refuses(source([],filename='empty.csv',body='z='+expr+';total=sum(of x1-x3);'))

    def test_keyword_named_scalar_targets_do_not_become_statements(self):
        for name in ('input','infile','file','keep','drop','put','output','retain'):
            text=source(None,body=name+'=1;x1=2;x2=3;s=sum(of x1-x2);')
            self.assertEqual(execute(text)['datasets']['d']['rows'][0][name],1)

    def test_source_refuses_other_numeric_control_array_and_SQL_domains(self):
        for body in ('array a{1} x1;','do i=1 to 2;put x1;end;','if 0 then x1=sin(1);','set raw;','put x1-x3 8.;','x1=1**2;','do;put x1;end;'):
            self.refuses(source(['1,2,3'],filename='out.csv',body=body))
        self.assertTrue(cpp_translate(source(['1,2,3'],filename='out.csv',name='_null_')).blocked)

    def test_destination_basename_case_devices_and_program_collision(self):
        self.assertEqual(destination('Output.CSV'),'Output.CSV')
        for name in ('../x.csv','/tmp/x.csv','a/b.csv','a\\b.csv','a.csv:stream','.x.csv','a space.csv','CON.csv','lpt9.csv','result.json','exports','x'*61+'.csv'):
            with self.assertRaises(ValueError):destination(name)
        self.refuses(source(['1,2,3'],filename='one.csv')+source(['4,5,6'],filename='two.csv'))

    def test_file_is_unconditional_prefix_and_does_not_leak_to_log(self):
        self.refuses('data _null_;if 0;file "bad.csv" dlm=\',\';put "x";run;')
        self.refuses('data _null_;x=1;file "bad.csv" dlm=\',\';put x;run;')
        self.refuses('data _null_;if 1 then file "bad.csv" dlm=\',\';put "x";run;')
        self.assertEqual(execute(source(['1,2,3'],filename='one.csv',name='_null_'))['log'],[])

    def test_exact_step_marker_source_lines_and_metadata_on_empty_input(self):
        original=self.plan(source([],filename='empty.csv'))
        mutations=[lambda p:p['steps'][0].update(extra='ignored'),lambda p:p['steps'][0].update(lengths={'unused':8}),
                   lambda p:p['steps'][0].update(display_names={'unused':'unused'}),lambda p:p['steps'][0].update(line=True),
                   lambda p:p['steps'][0]['operations'][0]['args'].update(name='binary64-pipeline-v1')]
        for mutate in mutations:
            p=deepcopy(original);mutate(p)
            with self.assertRaises(ValueError):run_plan(p)
        for version in (True,2.0,'2',None):
            p=deepcopy(original);p['version']=version
            with self.assertRaises(ValueError):run_plan(p)

    def test_new_operations_cannot_hide_in_old_profiles_or_dead_legacy_branches(self):
        original=self.plan(source([],filename='empty.csv'))
        for kind in ('data','control_data','sql_create'):
            p=deepcopy(original);p['steps'][0]['kind']=kind
            with self.assertRaises(ValueError):run_plan(p)
        p=compile_plan('data d;x=1;run;').to_dict();p['steps'][0]['operations'].append({'kind':'if','line':1,'args':{'condition':{'op':'truth','left':{'kind':'number','value':0}},'operation':deepcopy(original['steps'][0]['operations'][0])}})
        with self.assertRaises(ValueError):run_plan(p)

    def test_malformed_predicate_types_fail_controlled_not_hash_errors(self):
        original=self.plan(source(['1,2,3'],filename='x.csv',body='if 0 then put x1-x3;'))
        for malformed in ([],{},True,None,3):
            p=deepcopy(original);op=next(o for o in p['steps'][0]['operations'] if o['kind']=='if');op['args']['condition']['op']=malformed
            with self.assertRaises(ValueError):run_plan(p)

    def test_sum_list_is_a_complete_assignment_value_only(self):
        for body in ('s=sum(of x1-x2)+1;','s=(sum(of x1-x2));','if sum(of x1-x2) then put x1-x2;','s+sum(of x1-x2);'):
            self.refuses(source(None,body='x1=1;x2=2;'+body))
        p=self.plan(source(None,body='x1=1;x2=2;s=sum(of x1-x2);'))
        op=p['steps'][0]['operations'][-1];summed=deepcopy(op['args']['value'])
        op['args']['value']={'kind':'arithmetic','op':'+','left':summed,'right':{'kind':'number','value':1.}}
        with self.assertRaises(ValueError):run_plan(p)
        op['args']['value']=summed;op['kind']='sum_statement';p['steps'][0]['retained']['s']={'kind':'number','value':0.}
        with self.assertRaises(ValueError):run_plan(p)

    def test_unknown_or_extra_operations_and_list_metadata_validate_statically(self):
        original=self.plan(source([],filename='empty.csv'))
        for mutate in (lambda o:o['args'].update(extra=1),lambda o:o['args'].update(names=['x1','x2','missing'])):
            p=deepcopy(original);op=next(o for o in p['steps'][0]['operations'] if o['kind']=='put_named_list');mutate(op)
            with self.assertRaises(ValueError):run_plan(p)
        p=deepcopy(original);p['steps'][0]['operations'].append({'kind':'future','line':1,'args':{}})
        with self.assertRaises(ValueError):run_plan(p)

    def test_resource_container_cycle_expression_and_opaque_source_bounds(self):
        p=self.plan();expr={'kind':'number','value':1.}
        for _ in range(33):expr={'kind':'arithmetic','op':'+','left':expr,'right':{'kind':'number','value':0.}}
        p['steps'][0]['operations'].append({'kind':'assign','line':1,'args':{'name':'deep','value':expr}})
        with self.assertRaises(ValueError):run_plan(p)
        p=self.plan();p['steps'][0]['operations'].append(p['steps'][0]['operations'])
        with self.assertRaises(ValueError):run_plan(p)
        self.refuses(source(['1,2,3'],filename='x.csv',body='x1='+'round('*1000+'1'+',1)'*1000+';'))

    def test_operation_column_and_record_width_caps_on_empty_paths(self):
        positive='data _null_;file "cap.csv" dlm=\',\';'+'put "H";'*1023+'run;'
        self.assertEqual(execute(positive)['exports']['cap.csv'].count('\n'),1023)
        self.refuses(positive.replace('run;','put "H";run;'))
        sixtyfour=source(None,body=''.join(f'x{i}=1;' for i in range(1,65))+'x1=sum(of x1-x64);')
        self.assertEqual(len(execute(sixtyfour)['datasets']['d']['schema']),64)
        p=self.plan(source([],filename='empty.csv'));leaf={'kind':'declare','line':1,'args':{'name':'x1','spec':'number'}}
        p['steps'][0]['operations'].extend(deepcopy(leaf) for _ in range(1025))
        with self.assertRaises(ValueError):run_plan(p)
        text=source(None,body=''.join(f'x{i}=1;' for i in range(1,66))+'s=sum(of x1-x2);')
        self.refuses(text)
        text=source(None,body=''.join(f'x{i}=1;' for i in range(1,34))+'put x1-x33;')
        self.refuses(text)

    def test_record_count_and_step_event_caps(self):
        p=self.plan(source(['1,2,3'],filename='records.csv',name='_null_',body='put "H";'))
        op=next(o for o in p['steps'][0]['operations'] if o['kind']=='exchange_input');op['args']['records']=['1,2,3']*10000
        p['steps'][0]['operations'].append({'kind':'if','line':1,'args':{'condition':{'op':'=','left':{'kind':'automatic','value':'_n_'},'right':{'kind':'number','value':1.}},'operation':{'kind':'put_literal','line':1,'args':{'literals':['"EXTRA"']}}}})
        with self.assertRaises(ValueError):run_plan(p)
        text=source(['1']*10000,width=1,filename='events.csv',name='_null_',body='x1=1;'*98)
        with self.assertRaisesRegex(ValueError,'1000000'):execute(text)

    def test_caller_catalog_normalization_and_plan_nonmutation_preserve_unused_values(self):
        catalog={'Unused':{'schema':{'N':{'type':'number','length':8,'label':'fraction'},'Tag':'number','C':{'type':'character','length':2}},
                           'rows':[{'N':2147483647.5,'Tag':{'missing':'A'},'C':'é'}],'encoding':'latin-1','label':'transport'}}
        saved=deepcopy(catalog);p=self.plan();before=deepcopy(p);result=run_plan(p,catalog)
        self.assertEqual(catalog,saved);self.assertEqual(p,before)
        self.assertEqual(result['datasets']['unused']['rows'][0]['n'],2147483647.5)
        self.assertEqual(result['datasets']['unused']['rows'][0]['tag'],{'missing':'A'})
        scope={'inputs':deepcopy(catalog)};exec(translate(source(['1,2,3'],filename='out.csv',name='_null_')).code,scope)
        self.assertEqual(scope['result'],result)

    def test_runtime_and_emitted_buffers_perform_no_host_file_io(self):
        p=self.plan()
        with mock.patch.object(Path,'open',side_effect=AssertionError('host output is forbidden in runtime')):
            self.assertEqual(run_plan(p)['exports'],{'out.csv':'1,2,3,6\n'})

    def test_expected_manifest_duplicate_keys_types_and_complete_name_set(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'expected.json'
            for text in ('{"x.csv":"a","x.csv":"b"}','[]','null','{"x.csv":1}','{"x.csv":true}','{"x.csv":"a","y.csv":"b"}','{"../x.csv":"a"}'):
                path.write_text(text)
                with self.assertRaises(ValueError):read_expected_exports(path)
            path.write_text('{"x.csv":"a"}');self.assertEqual(read_expected_exports(path)[0],{'x.csv':'a'})

    def test_export_buffers_reject_nonASCII_controls_missing_newline_and_oversize(self):
        for text in ('x','x\r\n','é\n','x\v\n','x\t\n','x'*65+'\n','x\n'*10001):
            with self.assertRaises(ValueError):validate_exports({'x.csv':text})
        self.assertEqual(validate_exports({'x.csv':''}),{'x.csv':''})

    def test_statement_catalogue_routes_new_forms_without_relabeling_old_input(self):
        from saschi.rules import route_statement
        for text,expected in [('file "out.csv" dlm=\',\';',('csv-export','DS-063')),
                              ('s=sum(of x1-x3)',('numeric-ranges','DS-062')),
                              ('put x1-x3 s',('numeric-ranges','DS-062')),
                              ('input x1-x3',('input-ranges','DS-059'))]:
            self.assertEqual(route_statement(text),expected)
        self.assertNotEqual(route_statement('file=1')[0],'csv-export')

    def test_malformed_unreadable_and_wrong_UTF8_expectations_have_no_exports(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);path=folder/'job.sas';path.write_text(source(['1,2,3'],filename='out.csv',name='_null_'))
            for index,contents in enumerate(('{"out.csv":"a","out.csv":"b"}','{"out.csv":7}','{"out.csv":"é"}',None)):
                expected=folder/f'expected{index}.json'
                if contents is not None:expected.write_text(contents)
                out=folder/f'job{index}'
                with contextlib.redirect_stdout(io.StringIO()):code=cli_main(['run',str(path),'--expect-exports',str(expected),'--output',str(out)])
                self.assertEqual(code,1);receipt=json.loads((out/'receipt.json').read_text())
                self.assertFalse(receipt['accepted']);self.assertEqual(receipt['export_comparison'],'failed')
                self.assertFalse((out/'exports').exists());self.assertTrue((out/'observed.json').exists())

    def test_failed_export_comparison_never_publishes_files(self):
        text=source(['1,2,3'],filename='out.csv',name='_null_');expected=execute(text)
        for wrong in ({'other.csv':'1,2,3,6\n'},{'out.csv':'1,2,3,6'},{'out.csv':'1,2,3,6\n\n'}):cli_check(text,expected,wrong=wrong)

    def test_late_runtime_failure_discards_exports_and_log(self):
        text='data _null_;put "before";run;'+source(['1,2,3','4,0,6'],filename='late.csv',name='_null_',body='put x1-x3;z=x1/x2;')
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'job.sas';p.write_text(text);out=Path(td)/'job'
            stdout=io.StringIO()
            with contextlib.redirect_stdout(stdout):code=cli_main(['run',str(p),'--output',str(out)])
            self.assertEqual(code,1);self.assertNotIn('before',stdout.getvalue())
            self.assertEqual(set(f.name for f in out.iterdir()),{'plan.json','receipt.json'})

    def test_later_independent_step_failure_discards_whole_export(self):
        text=source(['1,2,3'],filename='first.csv',name='_null_')+'data _null_;d=0;x=1/d;run;'
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'job.sas';p.write_text(text);job=build_job(text)
            self.assertFalse(job.receipt['accepted']);self.assertIsNone(job.result)
            with contextlib.redirect_stdout(io.StringIO()):code=cli_main(['run',str(p),'--output',str(Path(td)/'job')])
            self.assertEqual(code,1);self.assertFalse((Path(td)/'job/exports').exists())

    def test_physical_open_partial_write_and_commit_failures_leave_no_job(self):
        for fault in ('open','partial','rename'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as td:
                folder=Path(td);source_path=folder/'job.sas';source_path.write_text(source(['1,2,3'],filename='out.csv',name='_null_'));out=folder/'job'
                real_open,real_rename=Path.open,Path.rename
                def opened(path,*args,**kwargs):
                    if path.name=='out.csv' and args and args[0]=='xb':
                        if fault=='open':raise OSError('injected export open failure')
                        if fault=='partial':
                            actual=real_open(path,*args,**kwargs)
                            class Partial:
                                def __enter__(self):return self
                                def write(self,data):actual.write(data[:2]);raise OSError('injected partial export write')
                                def __exit__(self,*ignored):actual.close()
                            return Partial()
                    return real_open(path,*args,**kwargs)
                def renamed(path,target):
                    if fault=='rename':raise OSError('injected commit failure')
                    return real_rename(path,target)
                with mock.patch.object(Path,'open',opened),mock.patch.object(Path,'rename',renamed),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(cli_main(['run',str(source_path),'--output',str(out)]),1)
                self.assertFalse(out.exists());self.assertEqual(list(folder.glob('.saschi-*')),[])

    def test_legacy_job_result_and_receipt_export_fields_remain_absent(self):
        job=build_job('data d;x=1;run;',None,None,'python')
        self.assertTrue(job.receipt['accepted']);self.assertEqual(set(job.result),{'datasets','log'})
        self.assertFalse(any('export' in key for key in job.receipt))
        self.assertEqual(set(execute(source(None,body='x1=1;x2=2;s=sum(of x1-x2);'))),{'datasets','log'})


if __name__=='__main__':unittest.main()
