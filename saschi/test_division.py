"""DS-036 source numeric composition evidence, repository/base R only."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from sas_semantics import sas_divide
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .test_do_counted import execute,job_with_inputs
from .test_sum_statement import raw


class DivisionTests(unittest.TestCase):
    def row(self,expression):
        return execute('data d; x='+expression+'; run;')[0]['datasets']['d']['rows'][0]['x']

    def test_rule_match_and_numeric_fraction(self):
        self.assertEqual(self.row('-7/2'),-3.5)
        self.assertIn(('division','DS-036',1),compile_plan('data d; x=9/2; run;').matched)

    def test_fractional_operands_and_cancelled_odd_denominator(self):
        for text,want in (('.5/2',.25),('3/1.5',2.),('6/3',2.),('-7/-2',3.5)):
            self.assertEqual(self.row(text),want)

    def test_division_precedence_over_addition_and_subtraction(self):
        for text,want in (('2+8/2',6.),('8/2+1',5.),('9-8/2',5.),('8/2-1',3.)):
            self.assertEqual(self.row(text),want)

    def test_left_associative_division_and_subtraction(self):
        self.assertEqual(self.row('20/2/5'),2.)
        self.assertEqual(self.row('20-8-2/2'),11.)

    def test_grouping_and_call_arguments(self):
        for text,want in (('20/(2+3)',4.),('(8+4)/2',6.),('8/(5-3)-1',3.),('mod(8/2,3)',1.)):
            self.assertEqual(self.row(text),want)

    def test_exponent_signs_names_and_quoted_operators(self):
        self.assertEqual(self.row('1e-3/2'),.0005)
        row=execute("data d; a1e=8; x=a1e-2/2; text='1e-3/2'; run;")[0]['datasets']['d']['rows'][0]
        self.assertEqual((row['x'],row['text']),(7.,'1e-3/2'))

    def test_exact_range_and_subnormal_boundary(self):
        self.assertEqual(self.row('2147483647/1'),2147483647.)
        self.assertEqual(self.row('1e-323/2'),5e-324)
        for expr in ('2147483648/1','2147483647/.5','5e-324/2','1/3'):
            job=build_job('data d; x='+expr+'; run;')
            self.assertEqual(job.code,1); self.assertIsNone(job.result)

    def test_set_metadata_and_schema_order(self):
        inputs=raw([2,4],{'type':'number','label':'source'})
        table=execute('data d; set raw; ratio=x/2; run;',inputs)[0]['datasets']['d']
        self.assertEqual(list(table['schema']),['x','ratio'])
        self.assertEqual(table['schema']['x'],inputs['raw']['schema']['x'])
        self.assertEqual([r['ratio'] for r in table['rows']],[1.,2.])

    def test_where_and_if_numeric_composition(self):
        source='data d; set raw; where x/2>1; if x/2+1=3 then code=1; else code=0; run;'
        rows=execute(source,raw([2,4]))[0]['datasets']['d']['rows']
        self.assertEqual(rows,[{'x':4.,'code':1.}])

    def test_sum_counted_and_until_composition(self):
        row=execute('data d; do i=1 to 3; total+i/2; end; run;')[0]['datasets']['d']['rows'][0]
        self.assertEqual((row['i'],row['total']),(4.,3.))
        row=execute('data d; do until(n/2=2); n+2; end; run;')[0]['datasets']['d']['rows'][0]
        self.assertEqual(row['n'],4.)

    def test_invalid_constants_refuse_on_skipped_and_zero_trip_paths(self):
        for expr in ('1/0','1/3','./2','.A/2','"2"/2'):
            for body in ('if 0 then y='+expr+';', 'do while(0); y='+expr+'; end;'):
                job=build_job('data d; '+body+' run;')
                self.assertNotEqual(job.code,0); self.assertIsNone(job.result)

    def test_empty_character_input_is_statically_refused(self):
        for body in ('y=x/2;','if 0 then y=x/2;','do while(x/2); end;'):
            job=job_with_inputs('data d; set raw; '+body+' run;',raw([],{'type':'character','length':1}))
            self.assertEqual(job.code,1); self.assertIsNone(job.result)

    def test_dynamic_calls_are_lazy_and_filtered(self):
        table=execute('data d; set raw; if 0 then y=1/x; run;',raw([0]))[0]['datasets']['d']
        self.assertEqual(table['rows'],[{'x':0.,'y':None}])
        table=execute('data d; set raw; where x>0; y=1/x; run;',raw([0,2]))[0]['datasets']['d']
        self.assertEqual(table['rows'],[{'x':2.,'y':.5}])

    def test_late_dynamic_errors_are_atomic(self):
        for values in ([2,3],[2,None],[2,{'missing':'A'}],[2,0]):
            job=job_with_inputs('data prior; put "earlier"; run; data d; set raw; y=1/x; put "row"; run;',raw(values))
            self.assertEqual(job.code,1); self.assertFalse(job.receipt['accepted']); self.assertIsNone(job.result)

    def test_forged_operators_and_complexity_cannot_bypass_guards(self):
        original=compile_plan('data d; y=8/2; run;').to_dict()
        product=deepcopy(original);product['steps'][0]['operations'][0]['args']['value']['op']='*'
        self.assertEqual(run_plan(product)['datasets']['d']['rows'],[{'y':16.}])
        for op in ('^','unknown'):
            plan=deepcopy(original);plan['steps'][0]['operations'][0]['args']['value']['op']=op
            with self.assertRaises(ValueError):run_plan(plan,allow_partial=True)
        self.assertTrue(compile_plan('data d; '+''.join('x=8/2;' for _ in range(129))+' run;').blocked)
        p=deepcopy(original);p['steps'][0]['operations']*=129
        with self.assertRaisesRegex(ValueError,'128'):run_plan(p,allow_partial=True)
        self.assertTrue(compile_plan('data d; x='+'('*34+'8/2'+')'*34+'; run;').blocked)
        product,stdout=execute('data d; x=2*y; run;')
        self.assertEqual(product,{'datasets':{'d':{'schema':{'x':'number','y':'number'},
                         'rows':[{'x':None,'y':None}]}},'log':[]})
        self.assertEqual(stdout,'')
        for expr in ('-y/2','8//2'):
            self.assertTrue(compile_plan('data d; x='+expr+'; run;').blocked)
        # A new numeric step must not quarantine a separate legacy step.
        source='data prior; '+''.join('x=mod(8,3);' for _ in range(129))+' run; data d; y=8/2; run;'
        result=execute(source)[0]
        self.assertEqual(result['datasets']['prior']['rows'],[{'x':2.}])
        self.assertEqual(result['datasets']['d']['rows'],[{'y':4.}])

    def test_comparator_controls_and_legacy_target_boundaries(self):
        source='data d; x=8/2; y=x+1; run;'
        actual=execute(source)[0]['datasets']['d']; changes=[]
        t=deepcopy(actual);t['rows'][0]['x']=5.;changes.append(t)
        t=deepcopy(actual);t['schema']={'y':'number','x':'number'};changes.append(t)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'expected.json';p.write_text(json.dumps({'d':actual}))
            self.assertTrue(build_job(source,expect=p).receipt['accepted'])
            for changed in changes:
                p.write_text(json.dumps({'d':changed}));job=build_job(source,expect=p)
                self.assertEqual(job.code,1);self.assertEqual(job.result['datasets']['d'],actual)
        for target,body in (('cpp','x=8/2;'),('python','x=8/2; put _all_;')):
            job=build_job('data _null_; '+body+' run;',target=target)
            self.assertNotEqual(job.code,0);self.assertIsNone(job.result)


if __name__=='__main__':unittest.main()
