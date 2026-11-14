"""Sorted numeric BY input and temporary read-only FIRST/LAST flags."""
from copy import deepcopy
import unittest
from examples.verify_stateful_groups import GATE
from .expression_test_support import ExpressionContract
from .test_stateful_decisions import execute,table
from .plan import compile_plan
from .runtime import run_plan


class StatefulGroupTests(ExpressionContract,unittest.TestCase):
    gate=GATE;phase='ordered-by-groups';rule='DS-126'

    def test_missing_first_ties_singletons_and_temporary_flags(self):
        source='data d;set raw;by batch;f=first.batch;l=last.batch;total+abs(a);output;run;'
        inputs=table([{'a':1,'batch':None},{'a':2,'batch':None},{'a':3,'batch':0.5},{'a':4,'batch':2},{'a':5,'batch':2}],{'a':'number','batch':'number'})
        result=execute(source,inputs)['datasets']['d']
        self.assertEqual([(r['f'],r['l']) for r in result['rows']],[(1,0),(0,1),(1,1),(1,0),(0,1)])
        self.assertEqual([r['total'] for r in result['rows']],[1,3,6,10,15])
        self.assertEqual(list(result['schema']),['a','batch','f','l','total'])
        self.assertTrue(all(set(r)==set(result['schema']) for r in result['rows']))

    def test_explicit_group_reset_versus_unreset_global_state(self):
        source='data d;retain peak 0;set raw;by batch;if first.batch then do;peak=0;total=0;end;total+abs(a);global+abs(a);peak=max(peak,abs(a));if last.batch then output;run;'
        inputs=table([{'a':-3,'batch':1},{'a':2,'batch':1},{'a':1,'batch':2}],{'a':'number','batch':'number'})
        rows=execute(source,inputs)['datasets']['d']['rows']
        self.assertEqual([(r['total'],r['global'],r['peak']) for r in rows],[(5,5,3),(1,6,1)])

    def test_boolean_auto_predicates_and_both_singleton_snapshots(self):
        source="data d;length phase $8;set raw;by batch;if first.batch and n(a)<1 then do;phase='FIRST';output;end;if last.batch then do;phase=ifc(first.batch,'SINGLE','MULTI');output;end;run;"
        inputs=table([{'a':None,'batch':1}],{'a':'number','batch':'number'})
        self.assertEqual([r['phase'] for r in execute(source,inputs)['datasets']['d']['rows']],['FIRST   ','SINGLE  '])

    def test_order_and_key_domains_refuse_before_any_body(self):
        source="data d;set raw;by batch;x=abs(a);output;put 'kept';run;"
        for keys in ([1,0],[1,None],[None,2,1],[0,1000001],[0,float('inf')]):
            inputs=table([{'a':1,'batch':key} for key in keys],{'a':'number','batch':'number'})
            with self.subTest(keys=keys),self.assertRaises(ValueError):execute(source,inputs)
        self.atomic_cli(source,table([{'a':1,'batch':1},{'a':2,'batch':0}],{'a':'number','batch':'number'}),'sorted')
        with self.assertRaises(ValueError):execute(source,table([],{'a':'number','batch':{'type':'character','length':8}}))
        with self.assertRaises(ValueError):execute(source,table([]))

    def test_no_sorting_and_input_metadata_are_preserved(self):
        source='data d;set raw;by batch;f=first.batch;x=abs(a);output;run;'
        inputs=table([{'a':3,'batch':1},{'a':1,'batch':1},{'a':2,'batch':2}],{'a':'number','batch':'number'})
        inputs['raw']['label']='Stable ties';saved=deepcopy(inputs)
        result=execute(source,inputs)['datasets']['d']
        self.assertEqual([r['a'] for r in result['rows']],[3,1,2])
        self.assertEqual(result['label'],'Stable ties');self.assertEqual(inputs,saved)

    def test_by_source_shape_and_automatic_assignment_refusals(self):
        forms=[
            'data d;set raw;by batch a;do;x=abs(a);end;run;',
            'data d;set raw;by descending batch;do;x=abs(a);end;run;',
            'data d;set raw;by batch notsorted;do;x=abs(a);end;run;',
            'data d;set raw;by batch;by batch;do;x=abs(a);end;run;',
            'data d;set raw;by batch;if first.other then do;x=abs(a);end;run;',
            'data d;set raw;if first.batch then do;x=abs(a);end;run;',
            'data d;set raw;by batch;first.batch=0;x=abs(a);output;run;',
            'data d;set raw;by batch;last.batch+1;x=abs(a);output;run;',
        ]
        for source in forms:
            with self.subTest(source=source):self.assertTrue(compile_plan(source).blocked)

    def test_auto_leaf_and_by_portable_fields_are_exact(self):
        source='data d;set raw;by batch;f=first.batch;x=abs(a);output;run;'
        p=compile_plan(source).to_dict();bad=[]
        for by in (['batch','a'],[True],['Batch'],[],['unknown']):
            q=deepcopy(p);q['steps'][0]['by']=by;bad.append(q)
        from .stateful_expressions import walk_ops
        for mutation in ('key','flag','extra'):
            q=deepcopy(p);op=next(o for o in walk_ops(q['steps'][0]['operations']) if o['kind']=='assign' and o['args']['name']=='f');node=op['args']['value']
            if mutation=='key':node['key']='other'
            elif mutation=='flag':node['flag']='middle'
            else:node['extra']=1
            bad.append(q)
        for q in bad:
            with self.subTest(index=bad.index(q)),self.assertRaises(ValueError):run_plan(q,table([],{'a':'number','batch':'number'}))

    def test_prior_three_stage_boundaries_are_retained(self):
        from . import stateful_expressions as sx
        for stage in (1,2,3):
            with self.subTest(stage=stage),self.assertRaises(ValueError):sx.validate_step(self.original()['steps'][0],max_stage=stage)

    def test_auto_names_do_not_capture_ordinary_columns_or_quoted_text(self):
        source="data d;length text $24;set raw;by batch;first=7;_sx0=9;f=first.batch;last=3;l=last.batch;text=ifc(first.batch,'first.batch','last.batch');output;run;"
        rows=execute(source,table([{'a':1,'batch':1}],{'a':'number','batch':'number'}))['datasets']['d']['rows']
        self.assertEqual([(r['first'],r['_sx0'],r['last'],r['f'],r['l']) for r in rows],[(7,9,3,1,1)])
        self.assertEqual(rows[0]['text'],'first.batch'.ljust(24))

    def test_nested_inline_auto_predicates_and_actions_keep_their_own_keys(self):
        source='data d;set raw;by batch;if first.batch then if last.batch then do;f=last.batch;x=abs(a);output;end;run;'
        inputs=table([{'a':2,'batch':1},{'a':3,'batch':2},{'a':4,'batch':2}],{'a':'number','batch':'number'})
        rows=execute(source,inputs)['datasets']['d']['rows']
        self.assertEqual([(r['batch'],r['f'],r['x']) for r in rows],[(1,1,2)])

    def test_automatic_numeric_leaves_need_no_scalar_call_or_stored_flag_columns(self):
        source='data d;set raw;by a;first_flag=first.a;last_flag=last.a;run;'
        rows=execute(source,table([{'a':1},{'a':1},{'a':2}]))['datasets']['d']['rows']
        self.assertEqual(rows,[{'a':1.,'first_flag':1.,'last_flag':0.},{'a':1.,'first_flag':0.,'last_flag':1.},{'a':2.,'first_flag':1.,'last_flag':1.}])

    def test_malformed_variable_values_refuse_as_validation_errors(self):
        source='data d;set raw;by batch;f=first.batch;x=abs(a);output;run;'
        p=compile_plan(source).to_dict()
        from .stateful_expressions import walk_ops
        for value in ([],{},True,None):
            q=deepcopy(p);op=next(o for o in walk_ops(q['steps'][0]['operations']) if o['kind']=='assign' and o['args']['name']=='x')
            op['args']['value']={'kind':'variable','value':value}
            with self.subTest(value=value),self.assertRaises(ValueError):run_plan(q,table([],{'a':'number','batch':'number'}))
