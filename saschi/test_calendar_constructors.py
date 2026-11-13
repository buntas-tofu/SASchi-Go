"""Supplied civil components and strict seven-digit ordinal dates."""
import unittest
from examples.verify_calendar_constructors import GATE,REFUSALS
from .wave3_test_support import FamilyContract
from .test_do_counted import execute,job_with_inputs
from .job import build_job
import sas_semantics as sem

class CalendarConstructorTests(FamilyContract,unittest.TestCase):
    gate=GATE;refusals=REFUSALS
    names=('hms','yyq','datejul','juldate7');family='calendar-constructors';rule='DS-114'

    def test_epoch_pre_epoch_and_four_digit_quarters(self):
        self.assertEqual(sem.sas_hms(23,59,59),86399)
        self.assertEqual(sem.sas_yyq(1960,1),0)
        self.assertEqual(sem.sas_yyq(1959,4),-92)
        self.assertEqual(sem.sas_juldate7(-1),1959365)
        for year in [0,24,99,100,1752,4000]:
            with self.assertRaises(ValueError):sem.sas_yyq(year,1)

    def test_leap_day_and_century_validation(self):
        self.assertEqual(sem.sas_datejul(2000060),14669)
        self.assertEqual(sem.sas_juldate7(14669),2000060)
        for value in [1900366,2023366,2024000,2024367,24001]:
            with self.assertRaises(ValueError):sem.sas_datejul(value)
        for value in [1753001,1960001,2000366,2024366,3999365]:
            self.assertEqual(sem.sas_juldate7(sem.sas_datejul(value)),value)

    def test_missing_propagates_after_all_component_checks(self):
        self.assertIsNone(sem.sas_hms(None,0,0))
        self.assertIsNone(sem.sas_yyq(None,1))
        self.assertIsNone(sem.sas_datejul(None))
        self.assertIsNone(sem.sas_juldate7(None))
        with self.assertRaises(ValueError):sem.sas_hms(None,60,0)
        with self.assertRaises(ValueError):sem.sas_yyq(None,5)

    def test_empty_descriptors_and_skipped_literal_validation(self):
        source='data d;set raw;if 0 then x=datejul(value);run;'
        self.assertEqual(job_with_inputs(source,{'raw':{'schema':{'value':{'type':'character','length':7}},'rows':[]}}).code,1)
        for rhs in ['datejul(2023366)','yyq(24,1)','hms(0,60,0)','juldate7(.5)']:
            self.assertEqual(build_job('data d;if 0 then x='+rhs+';run;').code,2)

    def test_late_invalid_ordinal_is_atomic(self):
        inputs={'raw':{'schema':{'value':'number'},'rows':[{'value':2024001},{'value':2023366}]}}
        self.atomic_cli('data d;set raw;x=datejul(value);output;put x;run;',inputs,'ordinal')

    def test_fractional_normalized_clock_and_cutoff_forms_stay_held(self):
        for rhs in ['hms(24,0,0)','hms(0,0,.5)','datejul(24001)','juldate(0)','today()','datetime()']:
            self.assertIn(build_job('data d;x='+rhs+';run;').code,(1,2))

if __name__=='__main__':unittest.main()
