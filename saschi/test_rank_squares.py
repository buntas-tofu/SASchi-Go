"""Rank error states and exact integral sums of squares."""
import unittest
from examples.verify_rank_squares import GATE,REFUSALS
from .wave3_test_support import FamilyContract
from .test_do_counted import execute,job_with_inputs
from .job import build_job
import sas_semantics as sem

class RankSquaresTests(FamilyContract,unittest.TestCase):
    gate=GATE;refusals=REFUSALS
    names=('largest','smallest','css','uss');family='ranks-and-sums-of-squares';rule='DS-112'

    def test_valid_rank_exceeding_nonmissing_count_is_missing(self):
        self.assertIsNone(sem.sas_largest(3,None,5,None))
        self.assertIsNone(sem.sas_smallest(2,5,None))
        for k in [0,-1,None,.5,4]:
            with self.assertRaises(ValueError):sem.sas_largest(k,1,2,3)
        self.assertEqual(sem.sas_largest(2,3,3,1),3)
        self.assertEqual(sem.sas_smallest(2,3,3,1),3)

    def test_centered_sum_avoids_high_offset_cancellation(self):
        self.assertEqual(sem.sas_css(999998,999999,1000000),2)
        self.assertEqual(sem.sas_css(-1,0,1),2)
        self.assertEqual(sem.sas_uss(999998,999999,1000000),2999994000005)
        self.assertEqual(sem.sas_css(0,1,1),2/3)
        self.assertEqual(sem.sas_css(999999,1000000,1000000),2/3)
        self.assertEqual(build_job('data d;x=css(0,1,1);put x;run;').code,1)
        self.assertEqual(sem.sas_css(*range(32)),2728)

    def test_singletons_all_missing_and_all_arguments_validate(self):
        self.assertEqual(sem.sas_css(-4,None),0)
        self.assertEqual(sem.sas_uss(-4,None),16)
        self.assertIsNone(sem.sas_css(None,None))
        self.assertIsNone(sem.sas_uss(None))
        with self.assertRaises(ValueError):sem.sas_largest(1,5,True)
        with self.assertRaises(ValueError):sem.sas_css(None,.5)

    def test_empty_descriptors_and_skipped_bad_literals(self):
        source='data d;set raw;if 0 then x=css(a,b);run;'
        inputs={'raw':{'schema':{'a':'number','b':{'type':'character','length':2}},'rows':[]}}
        self.assertEqual(job_with_inputs(source,inputs).code,1)
        for rhs in ['largest(0,1,2)','smallest(3,1,2)','css(.5)','uss(.A)']:
            self.assertEqual(build_job('data d;if 0 then x='+rhs+';run;').code,2)

    def test_late_invalid_rank_is_atomic(self):
        inputs={'raw':{'schema':{'k':'number','a':'number','b':'number'},'rows':[{'k':1,'a':3,'b':1},{'k':3,'a':3,'b':1}]}}
        self.atomic_cli('data d;set raw;x=largest(k,a,b);output;put x;run;',inputs,'rank')

    def test_skipped_dynamic_rank_and_held_contexts(self):
        inputs={'raw':{'schema':{'k':'number'},'rows':[{'k':0}]}}
        result,_=execute('data d;set raw;if 0 then x=largest(k,1,2);run;',inputs)
        self.assertIsNone(result['datasets']['d']['rows'][0]['x'])
        for source in ["data d;x=css(largest(1,2,3));run;","data d;x=largest(1,1,2);put largest(1,1,2);run;"]:
            self.assertIn(build_job(source).code,(1,2))

if __name__=='__main__':unittest.main()
