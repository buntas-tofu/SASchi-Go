"""DS-007 bounded source execution evidence for maintainers, no live SAS."""
import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

from sas_semantics import SasNumericLagQueue, sas_lag_numeric
from .emit_py import translate
from .functions import FUNCTIONS, LAG_FUNCTIONS, apply, validate_lag_calls
from .job import build_job
from .plan import compile_plan
from .rules import route_function
from .runtime import number, run_plan
from .test_put_list import build_job as job_with_inputs


def inputs(values,flags=None,keys=None):
    rows=[{'x':value} for value in values];schema={'x':'number'}
    if flags is not None:
        schema['flag']='number'
        for row,flag in zip(rows,flags):row['flag']=flag
    if keys is not None:
        schema['key']='number'
        for row,key in zip(rows,keys):row['key']=key
    return {'raw':{'schema':schema,'rows':rows}}


def execute(source,catalog=None):
    plan=compile_plan(source)
    if plan.blocked:raise AssertionError(plan.tickets)
    return run_plan(plan.to_dict(),catalog)


class LagExecutionTests(unittest.TestCase):
    def test_all_canonical_names_registered_and_routed(self):
        self.assertEqual(len(LAG_FUNCTIONS),202)
        for family in ('lag','dif'):
            for depth in range(1,101):
                name=family+str(depth)
                self.assertEqual(LAG_FUNCTIONS[name],(family,depth))
                self.assertEqual(FUNCTIONS[name].gate,'examples/verify_lag_execution.py')
                self.assertEqual(route_function('y='+name+'(x)'),('lag-dif','DS-007'))
        p=compile_plan('data d; x=lag100(1); y=dif2(.); run;')
        self.assertFalse(p.blocked,p.tickets)
        self.assertIn(('lag-dif','DS-007',1),p.matched)
        for name in ('lag0','lag01','lag101','dif0','dif001','dif101'):
            self.assertTrue(compile_plan('data d; x='+name+'(1); run;').blocked,name)

    def test_queue_initialization_and_depth_boundary(self):
        q=SasNumericLagQueue(100)
        self.assertEqual([q.invoke(float(i)) for i in range(100)],[None]*100)
        self.assertEqual(q.invoke(100.),0.)
        for depth in (0,101,-1,True,1.,None):
            with self.subTest(depth=depth),self.assertRaises(ValueError):SasNumericLagQueue(depth)

    def test_invalid_values_do_not_mutate_queue(self):
        for value in (10**400,True,False,{'missing':'A'},float('nan'),float('inf'),float('-inf'),'1',[]):
            q=SasNumericLagQueue(1);self.assertIsNone(q.invoke(7.))
            with self.subTest(value=repr(value)[:40]),self.assertRaises(ValueError):q.invoke(value)
            self.assertEqual(q.invoke(9.),7.)
        q=SasNumericLagQueue(1);q.invoke(7.)
        with self.assertRaises(ValueError):q.invoke(9.,difference='yes')
        self.assertEqual(q.invoke(11.),7.)

    def test_dif_overflow_is_refused_before_mutation(self):
        q=SasNumericLagQueue(1);self.assertIsNone(q.invoke(1e308,difference=True))
        with self.assertRaisesRegex(ValueError,'DIF overflow'):q.invoke(-1e308,difference=True)
        self.assertEqual(q.invoke(1e308,difference=True),0.)

    def test_ordinary_missing_is_a_real_invocation(self):
        q=SasNumericLagQueue(1)
        self.assertEqual([q.invoke(x) for x in (10.,None,30.,40.)],[None,10.,None,30.])
        q=SasNumericLagQueue(1)
        self.assertEqual([q.invoke(x,difference=True) for x in (10.,None,30.,40.)],[None,None,None,10.])
        self.assertIsNone(sas_lag_numeric(None))

    def test_conditional_invocation_differs_from_conditional_use(self):
        source='data d; set raw; if flag then c=lag(x); u=lag(x); if flag then used=u; run;'
        result=execute(source,inputs([10,20,30,40],[0,1,0,1]))['datasets']['d']['rows']
        self.assertEqual([r['c'] for r in result],[None,None,None,20.])
        self.assertEqual([r['u'] for r in result],[None,10.,20.,30.])
        self.assertEqual([r['used'] for r in result],[None,10.,None,30.])

    def test_lag2_dif2_and_ordinary_aliases(self):
        source='data d; set raw; a=lag(x); b=lag1(x); c=lag2(x); d=dif(x); e=dif1(x); f=dif2(x); run;'
        rows=execute(source,inputs([10,25,31,40]))['datasets']['d']['rows']
        self.assertEqual([r['c'] for r in rows],[None,None,10.,25.])
        self.assertEqual([r['f'] for r in rows],[None,None,21.,15.])
        self.assertEqual([r['a'] for r in rows],[r['b'] for r in rows])
        self.assertEqual([r['d'] for r in rows],[None,15.,6.,9.])
        self.assertEqual([r['d'] for r in rows],[r['e'] for r in rows])

    def test_identical_same_line_calls_own_independent_queues(self):
        source='data d; set raw; if flag then a=lag(x); b=lag(x); run;'
        p=compile_plan(source);conditional=p.to_dict()['steps'][0]['operations'][1]
        self.assertEqual(conditional['line'],p.to_dict()['steps'][0]['operations'][2]['line'])
        rows=execute(source,inputs([10,20,30,40],[1,0,1,0]))['datasets']['d']['rows']
        self.assertEqual([r['a'] for r in rows],[None,None,10.,None])
        self.assertEqual([r['b'] for r in rows],[None,10.,20.,30.])

    def test_aliased_operation_in_two_top_positions_is_not_one_queue(self):
        p=compile_plan('data d; set raw; y=lag(x); run;').to_dict()
        p['steps'][0]['operations'].append(p['steps'][0]['operations'][1])
        self.assertIs(p['steps'][0]['operations'][1],p['steps'][0]['operations'][2])
        rows=run_plan(p,inputs([10,20,30]))['datasets']['d']['rows']
        self.assertEqual([r['y'] for r in rows],[None,10.,20.])

    def test_aliased_then_else_positions_own_distinct_queues(self):
        p=compile_plan('data d; set raw; if flag then y=lag(x); else y=lag(x); run;').to_dict()
        args=p['steps'][0]['operations'][1]['args'];args['otherwise']=args['operation']
        rows=run_plan(p,inputs([10,20,30,40],[1,0,1,0]))['datasets']['d']['rows']
        self.assertEqual([r['y'] for r in rows],[None,None,10.,20.])

    def test_aliased_expression_objects_do_not_share_occurrences(self):
        p=compile_plan('data d; set raw; if flag then a=lag(x); b=lag(x); run;').to_dict()
        p['steps'][0]['operations'][2]['args']['value']=p['steps'][0]['operations'][1]['args']['operation']['args']['value']
        rows=run_plan(p,inputs([10,20,30,40],[1,0,1,0]))['datasets']['d']['rows']
        self.assertEqual([r['a'] for r in rows],[None,None,10.,None])
        self.assertEqual([r['b'] for r in rows],[None,10.,20.,30.])

    def test_loop_path_excludes_trip_and_input_row(self):
        source='data d; set raw; do i=1 to 2; y=lag(x); n=lag(_n_); output; end; run;'
        rows=execute(source,inputs([10,20]))['datasets']['d']['rows']
        self.assertEqual([r['y'] for r in rows],[None,10.,10.,20.])
        self.assertEqual([r['n'] for r in rows],[None,1.,1.,2.])
        self.assertEqual([r['i'] for r in rows],[1.,2.,1.,2.])

    def test_loop_else_dispatch_has_separate_histories(self):
        source='data d; do i=1 to 4; if mod(i,2)=0 then y=lag(i); else y=lag(i); output; end; run;'
        rows=execute(source)['datasets']['d']['rows']
        self.assertEqual([r['y'] for r in rows],[None,None,1.,2.])

    def test_output_snapshots_do_not_advance_queues(self):
        source='data d; set raw; y=lag(x); output; output; run;'
        rows=execute(source,inputs([10,20,30]))['datasets']['d']['rows']
        self.assertEqual([r['y'] for r in rows],[None,None,10.,10.,20.,20.])

    def test_where_and_subsetting_timing(self):
        data=inputs([10,20,30,40],[0,1,0,1])
        sources=['data d; set raw; where flag=1; y=lag(x); run;',
                 'data d; set raw; if flag; y=lag(x); run;',
                 'data d; set raw; y=lag(x); if flag; run;']
        values=[[r['y'] for r in execute(source,data)['datasets']['d']['rows']] for source in sources]
        self.assertEqual(values,[[None,20.],[None,20.],[10.,30.]])

    def test_by_boundary_does_not_reset_queue_and_masking_does_not_flush(self):
        data=inputs([10,20,30,40],keys=[1,1,2,2])
        source='data d; set raw; by key; y=lag(x); run;'
        rows=execute(source,data)['datasets']['d']['rows']
        self.assertEqual([r['y'] for r in rows],[None,10.,20.,30.])
        rows=execute(source.replace(' run;',' if first.key then y=.; run;'),data)['datasets']['d']['rows']
        self.assertEqual([r['y'] for r in rows],[None,10.,None,30.])

    def test_each_step_and_each_run_starts_fresh(self):
        source='data a; set raw; y=lag(x); run; data b; set a; z=lag(x); run;'
        p=compile_plan(source).to_dict();before=deepcopy(p);data=inputs([10,20,30]);original=deepcopy(data)
        first=run_plan(p,data);second=run_plan(p,data)
        self.assertEqual(first,second);self.assertEqual(p,before);self.assertEqual(data,original)
        self.assertEqual([r['y'] for r in first['datasets']['a']['rows']],[None,10.,20.])
        self.assertEqual([r['z'] for r in first['datasets']['b']['rows']],[None,10.,20.])

    def test_numeric_ordinary_missing_and_n_arguments(self):
        rows=execute('data d; set raw; a=lag(7); b=lag(.); c=lag(_n_); run;',inputs([1,2,3]))['datasets']['d']['rows']
        self.assertEqual([r['a'] for r in rows],[None,7.,7.])
        self.assertEqual([r['b'] for r in rows],[None,None,None])
        self.assertEqual([r['c'] for r in rows],[None,1.,2.])
        result=execute('data d; lag=7; dif1=9; x=lag; y=dif1; run;')
        self.assertEqual(result['datasets']['d']['rows'],[{'lag':7.,'dif1':9.,'x':7.,'y':9.}])

    def test_empty_filtered_and_zero_trip_descriptors(self):
        for rows,predicate in (([],''),([{'x':10.}],'where 0;')):
            data={'raw':{'schema':{'x':'number'},'rows':rows}}
            table=execute('data d; set raw; '+predicate+' y=lag100(x); run;',data)['datasets']['d']
            self.assertEqual(table['schema'],{'x':'number','y':'number'});self.assertEqual(table['rows'],[])
        result=execute('data d; do i=2 to 1; y=lag100(i); end; run;')
        self.assertEqual(result['datasets']['d']['rows'],[{'i':2.,'y':None}])
        for source,data in [('data d; length x $2; do i=2 to 1; y=lag(x); end; run;',{}),
                            ('data d; set raw; where 0; if 0 then y=lag(x); run;',{'raw':{'schema':{'x':{'type':'character','length':2}},'rows':[]}})]:
            with self.subTest(source=source),self.assertRaisesRegex(ValueError,'LAG/DIF'):execute(source,data)

    def test_literal_type_and_reserved_arguments_refuse_even_when_skipped(self):
        for argument in ("'7'",'.A','_error_','_infile_','_file_','_ods_','_page_','_blankpage_',
                         '_all_','_numeric_','_character_','first.key','last.key','x+1','sum(x,1)','lag(x)'):
            source='data d; do i=2 to 1; if 0 then y=lag('+argument+'); end; run;'
            self.assertTrue(compile_plan(source).blocked,argument)
        p=compile_plan('data d; set raw; if 0 then y=lag(1); run;').to_dict()
        arg=p['steps'][0]['operations'][1]['args']['operation']['args']['value']['args'][0]
        for value in (float('inf'),float('nan'),True,10**400):
            arg.update({'kind':'number','value':value})
            with self.subTest(value=repr(value)[:30]),self.assertRaisesRegex(ValueError,'LAG/DIF'):
                run_plan(p,inputs([]))

    def test_temporary_predicate_where_and_put_all_contexts_refuse(self):
        for source in ('data d; x=lag(1)+1; run;', 'data d; x=sum(lag(1),2); run;',
                       'data d; if lag(1) then x=7; run;', 'data d; set raw; where lag(x)=1; run;',
                       'data d; x=lag(1); put _all_; run;', 'data d; x=dif2(1); put _all_; run;'):
            p=compile_plan(source);self.assertTrue(p.blocked,source)
            p=p.to_dict();p['tickets']=[];p['matched']=[]
            with self.subTest(source=source),self.assertRaisesRegex(ValueError,'LAG/DIF'):
                run_plan(p,inputs([1,2]),allow_partial=True)
        for name in ('lag','lag100','dif2'):
            with self.assertRaisesRegex(ValueError,'scoped'):apply(name,[1.])
        with self.assertRaisesRegex(ValueError,'scoped'):
            number({'kind':'call','name':'lag','args':[{'kind':'number','value':1.}]},{})

    def test_malformed_direct_call_arguments_are_explicit_refusals(self):
        for args in ([],None,[None],[{'kind':'number','value':1.}]*2):
            with self.subTest(args=args),self.assertRaisesRegex(ValueError,'LAG/DIF'):
                validate_lag_calls({'kind':'call','name':'lag','args':args},direct=True)

    def test_skipped_invalid_dynamic_value_is_not_invoked(self):
        data=inputs([{'missing':'A'}],[0])
        result=execute('data d; set raw; if flag then y=lag(x); run;',data)
        self.assertIsNone(result['datasets']['d']['rows'][0]['y'])

    def test_late_tagged_value_and_dif_overflow_fail_atomically(self):
        for expression,values in [('lag(x)',[10.,{'missing':'A'}]),('dif(x)',[1e308,-1e308])]:
            source="data prior; put 'earlier'; run; data d; set raw; y="+expression+"; put 'row'; output; run;"
            data=inputs(values);translated=translate(source);self.assertFalse(translated.blocked,translated.tickets)
            printed=io.StringIO();ns={'inputs':data}
            with contextlib.redirect_stdout(printed),self.assertRaises(ValueError):exec(translated.code,ns)
            self.assertEqual(printed.getvalue(),'');self.assertNotIn('result',ns)
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'input.json';path.write_text(json.dumps(data))
                job=build_job(source,path)
            self.assertEqual(job.code,1);self.assertIsNone(job.result);self.assertFalse(job.receipt['accepted'])

    def test_handwritten_non_data_scope_is_refused(self):
        p=compile_plan('data d; x=lag(1); run;').to_dict()
        for kind in ('sort','sql','unknown'):
            p['steps'][0]['kind']=kind
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'DATA-step'):
                run_plan(p,allow_partial=True)

    def test_cpp_refusal_and_source_arity(self):
        for expression in ('lag(1)','dif100(1)'):
            job=build_job('data _null_; x='+expression+'; run;',target='cpp')
            self.assertEqual(job.code,2);self.assertIsNone(job.result)
        for expression in ('lag()','lag(1,2)','dif(1,2)'):
            self.assertTrue(compile_plan('data d; x='+expression+'; run;').blocked)


if __name__=='__main__':unittest.main()
