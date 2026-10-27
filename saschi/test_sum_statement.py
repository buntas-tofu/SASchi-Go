"""DS-034 source accumulation evidence for maintainer review, no live SAS."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from sas_semantics import sas_sum_statement
from .job import build_job
from .plan import compile_plan
from .rules import route_statement
from .runtime import run_plan
from .test_do_counted import execute, job_with_inputs


def raw(values, spec='number'):
    return {'raw': {'schema': {'x': spec}, 'rows': [{'x': x} for x in values]}}


class SumStatementTests(unittest.TestCase):
    def test_routing_and_rule_match(self):
        self.assertEqual(route_statement('TOTAL + x'), ('sum-statement', 'DS-034'))
        self.assertIn(('sum-statement', 'DS-034', 1), compile_plan('data d; total+1; run;').matched)

    def test_implicit_zero_and_cross_row_retention(self):
        result, _ = execute('data d; set raw; total+x; run;', raw([2, None, -1, .5]))
        self.assertEqual([r['total'] for r in result['datasets']['d']['rows']], [2, 2, 1, 1.5])

    def test_explicit_retain_before_or_after(self):
        for body in ('retain total 7; total+x;', 'total+x; retain total 7;'):
            rows = execute('data d; set raw; '+body+' run;', raw([None, 3]))[0]['datasets']['d']['rows']
            self.assertEqual([r['total'] for r in rows], [7, 10])

    def test_missing_current_and_increment(self):
        rows = execute('data d; set raw; total=.; total+x; run;', raw([None, 2]))[0]['datasets']['d']['rows']
        self.assertEqual([r['total'] for r in rows], [0, 2])

    def test_unselected_sum_still_initializes_and_retains(self):
        rows = execute('data d; set raw; if x>1 then n+1; run;', raw([0, 2, 0]))[0]['datasets']['d']['rows']
        self.assertEqual([r['n'] for r in rows], [0, 1, 1])

    def test_by_groups_require_explicit_reset(self):
        inputs={'raw':{'schema':{'k':'number','x':'number'},'rows':[
            {'k':1,'x':2},{'k':1,'x':None},{'k':2,'x':3}]}}
        for prefix, expected in (('',[2,2,5]),('if first.k then total=0;',[2,2,3])):
            rows=execute('data d; set raw; by k; '+prefix+' total+x; run;',inputs)[0]['datasets']['d']['rows']
            self.assertEqual([r['total'] for r in rows],expected)

    def test_counted_and_conditional_composition(self):
        rows=execute('data d; do i=1 to 3; if i=2 then total+.; else total+i; output; end; run;')[0]['datasets']['d']['rows']
        self.assertEqual([r['total'] for r in rows],[1,1,4])

    def test_counted_index_writes_refuse_in_all_branches(self):
        for body in ('i+1;', 'if 0 then i+1;', 'if 1 then x=0; else i+1;'):
            self.assertTrue(compile_plan('data d; do i=1 to 2; '+body+' end; run;').blocked)

    def test_schema_target_precedes_rhs_discovery(self):
        table=execute('data d; total+x; after=1; run;')[0]['datasets']['d']
        self.assertEqual(list(table['schema']),['total','x','after'])
        self.assertEqual(table['rows'],[{'total':0.,'x':None,'after':1.}])

    def test_input_metadata_survives(self):
        inputs=raw([3],{'type':'number','label':'increment'})
        table=execute('data d; set raw; total+x; run;',inputs)[0]['datasets']['d']
        self.assertEqual(table['schema']['x'],inputs['raw']['schema']['x'])
        self.assertEqual(list(table['schema']),['x','total'])

    def test_empty_and_filtered_inputs_keep_static_schema(self):
        for values, where in (([],''),([2],'where 0;')):
            table=execute('data d; set raw; '+where+' total+x; run;',raw(values))[0]['datasets']['d']
            self.assertEqual(table,{'schema':{'x':'number','total':'number'},'rows':[]})

    def test_dynamic_calls_are_lazy(self):
        table=execute('data d; set raw; if 0 then total+mod(x,0); run;',raw([1]))[0]['datasets']['d']
        self.assertEqual(table['rows'],[{'x':1.,'total':0.}])

    def test_static_types_and_literals_refuse_even_when_skipped(self):
        for body in ('if 0 then total+"1";', 'if 0 then total+.A;', 'if 0 then total+1e309;'):
            job=build_job('data d; '+body+' run;')
            self.assertNotEqual(job.code,0); self.assertIsNone(job.result)
        for rows in ([],['1']):
            job=job_with_inputs('data d; set raw; if 0 then total+x; run;',raw(rows,{'type':'character','length':1}))
            self.assertEqual(job.code,1); self.assertIsNone(job.result)
        job=job_with_inputs('data d; retain total 1e309; set raw; total+x; run;',raw([]))
        self.assertEqual(job.code,2); self.assertIsNone(job.result)
        plan=compile_plan('data d; retain total 0; set raw; total+x; run;').to_dict()
        plan['steps'][0]['retained']['total']['value']=float('inf')
        with self.assertRaises(ValueError): run_plan(plan,raw([]),allow_partial=True)

    def test_late_tag_and_overflow_are_atomic(self):
        for values in ([1,{'missing':'A'}],[1e308,1e308]):
            job=job_with_inputs('data prior; put "earlier"; run; data d; set raw; total+x; put "row"; run;',raw(values))
            self.assertEqual(job.code,1); self.assertIsNone(job.result)
            self.assertFalse(job.receipt['accepted'])
        # Tagged operands cannot disappear inside missing-propagating arithmetic.
        job=job_with_inputs('data d; set raw; total+x+1; run;',raw([{'missing':'A'}]))
        self.assertEqual(job.code,1); self.assertIsNone(job.result)

    def test_step_and_run_isolation(self):
        source='data d; n+1; run; data e; n+1; run;'
        first=execute(source)[0]; second=execute(source)[0]
        self.assertEqual(first,second)
        self.assertEqual(first['datasets']['e']['rows'],[{'n':1.}])

    def test_forged_plan_cannot_remove_implicit_retention(self):
        plan=compile_plan('data d; set raw; n+1; run;').to_dict()
        plan['steps'][0]['retained']={}
        snapshot=deepcopy(plan)
        rows=run_plan(plan,raw([0,0]))['datasets']['d']['rows']
        self.assertEqual([r['n'] for r in rows],[1,2]); self.assertEqual(plan,snapshot)

    def test_forged_shapes_targets_and_by_writes_refuse(self):
        original=compile_plan('data d; n+1; run;').to_dict()
        for args in ({'name':'_n_','value':{'kind':'number','value':1}},
                     {'name':'n','value':{'kind':'number','value':True}},
                     {'name':'n','value':None}, {'name':'n','value':{'kind':'number','value':1},'extra':0}):
            plan=deepcopy(original); plan['steps'][0]['operations'][0]['args']=args
            with self.assertRaises(ValueError): run_plan(plan,allow_partial=True)
        self.assertTrue(compile_plan('data d; set raw; by x; x+1; run;').blocked)
        self.assertTrue(compile_plan('data d; merge a b; by k; n+1; run;').blocked)

    def test_cpp_lag_and_put_all_boundaries(self):
        for source,target in (('data _null_; n+1; run;','cpp'),
                              ('data d; n+lag(1); run;','python'),
                              ('data _null_; n+1; put _all_; run;','python')):
            job=build_job(source,target=target)
            self.assertNotEqual(job.code,0); self.assertIsNone(job.result)

    def test_receipt_comparator_controls_preserve_observed_output(self):
        source='data d; n+1; output; n+2; output; run;'
        actual=execute(source)[0]['datasets']['d']
        changes=[]
        table=deepcopy(actual); table['rows'][0]['n']=9; changes.append(table)
        table=deepcopy(actual); table['rows'].reverse(); changes.append(table)
        table=deepcopy(actual); table['schema']['n']={'type':'number','label':'changed'}; changes.append(table)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'expected.json'; path.write_text(json.dumps({'d':actual}))
            self.assertTrue(build_job(source,expect=path).receipt['accepted'])
            for changed in changes:
                path.write_text(json.dumps({'d':changed})); job=build_job(source,expect=path)
                self.assertEqual(job.code,1); self.assertEqual(job.receipt['comparison'],'failed')
                self.assertEqual(job.result['datasets']['d'],actual)

    def test_helper_finite_ordinary_missing_contract(self):
        self.assertEqual(sas_sum_statement(None,None),0.)
        for value in (True,'2',{'missing':'A'},float('inf'),10**400):
            with self.assertRaises(ValueError): sas_sum_statement(value,1)
        with self.assertRaises(ValueError): sas_sum_statement(1e308,1e308)


if __name__=='__main__': unittest.main()
