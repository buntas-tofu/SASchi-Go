"""DS-040 source scheduling and complete-program proofs, repository/base R."""
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

from examples.verify_do_over import program_records
from sas_semantics import sas_do_over
from .emit_cpp import translate as cpp
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .rules import route_statement
from .runtime import run_plan
from .test_do_counted import execute, job_with_inputs
from .test_parser import ROKU_CORPUS

SOURCE_SHA = 'f93ccdac3029a544483d86bb64d88d6b01529ccabec2b641c867659c544205ae'
STDOUT_SHA = '7454bf7421a233a47005ce1cd5cf8e777ea8f403570ff41bd6a575201f8705f7'
RESULT_SHA = '83130684235d5189fac7e94a7a69aaf9c4d1ca4be3f573c988d77f1b4b10f589'


class DoOverTests(unittest.TestCase):
    def table(self,body,catalog=None):
        return execute('data d; '+body+' run;',catalog)[0]['datasets']['d']

    def blocked(self,body):
        p=compile_plan('data d; '+body+' run;')
        self.assertTrue(p.blocked,body)
        self.assertTrue(translate('data d; '+body+' run;').blocked)

    def test_routing_and_declaration_marker(self):
        self.assertEqual(route_statement('DO OVER a'),('do-over','DS-040'))
        p=compile_plan('data d; array a x y; do over a; a=1; end; run;')
        self.assertFalse(p.blocked,p.tickets)
        self.assertEqual(p.steps[0].operations[0].args,{'name':'a','lower':1,'names':['x','y'],'mode':'implicit'})
        self.assertIn(('do-over','DS-040',1),p.matched)

    def test_old_plans_keep_shape_and_execution(self):
        for decl in ('array a x y','array a[*] x y','array a[2] x y'):
            p=compile_plan('data d; '+decl+'; a[1]=3; run;')
            self.assertFalse(p.blocked,p.tickets)
            self.assertEqual(p.steps[0].operations[0].args,{'name':'a','lower':1,'names':['x','y']})
            self.assertEqual(run_plan(p.to_dict())['datasets']['d']['rows'],[{'x':3.,'y':None}])

    def test_explicit_extents_are_not_implicit(self):
        for bounds in ('[2]','{*}','(2)','[0:1]'):
            self.blocked('array a'+bounds+' x y; do over a; a=1; end;')
        self.blocked('array a(i) x y; do over a; a=1; end;')

    def test_declared_order_and_alias_reads_writes(self):
        t=self.table('array a y x; x=2; y=5; n=1; do over a; before=a; a=a+3; x=x+1; after=a; output; n=n+1; end;')
        self.assertEqual(t['rows'],[
            {'y':8.,'x':3.,'n':1.,'before':5.,'after':8.},
            {'y':8.,'x':7.,'n':2.,'before':3.,'after':7.}])

    def test_overlapping_arrays_share_actual_variables(self):
        t=self.table('array a x y; array b y z; do over a; a=1; end; do over b; b=3; end; total=sum(of a[*]);')
        self.assertEqual(t['rows'],[{'x':1.,'y':3.,'z':3.,'total':4.}])

    def test_scratch_elements_and_current_reset_each_row(self):
        raw={'raw':{'schema':{'v':'number'},'rows':[{'v':2},{'v':7}]}}
        t=self.table('set raw; array a x y; do over a; prior=a; a=v; rownum=_n_; output; end;',raw)
        self.assertEqual([r['prior'] for r in t['rows']],[None]*4)
        self.assertEqual([(r['x'],r['y'],r['rownum']) for r in t['rows']],[(2,None,1),(2,2,1),(7,None,2),(7,7,2)])

    def test_plan_catalog_and_each_run_are_isolated(self):
        p=compile_plan('data d; set raw; array a x y; do over a; a=a+1; end; run;').to_dict()
        raw={'raw':{'schema':{'x':'number','y':'number'},'rows':[{'x':2,'y':3}]}}
        before=deepcopy((p,raw))
        self.assertEqual(run_plan(p,raw),run_plan(p,raw));self.assertEqual((p,raw),before)

    def test_each_step_requires_its_own_declaration(self):
        self.assertTrue(compile_plan('data d; array a x; do over a; a=1; end; run; data e; do over a; a=2; end; run;').blocked)
        result=execute('data d; array a x; do over a; a=1; end; run; data e; array a x; do over a; a=2; end; run;')[0]
        self.assertEqual(result['datasets']['d']['rows'],[{'x':1.}]);self.assertEqual(result['datasets']['e']['rows'],[{'x':2.}])

    def test_implicit_output_once_after_all_elements(self):
        t=self.table('array a x1-x3; n=1; do over a; a=n; n=n+1; end;')
        self.assertEqual(t['rows'],[{'x1':1.,'x2':2.,'x3':3.,'n':4.}])
        self.assertNotIn('_i_',t['schema']);self.assertNotIn('a',t['schema'])

    def test_multiple_outputs_capture_each_point(self):
        t=self.table('array a x y; do over a; a=2; output; a=3; output; end;')
        self.assertEqual(t['rows'],[{'x':2.,'y':None},{'x':3.,'y':None},{'x':3.,'y':2.},{'x':3.,'y':3.}])

    def test_skipped_output_suppresses_implicit(self):
        t=self.table('array a x y; do over a; a=1; if 0 then output; end;')
        self.assertEqual(t,{'schema':{'x':'number','y':'number'},'rows':[]})

    def test_future_and_skipped_descriptors_are_discovered(self):
        t=self.table('array a x y; do over a; if 0 then never=a; output; end; later=3;')
        self.assertEqual(list(t['schema']),['x','y','never','later'])
        self.assertEqual(t['rows'],[dict.fromkeys(t['schema'])]*2)

    def test_empty_and_filtered_sources_keep_schema(self):
        for rows,where in (([],''),([{'v':1}],'where 0;')):
            raw={'raw':{'schema':{'v':'number'},'rows':rows}}
            t=self.table('set raw; '+where+' array a x y; do over a; a=v; if 0 then future=a; output; end;',raw)
            self.assertEqual(t,{'schema':dict.fromkeys(['v','x','y','future'],'number'),'rows':[]})

    def test_inherited_numeric_metadata_survives(self):
        spec={'type':'number','length':8,'label':'score','format':'best12.'}
        raw={'raw':{'schema':{'x':spec},'rows':[{'x':4}]}}
        t=self.table('array a x; set raw; do over a; a=a+1; end;',raw)
        self.assertEqual(t,{'schema':{'x':spec},'rows':[{'x':5.}]})

    def test_character_descriptor_fails_even_empty(self):
        raw={'raw':{'schema':{'x':{'type':'character','length':1}},'rows':[]}}
        job=job_with_inputs('data d; set raw; array a x; do over a; if 0 then a=1; end; run;',raw)
        self.assertEqual(job.code,1);self.assertIsNone(job.result)

    def test_current_predicates_and_else_branches(self):
        t=self.table('array a x y z; x=2; y=0; do over a; if a>1 then a=a-1; else if a=0 then a=4; else a=.; end;')
        self.assertEqual(t['rows'],[{'x':1.,'y':4.,'z':None}])

    def test_ordinary_missing_and_exact_fractional_values(self):
        t=self.table('array a x y; x=.5; do over a; a=a+.25; end; total=sum(of a[*]);')
        self.assertEqual(t['rows'],[{'x':.75,'y':None,'total':.75}])

    def test_dynamic_invalid_expression_is_lazy(self):
        t=self.table('array a x; v=.1; do over a; if 0 then a=v+.2; end;')
        self.assertEqual(t['rows'],[{'x':None,'v':.1}])

    def test_literal_errors_are_eager_on_skipped_paths(self):
        for value in ('2147483648','.1+.2',"'bad'",'.A','int(2)','1/2'):
            self.blocked('array a x; do over a; if 0 then a='+value+'; end;')

    def test_runtime_failure_is_atomic_and_has_source_line(self):
        source='data prior; put "earlier"; run;\ndata d; array a x y; x=1; y=.1;\ndo over a; output; put "row"; a=a+.2; end; run;'
        job=build_job(source);self.assertEqual(job.code,1);self.assertIsNone(job.result)
        self.assertIn('SAS line 3',job.receipt['error'])
        stream=io.StringIO();ns={}
        with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(source).code,ns)
        self.assertEqual(stream.getvalue(),'');self.assertNotIn('result',ns)

    def test_current_expression_shape_and_scope_refuse(self):
        base=compile_plan('data d; array a x; do over a; a=1; end; run;').to_dict()
        for update in ({'kind':'array_current','name':'missing'}, {'kind':'array_current','name':'a','index':1}):
            p=deepcopy(base);p['steps'][0]['operations'][1]['args']['body'][0]['args']['value']=update
            with self.assertRaises(ValueError):run_plan(p)
        p=deepcopy(base);p['steps'][0]['operations'].append(p['steps'][0]['operations'][1]['args']['body'][0])
        with self.assertRaises(ValueError):run_plan(p)

    def test_forged_loop_shapes_and_declaration_modes_refuse(self):
        base=compile_plan('data d; array a x; do over a; a=1; end; run;').to_dict()
        for update in ({'name':'missing'},{'name':[]},{'body':{}},{'body':[None]},{'limit':10000},{'index':'i'}):
            p=deepcopy(base);p['steps'][0]['operations'][1]['args'].update(update)
            with self.assertRaises(ValueError):run_plan(p)
        for key in ('name','body'):
            p=deepcopy(base);del p['steps'][0]['operations'][1]['args'][key]
            with self.assertRaises(ValueError):run_plan(p)
        for update in ({'mode':'explicit'},{'mode':True},{'lower':0}):
            p=deepcopy(base);p['steps'][0]['operations'][0]['args'].update(update)
            with self.assertRaises(ValueError):run_plan(p)
        p=deepcopy(base);del p['steps'][0]['operations'][0]['args']['mode']
        with self.assertRaises(ValueError):run_plan(p)
        p=deepcopy(base);p['version']=1
        with self.assertRaises(ValueError):run_plan(p)

    def test_forged_nested_or_conditional_loop_refuses(self):
        base=compile_plan('data d; array a x; do over a; a=1; end; run;').to_dict()
        loop=base['steps'][0]['operations'][1]
        for child in (deepcopy(loop),{'kind':'do_counted','line':1,'args':{'index':'i','start':1,'stop':2,'by':1,'body':[]}}):
            p=deepcopy(base);p['steps'][0]['operations'][1]['args']['body']=[child]
            with self.assertRaises(ValueError):run_plan(p)
        p=deepcopy(base);p['steps'][0]['operations'][1]={'kind':'if','line':1,'args':{'condition':{'op':'truth','left':{'kind':'number','value':0.}},'operation':deepcopy(loop)}}
        with self.assertRaises(ValueError):run_plan(p)

    def test_internal_index_is_not_user_addressable(self):
        for text in ('_i_=3;','x=_i_;','put _i_=;','array b _i_;','retain _i_ 0;'):
            self.blocked('array a x; '+text+' do over a; a=1; end;')
        raw={'raw':{'schema':{'_i_':'number'},'rows':[]}}
        self.assertEqual(job_with_inputs('data d; set raw; array a x; do over a; a=1; end; run;',raw).code,1)

    def test_boundary_syntax_and_state_conflicts_remain_refused(self):
        for body in ('do over a; a=1; end; array a x;',
                     'array a x; a=1; do over a; end;',
                     'array a x; do over a; end; y=a;',
                     'array a x; do over a; a[1]=1; end;',
                     'array a x; do over a; y=a[1]; end;',
                     'array a x; array b y; do over a; a=b; end;',
                     'array a x; array b[1] y; do over a; a=b[1]; end;',
                     'array a x; do over a; y=lag(x); end;',
                     'array a x; retain x 0; do over a; end;',
                     'array a x; do over a; a+1; end;',
                     'array a x; do over a; do i=1 to 2; end; end;',
                     'array a x; do over a; put a; end;',
                     'array a x; do over a; put _all_; end;',
                     'array a x; do over a while(1); end;',
                     'array a x; do over a;'):
            self.blocked(body)

    def test_null_output_and_cpp_remain_refused(self):
        source='data _null_; array a x; do over a; if 0 then output; end; run;'
        self.assertTrue(compile_plan(source).blocked)
        self.assertTrue(cpp('data _null_; array a x; do over a; a=1; end; run;').blocked)

    def test_existing_put_behavior_through_scalar(self):
        result,printed=execute('data _null_; array a x y; do over a; a=2; v=a; put v; end; run;')
        self.assertEqual(result,{'datasets':{},'log':['2 ','2 ']});self.assertEqual(printed,'2 \n2 \n')
        result,printed=execute('data _null_; array a x; do over a; a=2; if 0 then unused=1; else v=a; put v; end; run;')
        self.assertEqual(result,{'datasets':{},'log':['2 ']});self.assertEqual(printed,'2 \n')

    def test_extent_and_expression_budgets(self):
        t=self.table('array a x1-x1024; do over a; a=1; end;')
        self.assertEqual(len(t['rows'][0]),1024);self.assertEqual(set(t['rows'][0].values()),{1.})
        self.blocked('array a x1-x1025; do over a; end;')
        self.blocked('array a x1-x1024; array b y; do over a; end;')
        self.blocked('array a x; do over a; '+'a=a+1;'*50+' end;')

    def test_helper_refuses_before_callback_and_propagates_failure(self):
        for n in (True,False,None,0,-1,1.0,1025):
            seen=[]
            with self.assertRaises(ValueError):sas_do_over(n,seen.append)
            self.assertEqual(seen,[])
        seen=[]
        def body(offset):
            seen.append(offset)
            if offset==1:raise ValueError('body failure')
        with self.assertRaisesRegex(ValueError,'body failure'):sas_do_over(3,body)
        self.assertEqual(seen,[0,1])

    def test_oversized_current_expressions_refuse_promptly(self):
        for expr in ('+'.join(['a']*130), '('*34+'a'+')'*34):
            source='data d; array a x; do over a; a='+expr+'; end; run;'
            p=subprocess.run([sys.executable,'-c',
                'from saschi.plan import compile_plan; import sys; assert compile_plan(sys.argv[1]).blocked',source],
                capture_output=True,text=True,timeout=5)
            self.assertEqual(p.returncode,0,p.stderr)

    def test_comparator_rejects_values_order_schema_and_multiplicity(self):
        source='data d; array a x y; n=1; do over a; a=n; n=n+1; output; end; run;'
        actual=run_plan(compile_plan(source).to_dict())['datasets']['d']
        mutations=[]
        t=deepcopy(actual);t['rows'][0]['x']=99;mutations.append(t)
        t=deepcopy(actual);t['rows'].reverse();mutations.append(t)
        t=deepcopy(actual);t['rows'].pop();mutations.append(t)
        t=deepcopy(actual);t['schema']={'y':'number','x':'number','n':'number'};mutations.append(t)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'expected.json'
            p.write_text(json.dumps({'d':actual}));self.assertTrue(build_job(source,expect=p).receipt['accepted'])
            for t in mutations:
                p.write_text(json.dumps({'d':t}));job=build_job(source,expect=p)
                self.assertEqual(job.code,1);self.assertEqual(job.receipt['comparison'],'failed')

    def test_full_unmodified_external_program(self):
        p=ROKU_CORPUS/'loops_foreach.sas'
        if not p.is_file():self.skipTest('Roku corpus not present')
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),SOURCE_SHA)
        result,printed=execute(p.read_text());expected={'datasets':{},'log':['55 ']}
        self.assertEqual(result,expected)
        self.assertEqual(hashlib.sha256(printed.encode()).hexdigest(),STDOUT_SHA)
        self.assertEqual(hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest(),RESULT_SHA)
        self.assertEqual(program_records(p),expected['log'])
        job=build_job(p.read_text());self.assertEqual(job.code,0);self.assertTrue(job.receipt['accepted'])
        self.assertEqual(job.receipt['source_sha256'],SOURCE_SHA);self.assertEqual(job.result,expected)
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'cli'
            proc=subprocess.run([sys.executable,'-m','saschi','run',str(p),'--output',str(out)],capture_output=True,text=True,timeout=30)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertEqual(json.loads((out/'result.json').read_text()),expected)
            receipt=json.loads((out/'receipt.json').read_text())
            self.assertTrue(receipt['accepted']);self.assertEqual(receipt['source_sha256'],SOURCE_SHA)
        print('VERIFIED corpus: loops_foreach.sas; full source/stdout/result pins, CLI and independent base R; no live SAS')


if __name__=='__main__':unittest.main()
