"""DS-031 bounded control evidence for maintainer review, no live SAS."""
import contextlib
from copy import deepcopy
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import unittest

from examples.verify_do_if import program_records
from .emit_py import translate
from .job import build_job
from .operations import walk_operations
from .plan import Operation, compile_plan
from .rules import route_statement
from .runtime import run_plan
from .test_parser import ROKU_CORPUS
from .test_put_list import build_job as job_with_inputs

SOURCE_SHA='a2aa8937eb12194fa2b271dd89a329e3be75facae0025961849984dad37b969e'
STDOUT_SHA='a5efa59cf533c9bdc41629d453023d1eefdffd44cdde6e45f654fc04813651aa'
RESULT_SHA='ed842e4d91c5b29bcd9703f6b75c32d33b5577566c4c65b9fc7c0b1e1ef96fd4'


def execute(source,inputs=None):
    translated=translate(source)
    if translated.blocked:raise AssertionError(translated.tickets)
    namespace={'inputs':inputs or {}};printed=io.StringIO()
    with contextlib.redirect_stdout(printed):exec(translated.code,namespace)
    return namespace['result'],printed.getvalue()


class DoIfTests(unittest.TestCase):
    def test_plan_preserves_old_if_shape_and_adds_otherwise(self):
        p=compile_plan('data d; if 1 then x=7; run;')
        self.assertEqual(set(p.steps[0].operations[0].args),{'condition','operation'})
        p=compile_plan('data d; if 0 then x=7; else if 1 then x=9; else x=11; run;')
        self.assertFalse(p.blocked,p.tickets)
        op=p.steps[0].operations[0]
        self.assertEqual(op.args['otherwise']['kind'],'if')
        self.assertEqual(op.args['otherwise']['args']['otherwise']['args']['value']['value'],11.)
        self.assertIn(('do-if','DS-031',1),p.matched)
        self.assertEqual(route_statement('if 1 then x=7'),('do-if','DS-031'))
        self.assertEqual(route_statement('else x=7'),('do-if','DS-031'))

    def test_first_match_and_lazy_conditions(self):
        for condition,value in [('1',7.),('0',11.),('.',11.),('.A',11.),('-1',7.)]:
            result,_=execute('data d; if '+condition+' then x=7; else x=11; run;')
            self.assertEqual(result['datasets']['d']['rows'],[{'x':value}])
        result,_=execute('data d; if 1 then x=7; else if mod(1,0)=0 then x=9; else x=11; run;')
        self.assertEqual(result['datasets']['d']['rows'],[{'x':7.}])
        result,_=execute('data d; if 1 then x=7; else if 1 then x=9; else x=11; run;')
        self.assertEqual(result['datasets']['d']['rows'],[{'x':7.}])

    def test_independent_ifs_still_both_execute(self):
        result,_=execute('data d; x=0; if 1 then x=x+1; if 1 then x=x+1; run;')
        self.assertEqual(result['datasets']['d']['rows'],[{'x':2.}])

    def test_else_adjacency_comments_and_empty_statement_boundary(self):
        for separation in (' ',' /* comment */ ',' * comment; ',' %* comment; '):
            result,_=execute('data d; if 0 then x=1;'+separation+'else x=2; run;')
            self.assertEqual(result['datasets']['d']['rows'],[{'x':2.}])
        for source in ('data d; else x=1; run;', 'data d; if 0 then x=1;; else x=2; run;',
                       'data d; if 0 then x=1; y=7; else x=2; run;',
                       'data a; if 0 then x=1; run; data d; else x=2; run;',
                       'data d; do i=1 to 2; if 0 then x=1; end; else x=2; run;',
                       'data d; if 0 then x=1; else x=2; else x=3; run;'):
            with self.subTest(source=source):self.assertTrue(compile_plan(source).blocked)

    def test_keyword_shaped_values_and_names_are_not_branch_syntax(self):
        result,_=execute("data d; else=7; then=1; if then then x='then'; else x='else'; run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'else':7.,'then':1.,'x':'then'}])
        result,_=execute("data d; do i=1 to 2; else=7; if 'then'='then' then x=1; else x=2; end; run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'i':3.,'else':7.,'x':1.}])

    def test_literal_character_numeric_and_named_put_branches(self):
        source=("data _null_; c=' A '; n=7; do i=1 to 2; if i=1 then put 'left'; else put 'right'; "
                "if i=1 then put '[' c ']'; else put c; if i=1 then put n; else put i n; "
                "if i=1 then put n=; else put i= n=; end; run;")
        result,printed=execute(source)
        self.assertEqual(result,{'datasets':{},'log':['left','[A ]','7 ','n=7','right','A ','2 7 ','i=2 n=7']})
        self.assertEqual(printed,'\n'.join(result['log'])+'\n')

    def test_put_quoted_keywords_and_doubled_quotes(self):
        result,_=execute("data _null_; if 0 then put 'then'; else put 'else' 'O''Q'; run;")
        self.assertEqual(result['log'],["elseO'Q"])

    def test_branch_put_retains_type_adjacency_and_format_refusals(self):
        for action in ("put '41'x", "put '41'/* comment */x", 'put x $2.', 'put n best12.',
                       'put _all_', 'put _n_', 'put 7'):
            source="data d; x='A'; n=7; if 0 then "+action+'; else n=9; run;'
            with self.subTest(action=action):self.assertTrue(compile_plan(source).blocked)
        result,_=execute("data d; x='A'; if 1 then put '41' x; else put 'hidden'; run;")
        self.assertEqual(result['log'],['41A '])

    def test_branch_schema_is_source_order_even_when_skipped(self):
        result,_=execute("data d; if 0 then x='A'; else x='BC'; run;")
        self.assertEqual(result['datasets']['d'],{'schema':{'x':{'type':'character','length':1}},'rows':[{'x':'B'}]})
        result,_=execute("data d; a='ABCDE'; if 0 then x=substr(a,2,3); else x=substr(a,3,2); run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':'ABCDE','x':'CD   '}])

    def test_zero_trip_and_false_branches_keep_all_descriptors(self):
        source="data d; do i=2 to 1; if 0 then x='ABC'; else if 1 then y=7; else z='QQ'; end; run;"
        result,printed=execute(source)
        self.assertEqual(result['datasets']['d'],{'schema':{'i':'number','x':{'type':'character','length':3},'y':'number','z':{'type':'character','length':2}},'rows':[{'i':2.,'x':'   ','y':None,'z':'  '}]})
        self.assertEqual(printed,'')

    def test_output_in_any_skipped_branch_suppresses_implicit_output(self):
        for source in ('data d; if 1 then x=7; else output; run;',
                       'data d; do i=2 to 1; if 1 then output; else x=7; end; run;',
                       'data d; do i=1 to 2; if 0 then output; else x=7; end; run;'):
            self.assertEqual(execute(source)[0]['datasets']['d']['rows'],[])
        result,_=execute('data d; do i=1 to 3; if i=2 then output; else x=i; end; run;')
        self.assertEqual(result['datasets']['d']['rows'],[{'i':2.,'x':1.}])

    def test_set_rows_have_independent_branch_dispatch_and_n(self):
        inputs={'raw':{'schema':{'flag':'number'},'rows':[{'flag':0},{'flag':1}]}}
        source='data d; set raw; do i=1 to 2; if flag=1 then seen=_n_; else seen=0; output; end; run;'
        result,_=execute(source,inputs)
        self.assertEqual(result['datasets']['d']['rows'],[
            {'flag':0.,'i':1.,'seen':0.},{'flag':0.,'i':2.,'seen':0.},
            {'flag':1.,'i':1.,'seen':2.},{'flag':1.,'i':2.,'seen':2.}])

    def test_empty_input_checks_skipped_put_descriptors(self):
        source='data d; set raw; do i=2 to 1; if 0 then put c; else if 0 then put n; else x=1; end; run;'
        inputs={'raw':{'schema':{'c':{'type':'character','length':2,'format':'$2.'},'n':'number'},'rows':[]}}
        job=job_with_inputs(source,inputs);self.assertEqual(job.code,1);self.assertIn('format',job.receipt['error'])
        inputs['raw']['schema']['c'].pop('format');inputs['raw']['schema']['n']={'type':'number','format':'8.2'}
        job=job_with_inputs(source,inputs);self.assertEqual(job.code,1);self.assertIn('format',job.receipt['error'])

    def test_filtered_input_keeps_else_schema_and_static_checks(self):
        inputs={'raw':{'schema':{'a':{'type':'character','length':5}},'rows':[{'a':'ABCDE'}]}}
        source="data d; set raw; where 0; if 1 then x=substr(a,1,1); else x=substr(a,2,2); run;"
        result,_=execute(source,inputs);self.assertEqual(result['datasets']['d']['schema']['x']['length'],5)
        self.assertEqual(result['datasets']['d']['rows'],[])
        with self.assertRaisesRegex(ValueError,'SUBSTR'):
            execute(source.replace('substr(a,2,2)','substr(a,5,2)'),inputs)

    def test_loop_index_writes_are_refused_in_every_branch(self):
        for branch in ('if 1 then i=3','if 0 then i=3','if 1 then x=7; else i=3',
                       'if 1 then x=7; else if 0 then i=3; else x=9'):
            for controls in ('1 to 2','2 to 1'):
                source='data d; do i='+controls+'; '+branch+'; end; run;'
                with self.subTest(branch=branch,controls=controls):self.assertTrue(compile_plan(source).blocked)

    def test_subsetting_groups_reads_and_nested_conditionals_remain_refused(self):
        for branch in ('if 1', 'if 1 then do; x=7; end', 'if 1 then if 0 then x=7',
                       'if 1 then do j=1 to 2; end','if 1 then set raw',
                       'if 1 then length x $3','if 1 then retain x 0','if 1 then leave','if 1 then continue'):
            self.assertTrue(compile_plan('data d; do i=1 to 2; '+branch+'; end; run;').blocked,branch)
        self.assertTrue(compile_plan('data d; if 1 then x=7; else do; x=9; end; run;').blocked)

    def test_chain_limit_is_enforced_in_compile_and_forged_plan(self):
        chain='if 0 then x=1; '+'else if 0 then x=1; '*31+'else x=7;'
        self.assertEqual(execute('data d; '+chain+' run;')[0]['datasets']['d']['rows'],[{'x':7.}])
        self.assertTrue(compile_plan('data d; if 0 then x=1; '+chain.replace('if 0','else if 0',1)+' run;').blocked)
        p=compile_plan('data d; if 1 then x=1; run;').to_dict();leaf=deepcopy(p['steps'][0]['operations'][0]);parent=leaf
        for _ in range(32):
            parent['args']['otherwise']=deepcopy(p['steps'][0]['operations'][0]);parent=parent['args']['otherwise']
        p['steps'][0]['operations']=[leaf];p['tickets']=[]
        with self.assertRaisesRegex(ValueError,'32-condition'):run_plan(p,allow_partial=True)

    def test_else_traversal_preserves_identity_and_preorder(self):
        yes={'kind':'assign','line':2,'args':{'name':'x','value':{'kind':'number','value':1.}}}
        no={'kind':'output','line':3,'args':{'target':None}}
        op=Operation('if',1,{'condition':{},'operation':yes,'otherwise':no});before=deepcopy(op)
        walked=list(walk_operations([op]));self.assertIs(walked[0],op);self.assertIs(walked[1],yes);self.assertIs(walked[2],no)
        self.assertEqual(op,before)
        self.assertEqual([asdict(x) if isinstance(x,Operation) else x for x in walked],list(walk_operations([asdict(op)])))

    def test_runtime_rejects_hidden_unsafe_branch_operations(self):
        original=compile_plan('data d; do i=1 to 2; if 0 then x=1; else x=2; end; run;').to_dict()
        root=original['steps'][0]['operations'][1]['args']['body'][0]
        for mode in ('index','declare','read','nested-do','subset','put-all','extra','condition','missing','null'):
            p=deepcopy(original);node=p['steps'][0]['operations'][1]['args']['body'][0];args=node['args']
            if mode=='index':args['otherwise']['args']['name']='i'
            elif mode=='declare':args['otherwise']={'kind':'declare','line':1,'args':{'name':'y','spec':'number'}}
            elif mode=='read':args['otherwise']={'kind':'read','line':1,'args':{'datasets':['raw']}}
            elif mode=='nested-do':args['otherwise']=deepcopy(p['steps'][0]['operations'][1])
            elif mode=='subset':args['otherwise']={'kind':'subset','line':1,'args':{'condition':args['condition']}}
            elif mode=='put-all':args['otherwise']={'kind':'put_all','line':1,'args':{}}
            elif mode=='extra':args['unexpected']=0
            elif mode=='condition':args['condition']={}
            elif mode=='missing':args.pop('operation')
            else:args['otherwise']=None
            p['tickets']=[];p['matched']=[]
            with self.subTest(mode=mode),self.assertRaises(ValueError):run_plan(p,allow_partial=True)

    def test_source_guards_see_both_branch_directions(self):
        for body in ("if 0 then put n; else n=9;", "if 1 then n=9; else put n;"):
            source='data d; n=7; do i=2 to 1; '+body+' end; unused="&macro"; run;'
            self.assertTrue(compile_plan(source).blocked)
        self.assertTrue(compile_plan("data d; n=7; if 1 then n=9; else put n; unused='é'; run;").blocked)

    def test_late_condition_or_put_failure_is_atomic(self):
        sources=["data prior; put 'earlier'; run; data d; do i=1 to 2; if i=1 then put 'row'; else if mod(1,0)=0 then x=1; end; run;",
                 "data prior; put 'earlier'; run; data d; c='ok'; do i=1 to 2; if i=1 then put c; else c=' '; put c; end; run;"]
        for source in sources:
            translated=translate(source);self.assertFalse(translated.blocked,translated.tickets)
            printed=io.StringIO();ns={}
            with contextlib.redirect_stdout(printed),self.assertRaises(ValueError):exec(translated.code,ns)
            self.assertEqual(printed.getvalue(),'');self.assertNotIn('result',ns)
            job=build_job(source);self.assertEqual(job.code,1);self.assertIsNone(job.result)

    def test_null_output_and_cpp_stay_deferred(self):
        self.assertTrue(compile_plan('data _null_; do i=1 to 2; if 0 then output; else x=7; end; run;').blocked)
        job=build_job("data _null_; if 1 then put 'row'; else put 'other'; run;",target='cpp')
        self.assertEqual(job.code,2);self.assertIsNone(job.result)


class FizzBuzzProgramTests(unittest.TestCase):
    def test_unmodified_external_program_complete_proof(self):
        path=ROKU_CORPUS/'fizzbuzz.sas'
        if not path.is_file():self.skipTest('Roku corpus not present')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),SOURCE_SHA)
        result,printed=execute(path.read_text())
        self.assertEqual(hashlib.sha256(printed.encode()).hexdigest(),STDOUT_SHA)
        packed=json.dumps(result,sort_keys=True,separators=(',',':')).encode()
        self.assertEqual(hashlib.sha256(packed).hexdigest(),RESULT_SHA)
        independent,final_index=program_records(path)
        self.assertEqual(result,{'datasets':{},'log':independent});self.assertEqual(len(independent),100)
        self.assertEqual(final_index,101)
        self.assertEqual(hashlib.sha256(('\n'.join(independent)+'\n').encode()).hexdigest(),STDOUT_SHA)
        job=build_job(path.read_text());self.assertEqual(job.code,0);self.assertTrue(job.receipt['accepted'])
        self.assertEqual(job.receipt['source_sha256'],SOURCE_SHA);self.assertEqual(job.receipt['tickets'],[])
        self.assertEqual(job.result,result)
        print('VERIFIED corpus: fizzbuzz.sas; source/stdout/complete-result hashes, shared job and independent base R; no live SAS')


if __name__=='__main__':unittest.main()
