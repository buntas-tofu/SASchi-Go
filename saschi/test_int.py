"""DS-037 safe INT source execution, repository/base-R evidence only."""
from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import unittest

from sas_semantics import sas_int
from .functions import FUNCTIONS
from .job import build_job
from .plan import compile_plan
from .rules import route_function
from .runtime import run_plan
from .test_do_counted import execute,job_with_inputs
from .test_sum_statement import raw


class IntTests(unittest.TestCase):
    def test_registry_arity_routing_and_provenance(self):
        spec=FUNCTIONS['int']
        self.assertEqual((spec.min_args,spec.max_args,spec.returns,spec.gate),(1,1,'number','examples/verify_int.py'))
        self.assertEqual(route_function('x=INT(-2.7)'),('int','DS-037'))
        self.assertEqual(route_function("x='INT(-2.7)'"),('unknown',''))

    def test_truncation_toward_zero_for_both_signs(self):
        row=execute('data d; a=int(2.1); b=int(-2.4); c=int(-.5); d=int(1.999); run;')[0]['datasets']['d']['rows'][0]
        self.assertEqual(row,{'a':2.,'b':-2.,'c':0.,'d':1.})

    def test_near_integer_fuzz_band_is_explicitly_refused(self):
        for x in (math.nextafter(1,0),math.nextafter(1,2),1.9999999999995,-1.9999999999995,1e-13):
            with self.assertRaisesRegex(ValueError,'fuzz'):sas_int(x)
        self.assertEqual((sas_int(1-4e-12),sas_int(-1+4e-12)),(0,0))

    def test_exact_integer_and_magnitude_boundaries(self):
        for x in (0,1,-1,2147483647,-2147483647):self.assertEqual(sas_int(x),x)
        for x in (2147483648,-2147483648,True,None,{'missing':'A'},float('inf')):
            with self.assertRaises(ValueError):sas_int(x)

    def test_set_metadata_and_target_before_reference_schema(self):
        inputs=raw([2.5,-2.5],{'type':'number','label':'source'})
        table=execute('data d; set raw; y=int(x); run;',inputs)[0]['datasets']['d']
        self.assertEqual(table['schema']['x'],inputs['raw']['schema']['x'])
        self.assertEqual([r['y'] for r in table['rows']],[2.,-2.])

    def test_nested_numeric_calls_division_and_grouping(self):
        row=execute('data d; a=int(9/2); b=int(-7/2)+1; c=mod(int(9/2),3); d=int((8+1)/2); run;')[0]['datasets']['d']['rows'][0]
        self.assertEqual(row,{'a':4.,'b':-2.,'c':1.,'d':4.})

    def test_where_and_if_call_contexts(self):
        rows=execute('data d; set raw; where int(x)>0; if int(x)=2 then y=1; else y=0; run;',raw([-.5,2.5]))[0]['datasets']['d']['rows']
        self.assertEqual(rows,[{'x':2.5,'y':1.}])

    def test_sum_and_loop_composition(self):
        row=execute('data d; do i=1 to 3; total+int(i/2); end; run;')[0]['datasets']['d']['rows'][0]
        self.assertEqual((row['total'],row['i']),(2.,4.))

    def test_static_invalid_literals_on_skipped_and_empty_inputs(self):
        for expr in ('int(.)','int(.A)','int("2")','int(1.9999999999995)','int(2147483648)'):
            job=job_with_inputs('data d; set raw; if 0 then y='+expr+'; run;',raw([]))
            self.assertNotEqual(job.code,0);self.assertIsNone(job.result)
        job=job_with_inputs('data d; set raw; y=int(x); run;',raw([],{'type':'character','length':1}))
        self.assertEqual(job.code,1);self.assertIsNone(job.result)

    def test_unselected_dynamic_call_remains_lazy(self):
        table=execute('data d; set raw; if 0 then y=int(x); run;',raw([None]))[0]['datasets']['d']
        self.assertEqual(table['rows'],[{'x':None,'y':None}])

    def test_late_invalid_input_is_atomic(self):
        for values in ([2.5,None],[2.5,1.9999999999995],[2.5,{'missing':'A'}]):
            job=job_with_inputs('data prior; put "earlier"; run; data d; set raw; y=int(x); put "row"; run;',raw(values))
            self.assertEqual(job.code,1);self.assertFalse(job.receipt['accepted']);self.assertIsNone(job.result)

    def test_forged_call_cannot_bypass_arity_or_literals(self):
        original=compile_plan('data d; y=int(2.5); run;').to_dict()
        for args in ([],[{'kind':'number','value':True}], [{'kind':'number','value':1.9999999999995}],
                     [{'kind':'number','value':1},{'kind':'number','value':2}]):
            p=deepcopy(original);p['steps'][0]['operations'][0]['args']['value']['args']=args
            with self.assertRaises(ValueError):run_plan(p,allow_partial=True)

    def test_unwired_related_calls_and_legacy_targets_stay_refused(self):
        for expr in ('int()','int(1,2)','intz(2.5)','floor(2.5)'):
            self.assertTrue(compile_plan('data d; x='+expr+'; run;').blocked)
        for target,body in (('cpp','x=int(2.5);'),('python','x=int(2.5); put _all_;')):
            job=build_job('data _null_; '+body+' run;',target=target)
            self.assertNotEqual(job.code,0);self.assertIsNone(job.result)

    def test_comparator_controls_preserve_observed_values(self):
        source='data d; x=int(-2.4); run;'; actual=execute(source)[0]['datasets']['d']
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'expected.json';p.write_text(json.dumps({'d':actual}))
            self.assertTrue(build_job(source,expect=p).receipt['accepted'])
            changed=deepcopy(actual);changed['rows'][0]['x']=-3.;p.write_text(json.dumps({'d':changed}))
            job=build_job(source,expect=p);self.assertEqual(job.code,1)
            self.assertEqual(job.receipt['comparison'],'failed');self.assertEqual(job.result['datasets']['d'],actual)


if __name__=='__main__':unittest.main()
