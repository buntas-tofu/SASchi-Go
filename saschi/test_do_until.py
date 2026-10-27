"""DS-035 post-test loop evidence for maintainer review, no live SAS."""
import contextlib
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from examples.verify_do_until import program_records
from sas_semantics import sas_do_until
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .rules import route_statement
from .runtime import run_plan
from .test_do_counted import execute, job_with_inputs
from .test_parser import ROKU_CORPUS
from .test_sum_statement import raw

SOURCE_SHA = 'dd59991a99fdd5b1fa9f9c039d08464bcbe58655533ab6b8b2eff567e410bf53'
STDOUT_SHA = '287b9d97d3936f9e3d5bb677de45fa8e0c1f24649d8b971a6195572306c2f257'
RESULT_SHA = 'dd5ddfbc7922f0867841552e18f29bdb391b9725e43704d29ef1907e84d67dc5'


class DoUntilTests(unittest.TestCase):
    def test_routing_and_initially_true_body(self):
        self.assertEqual(route_statement('DO UNTIL(1)'),('do-until','DS-035'))
        table=execute('data d; n=0; do until(n>=0); n+1; end; run;')[0]['datasets']['d']
        self.assertEqual(table['rows'],[{'n':1.}])
        self.assertIn(('do-until','DS-035',1),compile_plan('data d; do until(1); end; run;').matched)

    def test_helper_body_then_test_schedule(self):
        events=[]
        def body(): events.append('body')
        def stop(): events.append('test'); return len(events)>=6
        self.assertEqual(sas_do_until(body,stop),3)
        self.assertEqual(events,['body','test']*3)

    def test_exact_limit_passes_next_iteration_refuses(self):
        rows=execute('data d; do until(n=10000); n+1; end; run;')[0]['datasets']['d']['rows']
        self.assertEqual(rows,[{'n':10000.}])
        job=build_job('data d; do until(n=10001); n+1; end; run;')
        self.assertEqual(job.code,1); self.assertIn('10000',job.receipt['error']); self.assertIsNone(job.result)

    def test_outer_data_iteration_and_retention(self):
        rows=execute('data d; set raw; i=0; do until(i>=x); i=i+1; total+1; seen=_n_; end; run;',raw([0,2,3]))[0]['datasets']['d']['rows']
        self.assertEqual([(r['i'],r['total'],r['seen']) for r in rows],[(1,1,1),(2,3,2),(3,6,3)])

    def test_explicit_output_snapshots_and_schema_discovery(self):
        source='data d; n=0; do until(n=3); n+1; if n=2 then flag=9; output; end; after=1; run;'
        table=execute(source)[0]['datasets']['d']
        self.assertEqual(list(table['schema']),['n','flag','after'])
        self.assertEqual(table['rows'],[{'n':1.,'flag':None,'after':None},
                                       {'n':2.,'flag':9.,'after':None},{'n':3.,'flag':9.,'after':None}])

    def test_unselected_output_suppresses_implicit_output(self):
        table=execute('data d; do until(n=2); n+1; if 0 then output; end; run;')[0]['datasets']['d']
        self.assertEqual(table,{'schema':{'n':'number'},'rows':[]})

    def test_empty_set_does_not_invoke_body(self):
        table=execute('data d; set raw; do until(0); n+1; output; end; run;',raw([]))[0]['datasets']['d']
        self.assertEqual(table,{'schema':{'x':'number','n':'number'},'rows':[]})

    def test_static_condition_descriptors_and_literals(self):
        job=job_with_inputs('data d; set raw; do until(x); n+1; end; run;',raw([],{'type':'character','length':1}))
        self.assertEqual(job.code,1); self.assertIsNone(job.result)
        for test in ('"1"','.A','1e309','weekday(.)'):
            job=job_with_inputs('data d; set raw; do until('+test+'); end; run;',raw([]))
            self.assertNotEqual(job.code,0); self.assertIsNone(job.result)

    def test_lag_dif_scheduling_stays_deferred(self):
        for body,test in (('v=lag(n);','1'),('if 0 then v=dif(n);','1'),('n+1;','lag(n)=1')):
            job=build_job('data d; n=0; do until('+test+'); '+body+' end; run;')
            self.assertEqual(job.code,2); self.assertIsNone(job.result)

    def test_nested_and_combined_controls_stay_refused(self):
        for source in ('do until(1); do until(1); end; end;',
                       'do i=1 to 2; do until(1); end; end;',
                       'do until(1); do i=1 to 2; end; end;',
                       'do until(1) while(1); end;'):
            self.assertTrue(compile_plan('data d; '+source+' run;').blocked)
        # Preserve the old standalone WHILE source as a bounded runtime refusal.
        job=build_job('data d; do while(1); end; run;')
        self.assertEqual(job.code,1); self.assertIsNone(job.result)
        self.assertIn('10000',job.receipt['error'])

    def test_body_declarations_control_and_null_output_refuse(self):
        for body in ('length c $2;','retain n 0;','set raw;','where 1;',
                     'leave;','continue;','if 1;','put _all_;','output other;'):
            self.assertTrue(compile_plan('data d; do until(1); '+body+' end; run;').blocked)
        self.assertTrue(compile_plan('data _null_; do until(1); if 0 then output; end; run;').blocked)

    def test_numeric_missing_predicates_and_else_actions(self):
        table=execute('data d; n=0; do until(missing_value=.); if n=0 then n+1; else n+2; end; run;')[0]['datasets']['d']
        self.assertEqual(table['rows'],[{'n':1.,'missing_value':None}])
        job=build_job('data d; do until(.); end; run;')
        self.assertEqual(job.code,1); self.assertIsNone(job.result)

    def test_dynamic_tagged_predicate_refuses(self):
        job=job_with_inputs('data d; set raw; do until(x=1); end; run;',raw([{'missing':'A'}]))
        self.assertEqual(job.code,1); self.assertIsNone(job.result)

    def test_forged_limit_shape_and_predicate_refuse(self):
        original=compile_plan('data d; do until(1); end; run;').to_dict()
        for update in ({'limit':1000000},{'body':{}},{'condition':{'op':'unknown','left':{}}},
                       {'condition':{'op':'truth','left':{'kind':'number','value':True}}}):
            plan=deepcopy(original); plan['steps'][0]['operations'][0]['args'].update(update)
            with self.assertRaises(ValueError): run_plan(plan,allow_partial=True)

    def test_forged_hidden_body_and_lag_refuse(self):
        original=compile_plan('data d; do until(1); if 0 then n+1; end; run;').to_dict()
        for child in ({'kind':'do_until','line':1,'args':{'condition':{'op':'truth','left':{'kind':'number','value':1}},'body':[]}},
                      {'kind':'declare','line':1,'args':{'name':'x','spec':'number'}},
                      {'kind':'assign','line':1,'args':{'name':'n','value':{'kind':'call','name':'lag','args':[{'kind':'number','value':1}]}}}):
            plan=deepcopy(original); plan['steps'][0]['operations'][0]['args']['body'][0]['args']['operation']=child
            with self.assertRaises(ValueError): run_plan(plan,allow_partial=True)

    def test_helper_callback_contract(self):
        for body,stop in ((None,lambda:True),(lambda:None,None),(lambda:None,lambda:1)):
            with self.assertRaises(ValueError): sas_do_until(body,stop)

    def test_budget_failure_emits_no_prior_or_partial_records(self):
        source='data prior; put "earlier"; run; data d; do until(0); n+1; output; end; run;'
        translated=translate(source); self.assertFalse(translated.blocked)
        namespace={}; printed=io.StringIO()
        with contextlib.redirect_stdout(printed),self.assertRaisesRegex(ValueError,'10000'):
            exec(translated.code,namespace)
        self.assertEqual(printed.getvalue(),''); self.assertNotIn('result',namespace)
        job=build_job(source); self.assertEqual(job.code,1); self.assertIsNone(job.result)

    def test_overflow_and_cpp_refuse_atomically(self):
        job=build_job('data d; n=1e308; do until(0); n+1e308; end; run;')
        self.assertEqual(job.code,1); self.assertIsNone(job.result)
        job=build_job('data _null_; do until(1); n+1; end; run;',target='cpp')
        self.assertEqual(job.code,2); self.assertIsNone(job.result)

    def test_comparator_controls_preserve_observed_result(self):
        source='data d; do until(n=2); n+1; m=n; output; end; run;'
        actual=execute(source)[0]['datasets']['d']; changes=[]
        t=deepcopy(actual); t['rows'].reverse(); changes.append(t)
        t=deepcopy(actual); t['schema']={'m':'number','n':'number'}; changes.append(t)
        t=deepcopy(actual); t['rows'][0]['m']=9; changes.append(t)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'expected.json'; path.write_text(json.dumps({'d':actual}))
            self.assertTrue(build_job(source,expect=path).receipt['accepted'])
            for changed in changes:
                path.write_text(json.dumps({'d':changed})); job=build_job(source,expect=path)
                self.assertEqual(job.code,1); self.assertEqual(job.receipt['comparison'],'failed')
                self.assertEqual(job.result['datasets']['d'],actual)

    def test_full_unmodified_external_program(self):
        path=ROKU_CORPUS/'loops_do_while.sas'
        if not path.is_file(): self.skipTest('Roku corpus not present')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),SOURCE_SHA)
        result,printed=execute(path.read_text())
        expected={'datasets':{},'log':[str(n)+' ' for n in range(1,7)]}
        self.assertEqual(result,expected)
        self.assertEqual(hashlib.sha256(printed.encode()).hexdigest(),STDOUT_SHA)
        self.assertEqual(hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest(),RESULT_SHA)
        records,final,count=program_records(path)
        self.assertEqual((records,final,count),(expected['log'],6,6))
        job=build_job(path.read_text()); self.assertEqual(job.code,0)
        self.assertTrue(job.receipt['accepted']); self.assertEqual(job.receipt['source_sha256'],SOURCE_SHA)
        self.assertEqual(job.result,expected)
        print('VERIFIED corpus: loops_do_while.sas; full source/stdout/result pins and independent R, no live SAS')


if __name__=='__main__': unittest.main()
