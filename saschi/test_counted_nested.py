"""DS-041 captured controls, recursive schedules and refusal evidence."""
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

from examples.verify_counted_nested import PROGRAM, hand_result, program_witness
from sas_semantics import sas_counted_control, sas_counted_capture
from .counted import parse_control
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .test_do_counted import execute, job_with_inputs
from .test_parser import ROKU_CORPUS

SOURCE_SHA = '7e5a469154300963c3f619da372af0b1631c6f51d75a80ea0b67375a5be46025'
RESULT_SHA = 'd027eeb1ab5e969c5ee77c45fb8596c564632b1c9ee52738c83443a15259cbb8'
STDOUT_SHA = 'f7a93a6cfb100bcf8e567df989c1fb386a9220e69792f2d6285ad3b57c6ea8e4'


class CountedNestedTests(unittest.TestCase):
    def table(self, body, inputs=None):
        return execute('data d; '+body+' run;', inputs)[0]['datasets']['d']

    def blocked(self, body):
        plan=compile_plan('data d; '+body+' run;')
        self.assertTrue(plan.blocked,body)

    def test_original_whole_program_pins_R_emitted_and_job(self):
        self.assertEqual(hashlib.sha256(PROGRAM.read_bytes()).hexdigest(),SOURCE_SHA)
        source=PROGRAM.read_text();result,stdout=execute(source)
        self.assertEqual(result,hand_result())
        self.assertEqual(hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest(),RESULT_SHA)
        self.assertEqual(stdout,'total=8 i=4 j=6\n')
        self.assertEqual(hashlib.sha256(stdout.encode()).hexdigest(),STDOUT_SHA)
        self.assertEqual(program_witness(),result['datasets']['capture']['rows'])
        p=compile_plan(source).to_dict();self.assertEqual(run_plan(p),result)
        job=build_job(source);self.assertTrue(job.receipt['accepted']);self.assertEqual(job.result,result)
        self.assertEqual(job.receipt['source_sha256'],SOURCE_SHA)

    def test_original_program_actual_CLI(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'run'
            p=subprocess.run([sys.executable,'-m','saschi','run',str(PROGRAM),'--out',str(out)],capture_output=True,text=True,timeout=30)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            self.assertEqual(json.loads((out/'result.json').read_text()),hand_result())
            self.assertTrue(json.loads((out/'receipt.json').read_text())['accepted'])

    def test_old_literal_plan_stays_unmarked(self):
        p=compile_plan('data d; do i=1 to 2; x=i; end; run;')
        self.assertEqual(set(p.steps[0].operations[1].args),{'index','start','stop','by','body'})
        self.assertEqual(run_plan(p.to_dict())['datasets']['d']['rows'],[{'i':3.,'x':2.}])
        p.version=1
        self.assertEqual(run_plan(p.to_dict())['datasets']['d']['rows'],[{'i':3.,'x':2.}])

    def test_nested_literal_plans_have_explicit_profile(self):
        p=compile_plan('data d; do i=1 to 2; do j=1 to 2; end; end; run;')
        root=p.steps[0].operations[1].args
        self.assertEqual(root['profile'],'bounded')
        self.assertEqual(root['body'][1]['args']['profile'],'bounded')
        self.assertIn(('do-counted-bounded','DS-041',1),p.matched)
        p.version=1
        with self.assertRaises(ValueError):run_plan(p.to_dict())

    def test_controls_captured_once_and_scalar_mutations_visible(self):
        t=self.table('s=1; z=3; b=1; total=0; do i=s to z by b; s=99; z=-9; b=-2; total=total+i; end;')
        self.assertEqual(t['rows'],[{'s':99.,'z':-9.,'b':-2.,'total':6.,'i':4.}])

    def test_inner_controls_recaptured_each_outer_visit(self):
        t=self.table('z=1; do i=1 to 3; do j=i to z+i; z=z+1; output; end; end;')
        self.assertEqual([(r['i'],r['j']) for r in t['rows']],
                         [(1,1),(1,2),(2,2),(2,3),(2,4),(2,5),
                          (3,3),(3,4),(3,5),(3,6),(3,7),(3,8),(3,9),(3,10)])

    def test_computed_descending_and_final_indices(self):
        t=self.table('a=2; do i=(a+1) to -a by -(a-1); do j=i to i-1 by -1; x=j; end; end;')
        self.assertEqual(t['rows'],[{'a':2.,'i':-3.,'j':-4.,'x':-3.}])

    def test_own_index_controls_and_active_index_reuse_refuse(self):
        for header in ('i=i to 3','i=1 to i','i=1 to 2 by i','i=i-i+1 to 2'):
            self.blocked('i=2; do '+header+'; end;')
        self.blocked('do i=1 to 2; do I=1 to 2; end; end;')

    def test_writes_to_any_active_index_refuse_in_all_branches(self):
        for action in ('i=7','j=7','if 0 then i=2','if 0 then x=1; else i=2','i+1','i=round(2,1)'):
            self.blocked('do i=1 to 2; do j=1 to 2; '+action+'; end; end;')

    def test_inner_index_can_be_used_after_it_finishes(self):
        t=self.table('do i=1 to 2; do j=1 to i; x=j; end; j=j+10; end;')
        self.assertEqual(t['rows'],[{'i':3.,'j':13.,'x':2.}])

    def test_zero_trip_outer_discovers_all_schema(self):
        t=self.table("n=0; do i=1 to n; do j=1 to 2; c='xy'; x=1; end; end; after=i;")
        self.assertEqual(list(t['schema']),['n','i','j','c','x','after'])
        self.assertEqual(t['rows'],[{'n':0.,'i':1.,'j':None,'c':'  ','x':None,'after':1.}])

    def test_zero_trip_inner_sets_its_start(self):
        t=self.table('do i=1 to 2; do j=i+2 to i; x=1; end; output; end;')
        self.assertEqual(t['rows'],[{'i':1.,'j':3.,'x':None},{'i':2.,'j':4.,'x':None}])

    def test_unreached_dynamic_control_is_lazy_but_static_invalid_is_eager(self):
        t=self.table('n=0; do i=1 to n; do j=missingvar to 2; end; end;')
        self.assertEqual(t['rows'],[{'n':0.,'i':1.,'j':None,'missingvar':None}])
        for control in ('1+2147483647','1 to 2 by 0'):
            header='j='+control+(' to 2' if ' to ' not in control else '')
            self.blocked('do i=2 to 1; do '+header+'; end; end;')

    def test_explicit_output_suppresses_implicit_even_when_skipped(self):
        for body in ('n=0; do i=1 to n; do j=1 to 2; output; end; end;',
                     'do i=1 to 2; do j=1 to 2; if 0 then output; end; end;'):
            self.assertEqual(self.table(body)['rows'],[])

    def test_multiple_outputs_and_future_values(self):
        t=self.table('do i=1 to 1; do j=1 to 1; x=2; output; x=3; output; end; end; later=9;')
        self.assertEqual(t['rows'],[{'i':1.,'j':1.,'x':2.,'later':None},{'i':1.,'j':1.,'x':3.,'later':None}])

    def test_per_row_reset_N_and_input_index_descriptors(self):
        raw={'raw':{'schema':{'n':'number','j':{'type':'number','label':'inner'}},'rows':[{'n':1,'j':80},{'n':2,'j':90}]}}
        t=self.table('set raw; do i=1 to n; do j=1 to i; prior=scratch; scratch=_n_; output; end; end;',raw)
        self.assertEqual([r['prior'] for r in t['rows']],[None,None,2.,2.])
        self.assertEqual([r['scratch'] for r in t['rows']],[1.,2.,2.,2.])
        self.assertEqual(t['schema']['j'],{'type':'number','label':'inner'})

    def test_plan_catalog_and_run_state_isolation(self):
        raw={'raw':{'schema':{'n':'number'},'rows':[{'n':2}]}}
        p=compile_plan('data d; set raw; do i=1 to n; do j=1 to i; x=j; end; end; run;').to_dict()
        before=deepcopy((p,raw));a=run_plan(p,raw)
        self.assertEqual(run_plan(p,raw),a);self.assertEqual((p,raw),before)

    def test_empty_filtered_inputs_validate_character_controls(self):
        for rows,where in (([],''),([{'n':'x'}],'where 0;')):
            raw={'raw':{'schema':{'n':{'type':'character','length':1}},'rows':rows}}
            self.assertEqual(job_with_inputs('data d; set raw; '+where+' do i=1 to n; end; run;',raw).code,1)
        self.blocked('n=0; do i=1 to n; do j=1 to 2; length x $3; end; end;')

    def test_numeric_empty_input_preserves_nested_schema(self):
        raw={'raw':{'schema':{'n':'number'},'rows':[]}}
        t=self.table('set raw; do i=1 to n; do j=i to n; if 0 then unseen=j; end; end;',raw)
        self.assertEqual(t,{'schema':dict.fromkeys(['n','i','j','unseen'],'number'),'rows':[]})

    def test_numeric_control_refusals_cannot_hide_invalid_operands(self):
        for value in (None,True,1.5,float('inf'),float('nan'),2147483648,{'missing':'A'}):
            with self.subTest(value=value),self.assertRaises(ValueError):sas_counted_control(value)
        with self.assertRaises(ValueError):sas_counted_control(10**5000)
        for expr in ('n','n-n+1'):
            raw={'raw':{'schema':{'n':'number'},'rows':[{'n':1.5}]}}
            job=job_with_inputs('data d; set raw; do i=1 to '+expr+'; end; run;',raw)
            self.assertEqual(job.code,1);self.assertIsNone(job.result)

    def test_control_syntax_and_expression_budgets(self):
        for control in ('1.0','1e0','١','K','Ｋ','é','round(2,1)','a[1]','sum(of a[*])','1*2','1/1','.',
                        'first.x','_error_','1,2','(' * 34+'1'+')'*34,'+'.join(['1']*129)):
            self.blocked('do i='+control+' to 3; end;')
        with self.assertRaises(ValueError):parse_control('9'*5000)
        with self.assertRaises(ValueError):parse_control('1 junk')

    def test_depth_boundary_and_unbalanced_groups(self):
        body=''.join(f'do i{n}=1 to 1;' for n in range(8))+'x=7;'+'end;'*8
        self.assertEqual(self.table(body)['rows'],[{**{f'i{n}':2. for n in range(8)},'x':7.}])
        self.blocked(''.join(f'do i{n}=1 to 1;' for n in range(9))+'end;'*9)
        for body in ('do i=1 to 2; do j=1 to 2; end;', 'do i=1 to 2; end; end;'):
            self.blocked(body)

    def test_aggregate_work_boundary(self):
        t=self.table('total=0; do i=1 to 2; do j=1 to 4999; total=total+1; end; end;')
        self.assertEqual(t['rows'],[{'total':9998.,'i':3.,'j':5000.}])
        job=build_job('data d; do i=1 to 2; do j=1 to 5000; end; end; run;')
        self.assertEqual(job.code,1);self.assertIsNone(job.result)

    def test_budget_shared_by_A2_roots_and_reset_each_row(self):
        raw={'raw':{'schema':{'n':'number'},'rows':[{'n':5000},{'n':5000}]}}
        t=self.table('set raw; do i=1 to n; end; do j=1 to n; end;',raw)
        self.assertEqual(t['rows'],[{'n':5000.,'i':5001.,'j':5001.}]*2)
        source='data d; n=5000; do i=1 to n; end; do j=1 to n; end; do k=1 to n; end; run;'
        self.assertEqual(build_job(source).code,1)
        # Legacy independent literal roots retain their pre-A2 per-loop contract.
        self.assertEqual(self.table('do i=1 to 10000; end; do j=1 to 10000; end;')['rows'],[{'i':10001.,'j':10001.}])

    def test_skipped_inner_loop_consumes_no_trips(self):
        self.assertEqual(self.table('do i=1 to 10000; do j=2 to 1; end; end;')['rows'],[{'i':10001.,'j':2.}])

    def test_literal_final_index_may_pass_control_bound(self):
        t=self.table('n=2147483647; do i=n to n by n; end;')
        self.assertEqual(t['rows'],[{'n':2147483647.,'i':4294967294.}])

    def test_nested_retained_sum_and_selected_branches(self):
        t=self.table('do i=1 to 2; do j=1 to i; if j=1 then total+i; else total+10; end; end;')
        self.assertEqual(t['rows'],[{'i':3.,'j':3.,'total':13.}])

    def test_aliases_cannot_mutate_loop_indices(self):
        self.blocked('array a i x; do i=1 to 2; do j=1 to 2; a[1]=7; end; end;')
        self.blocked('array a x; do i=1 to 2; do a=1 to 2; end; end;')

    def test_boundary_operations_remain_refused(self):
        for body in ('do while(1); end;', 'do until(1); end;', 'do over a; end;',
                     'leave;', 'continue;', 'set raw;', 'retain x 0;', 'put _all_;',
                     'if 1 then do j=1 to 2; end;', 'x=lag(i);'):
            body_source='n=2; do i=1 to n; '+body+' end;'
            if body in ('leave;','continue;'):
                from .test_grouped_control import assert_promoted_source
                assert_promoted_source(self,'data d; '+body_source+' run;')
            else:self.blocked(body_source)
        self.blocked('do while(1); do i=1 to 2; end; end;')
        self.blocked('do i=1 to 2 while(1); end;')

    def test_atomic_late_row_failure_and_source_line(self):
        source="data d; set raw; put 'before';\ndo i=1 to n;\n do j=1 to i; output; end; end; run;"
        raw={'raw':{'schema':{'n':'number'},'rows':[{'n':2},{'n':1.5}]}}
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream),self.assertRaisesRegex(ValueError,'SAS line 2'):
            exec(translate(source).code,{'inputs':raw})
        self.assertEqual(stream.getvalue(),'')
        job=job_with_inputs(source,raw);self.assertEqual(job.code,1);self.assertIsNone(job.result)

    def test_malformed_markers_and_controls_refuse_independently(self):
        original=compile_plan('data d; n=2; do i=1 to n; do j=1 to i; x=j; end; end; run;').to_dict()
        for mutation in ('profile','extra','missing','zero','bool','call','character','self','unmark','child-unmark','own-index','no-declare','write','unknown'):
            p=deepcopy(original);a=p['steps'][0]['operations'][2]['args'];child=a['body'][1]['args']
            if mutation=='profile':a['profile']='unchecked'
            elif mutation=='extra':a['extra']=0
            elif mutation=='missing':a.pop('stop')
            elif mutation=='zero':a['by']=0
            elif mutation=='bool':a['start']=True
            elif mutation=='call':a['start']={'kind':'call','name':'lag','args':[]}
            elif mutation=='character':a['stop']={'kind':'character','value':'2'}
            elif mutation=='self':a['stop']={'kind':'variable','value':'i'}
            elif mutation=='unmark':a.pop('profile')
            elif mutation=='child-unmark':child.pop('profile')
            elif mutation=='own-index':child['index']='i'
            elif mutation=='no-declare':a['body'].pop(0)
            elif mutation=='write':child['body'][0]['args']['name']='i'
            else:child['body'].append({'kind':'input','line':1,'args':{}})
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):run_plan(p)

    def test_malformed_tree_depth_shape_and_hidden_control(self):
        original=compile_plan('data d; n=2; do i=1 to n; x=1; end; run;').to_dict()
        for body in (None,{},[{}],[{'kind':'assign','line':1,'args':None}],[{'kind':[],'line':1,'args':{}}]):
            p=deepcopy(original);p['steps'][0]['operations'][2]['args']['body']=body
            with self.subTest(body=body),self.assertRaises(ValueError):run_plan(p)
        p=deepcopy(original);op=p['steps'][0]['operations'].pop()
        p['steps'][0]['operations'].append({'kind':'if','line':1,'args':{'condition':{'op':'truth','left':{'kind':'number','value':0}},'operation':op}})
        with self.assertRaises(ValueError):run_plan(p)

    def test_comparator_value_order_multiplicity_and_schema_controls(self):
        for change in ('value','order','multiplicity','schema'):
            wrong=hand_result();t=wrong['datasets']['capture']
            if change=='value':t['rows'][0]['first']=9.
            elif change=='order':t['rows'].reverse()
            elif change=='multiplicity':t['rows'].append(deepcopy(t['rows'][0]))
            else:t['schema']={k:v for k,v in reversed(list(t['schema'].items()))}
            with tempfile.TemporaryDirectory() as d:
                path=Path(d)/'wrong.json';path.write_text(json.dumps(wrong))
                job=build_job(PROGRAM.read_text(),expect=path)
                self.assertFalse(job.receipt['accepted']);self.assertNotEqual(job.code,0)
                self.assertEqual(job.result,hand_result())

    def test_null_output_cpp_and_promoted_A3_whole_program(self):
        self.assertTrue(compile_plan('data _null_; n=2; do i=1 to n; output; end; run;').blocked)
        self.assertEqual(build_job(PROGRAM.read_text(),target='cpp').code,2)
        source=(ROKU_CORPUS/'100_doors.sas').read_text()
        plan=compile_plan(source)
        # DS-042 promotes the exact former runtime refusal to whole-file evidence.
        self.assertFalse(plan.blocked,plan.tickets)
        job=build_job(source)
        self.assertEqual(job.code,0);self.assertTrue(job.receipt['accepted'])
        self.assertEqual(job.result,{'datasets':{},'log':['Number of Open Doors:  10 ']})

    def test_step_expression_and_body_operation_budgets(self):
        self.blocked('n=1;'+'do i=1 to n; end;'*43)
        self.blocked('n=1; do i=1 to n;'+'x=1;'*257+'end;')
        result=self.table('n=1; do i=1 to n;'+'x=1;'*256+'end;')
        self.assertEqual(result['rows'],[{'n':1.,'i':2.,'x':1.}])

    def test_invalid_plan_expression_shapes_and_unmarked_controls(self):
        original=compile_plan('data d; n=2; do i=1 to n; end; run;').to_dict()
        malformed=[{},[],{'kind':[]}, {'kind':'variable','value':[]},
                   {'kind':'automatic','value':'first.x'},
                   {'kind':'number','value':True},
                   {'kind':'number','value':1,'extra':0},
                   {'kind':'arithmetic','op':'*','left':1,'right':2}]
        for expr in malformed:
            p=deepcopy(original);p['steps'][0]['operations'][2]['args']['stop']=expr
            with self.subTest(expr=expr),self.assertRaises(ValueError):run_plan(p)
        p=deepcopy(original);p['steps'][0]['operations'][2]['args'].pop('profile')
        with self.assertRaises(ValueError):run_plan(p)

    def test_late_inner_budget_failure_is_atomic(self):
        source="data d; put 'before'; do i=1 to 2; do j=1 to 5000; if j=1 then output; end; end; run;"
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream),self.assertRaisesRegex(ValueError,'10000 total iterations'):
            exec(translate(source).code,{})
        self.assertEqual(stream.getvalue(),'');self.assertIsNone(build_job(source).result)

    def test_scalar_put_round_and_implicit_output_schedule(self):
        source="data d; n=2; do i=1 to n; do j=1 to i; x=round(2.5,1); put x=; end; end; run;"
        result,printed=execute(source)
        self.assertEqual(result['datasets']['d']['rows'],[{'n':2.,'i':3.,'j':3.,'x':3.}])
        self.assertEqual(result['log'],['x=3']*3);self.assertEqual(printed,'x=3\n'*3)

    def test_inherited_and_future_character_indices_refuse(self):
        for body,raw in [("n=0; do i=1 to n; do j=1 to 2; end; end; j='x';",{}),
                         ('set raw; do i=1 to n; do j=1 to 2; end; end;',
                          {'raw':{'schema':{'n':'number','j':{'type':'character','length':1}},'rows':[]}})]:
            job=job_with_inputs('data d; '+body+' run;',raw)
            self.assertEqual(job.code,1);self.assertIsNone(job.result)


if __name__=='__main__':unittest.main()
