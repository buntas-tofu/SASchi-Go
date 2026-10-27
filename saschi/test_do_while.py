"""DS-038 pre-test loop and whole-program evidence, repository/base R only."""
import contextlib
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from examples.verify_do_while import program_records
from sas_semantics import sas_do_while
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .rules import route_statement
from .runtime import run_plan
from .test_do_counted import execute,job_with_inputs
from .test_parser import ROKU_CORPUS
from .test_sum_statement import raw

SOURCE_SHA='688c60c70435a89c6f05badf4623345311e5bcad05c9b03fb2cd3599c3e42787'
STDOUT_SHA='bdabf303c8c119f7a7c8f3cb2f45195b7f0365f84bb3fcef3bc94f34550369b0'
RESULT_SHA='fba80f4e789a2bc76fb16c38ec05b43d76f8d58b94c66564a6a059dd85e4f463'
VALUES=[1024,512,256,128,64,32,16,8,4,2,1]


class DoWhileTests(unittest.TestCase):
    def test_routing_and_initially_false_zero_trip(self):
        self.assertEqual(route_statement('DO WHILE(0)'),('do-while','DS-038'))
        p=compile_plan('data d; do while(0); x=1; end; run;')
        self.assertFalse(p.blocked,p.tickets);self.assertIn(('do-while','DS-038',1),p.matched)
        self.assertEqual(run_plan(p.to_dict())['datasets']['d'],{'schema':{'x':'number'},'rows':[{'x':None}]})

    def test_helper_test_before_body_and_final_test(self):
        events=[];state=[0]
        def body():events.append('body');state[0]+=1
        def test():events.append('test');return state[0]<2
        self.assertEqual(sas_do_while(body,test),2)
        self.assertEqual(events,['test','body','test','body','test'])

    def test_zero_false_and_missing_numeric_truth(self):
        for test in ('0','.','1>2'):
            result,printed=execute('data d; do while('+test+'); x=1; put "bad"; end; run;')
            self.assertEqual(printed,'');self.assertEqual(result['datasets']['d']['rows'],[{'x':None}])

    def test_exact_limit_success_and_next_body_refusal(self):
        row=execute('data d; do while(n<10000); n+1; end; run;')[0]['datasets']['d']['rows'][0]
        self.assertEqual(row,{'n':10000.})
        job=build_job('data d; do while(n<10001); n+1; end; run;')
        self.assertEqual(job.code,1);self.assertIn('10000',job.receipt['error']);self.assertIsNone(job.result)

    def test_outer_data_rows_n_and_retained_state(self):
        rows=execute('data d; set raw; i=0; do while(i<x); i=i+1; total+1; seen=_n_; end; run;',raw([0,2,3]))[0]['datasets']['d']['rows']
        self.assertEqual([(r['i'],r['total'],r['seen']) for r in rows],[(0,0,None),(2,2,2),(3,5,3)])

    def test_explicit_output_snapshots_and_schema_discovery(self):
        table=execute('data d; do while(n<3); n+1; if n=2 then flag=9; output; end; after=1; run;')[0]['datasets']['d']
        self.assertEqual(list(table['schema']),['n','flag','after'])
        self.assertEqual(table['rows'],[{'n':1.,'flag':None,'after':None},
                                      {'n':2.,'flag':9.,'after':None},{'n':3.,'flag':9.,'after':None}])

    def test_unselected_or_zero_trip_output_suppresses_implicit(self):
        for body in ('do while(0); x=1; output; end;', 'do while(n<2); n+1; if 0 then output; end;'):
            table=execute('data d; '+body+' run;')[0]['datasets']['d']
            self.assertEqual(table['rows'],[]);self.assertTrue(table['schema'])

    def test_empty_and_filtered_set_do_not_test_or_execute(self):
        for values,where in (([],''),([0],'where 0;')):
            table=execute('data d; set raw; '+where+' do while(1/x); n+1; end; run;',raw(values))[0]['datasets']['d']
            self.assertEqual(table,{'schema':{'x':'number','n':'number'},'rows':[]})

    def test_static_body_and_predicate_validation_on_zero_trip(self):
        for body in ('y=1/0;','y=int(1.9999999999995);'):
            job=build_job('data d; do while(0); '+body+' end; run;')
            self.assertEqual(job.code,1);self.assertIsNone(job.result)
        job=job_with_inputs('data d; set raw; do while(x); end; run;',raw([],{'type':'character','length':1}))
        self.assertEqual(job.code,1);self.assertIsNone(job.result)

    def test_lag_scheduling_is_deferred_even_on_zero_trip(self):
        for body,test in (('y=lag(n);','0'),('if 0 then y=dif(n);','0'),('n+1;','lag(n)')):
            job=build_job('data d; do while('+test+'); '+body+' end; run;')
            self.assertEqual(job.code,2);self.assertIsNone(job.result)

    def test_nested_and_combined_controls_remain_refused(self):
        for source in ('do while(1); do while(0); end; end;',
                       'do while(1); do until(1); end; end;',
                       'do i=1 to 2; do while(0); end; end;',
                       'do while(1) until(0); end;'):
            self.assertTrue(compile_plan('data d; '+source+' run;').blocked)

    def test_body_declarations_control_and_null_output_refuse(self):
        for body in ('length c $2;','retain n 0;','set raw;','where 1;','leave;','continue;','if 1;','put _all_;','output other;'):
            self.assertTrue(compile_plan('data d; do while(0); '+body+' end; run;').blocked)
        self.assertTrue(compile_plan('data _null_; do while(0); if 0 then output; end; run;').blocked)

    def test_numeric_composition_predicate_and_else_dispatch(self):
        row=execute('data d; do while(n/2<2); if n=0 then n+1; else n+3; end; half=int(n/2); run;')[0]['datasets']['d']['rows'][0]
        self.assertEqual(row,{'n':4.,'half':2.})

    def test_forged_budget_shape_predicate_and_hidden_body_refuse(self):
        original=compile_plan('data d; do while(0); end; run;').to_dict()
        for update in ({'limit':100000},{'body':{}},{'condition':{'op':'unknown','left':{}}},
                       {'condition':{'op':'truth','left':{'kind':'number','value':True}}},
                       {'body':[{'kind':'declare','line':1,'args':{'name':'n','spec':'number'}}]}):
            p=deepcopy(original);p['steps'][0]['operations'][0]['args'].update(update)
            with self.assertRaises(ValueError):run_plan(p,allow_partial=True)

    def test_helper_callback_contract(self):
        for body,test in ((None,lambda:False),(lambda:None,None),(lambda:None,lambda:1)):
            with self.assertRaises(ValueError):sas_do_while(body,test)

    def test_pretest_dynamic_error_prevents_body_and_prior_logs(self):
        source='data prior; put "earlier"; run; data d; n=0; do while(1/n); put "body"; end; run;'
        translated=translate(source);self.assertFalse(translated.blocked,translated.tickets)
        ns={};printed=io.StringIO()
        with contextlib.redirect_stdout(printed),self.assertRaises(ValueError):exec(translated.code,ns)
        self.assertEqual(printed.getvalue(),'');self.assertNotIn('result',ns)

    def test_budget_failure_publishes_no_partial_result(self):
        source='data prior; put "earlier"; run; data d; do while(1); n+1; output; end; run;'
        job=build_job(source);self.assertEqual(job.code,1);self.assertFalse(job.receipt['accepted']);self.assertIsNone(job.result)

    def test_step_run_reset_and_cpp_boundary(self):
        source='data d; do while(n<2); n+1; end; run; data e; do while(n<2); n+1; end; run;'
        a=execute(source)[0];self.assertEqual(a,execute(source)[0])
        self.assertEqual(a['datasets']['e']['rows'],[{'n':2.}])
        job=build_job('data _null_; do while(0); end; run;',target='cpp')
        self.assertEqual(job.code,2);self.assertIsNone(job.result)

    def test_comparator_controls_preserve_observed_results(self):
        source='data d; do while(n<2); n+1; m=n; output; end; run;'
        actual=execute(source)[0]['datasets']['d'];changes=[]
        t=deepcopy(actual);t['rows'].reverse();changes.append(t)
        t=deepcopy(actual);t['schema']={'m':'number','n':'number'};changes.append(t)
        t=deepcopy(actual);t['rows'][0]['m']=9.;changes.append(t)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'expected.json';p.write_text(json.dumps({'d':actual}))
            self.assertTrue(build_job(source,expect=p).receipt['accepted'])
            for changed in changes:
                p.write_text(json.dumps({'d':changed}));job=build_job(source,expect=p)
                self.assertEqual(job.code,1);self.assertEqual(job.receipt['comparison'],'failed');self.assertEqual(job.result['datasets']['d'],actual)

    def test_full_unmodified_external_program(self):
        p=ROKU_CORPUS/'loops_while.sas'
        if not p.is_file():self.skipTest('Roku corpus not present')
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),SOURCE_SHA)
        result,printed=execute(p.read_text());expected={'datasets':{},'log':[str(n)+' ' for n in VALUES]}
        self.assertEqual(result,expected)
        self.assertEqual(hashlib.sha256(printed.encode()).hexdigest(),STDOUT_SHA)
        self.assertEqual(hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest(),RESULT_SHA)
        self.assertEqual(program_records(p),(expected['log'],0,11))
        job=build_job(p.read_text());self.assertEqual(job.code,0);self.assertTrue(job.receipt['accepted'])
        self.assertEqual(job.receipt['source_sha256'],SOURCE_SHA);self.assertEqual(job.result,expected)
        print('VERIFIED corpus: loops_while.sas; full source/stdout/result pins and independent base R; no live SAS')


if __name__=='__main__':unittest.main()
