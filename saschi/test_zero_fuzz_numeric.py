"""Zero-fuzz integer boundaries, exact half ties and signed remainders."""
import json,math,unittest
from examples.verify_zero_fuzz_numeric import GATE,REFUSALS
from .wave3_test_support import FamilyContract
from .test_do_counted import execute,job_with_inputs
from .job import build_job
import sas_semantics as sem

class ZeroFuzzNumericTests(FamilyContract,unittest.TestCase):
    gate=GATE;refusals=REFUSALS
    names=('ceilz','floorz','intz','roundz','modz');family='zero-fuzz-numeric';rule='DS-113'

    def test_integer_neighbors_are_not_fuzzed(self):
        self.assertEqual(sem.sas_ceilz(math.nextafter(1.,2.)),2)
        self.assertEqual(sem.sas_floorz(math.nextafter(1.,0.)),0)
        self.assertEqual(sem.sas_intz(math.nextafter(-1.,0.)),0)
        self.assertEqual(sem.sas_intz(math.nextafter(-1.,-2.)),-1)

    def test_exact_ties_even_and_neighbors_do_not_collapse(self):
        for tie,wanted in [(-3.5,-4),(-2.5,-2),(-.5,0),(.5,0),(2.5,2),(3.5,4)]:
            self.assertEqual(sem.sas_roundz(tie),wanted)
            self.assertEqual(sem.sas_roundz(math.nextafter(tie,-math.inf)),math.floor(tie))
            self.assertEqual(sem.sas_roundz(math.nextafter(tie,math.inf)),math.ceil(tie))
        self.assertEqual(sem.sas_roundz(.625,.25),.5)
        self.assertNotEqual(sem.sas_roundz(2.5),sem.sas_round(2.5,1))

    def test_remainder_uses_dividend_sign_and_preserves_small_nonzero_results(self):
        self.assertEqual(sem.sas_modz(-3.5,-2),-1.5)
        self.assertEqual(sem.sas_modz(3.5,-2),1.5)
        self.assertEqual(sem.sas_modz(math.nextafter(1.,2.),1),2.220446049250313e-16)
        for name in self.names:
            f=getattr(sem,'sas_'+name);value=f(-0.,1) if name=='modz' else f(-0.)
            self.assertEqual(math.copysign(1.,value),1.)

    def test_every_power_of_two_unit_against_exact_rational_targets(self):
        pins=json.loads((GATE.directory/'zero_fuzz_kernel_pins.json').read_text())
        self.assertEqual(GATE.r_cases([(name,args) for name,args,_ in pins]),[wanted for _,_,wanted in pins])
        for name,args,wanted in pins:
            value=getattr(sem,'sas_'+name)(*args)
            self.assertEqual(value,wanted,(name,args))
            if value==0:self.assertEqual(math.copysign(1.,value),1.)

    def test_missing_validates_other_operands_and_decimal_domains_remain_held(self):
        self.assertIsNone(sem.sas_roundz(None,1))
        self.assertIsNone(sem.sas_modz(1,None))
        with self.assertRaises(ValueError):sem.sas_modz(None,0)
        for name in ['roundz','modz']:
            for unit in [.1,3,2**11,2**-11]:
                with self.assertRaises(ValueError):getattr(sem,'sas_'+name)(1,unit)
        with self.assertRaises(ValueError):sem.sas_ceilz(math.nextafter(0.,1.))

    def test_empty_descriptor_and_skipped_literal_validation(self):
        source='data d;set raw;if 0 then x=roundz(a,u);run;'
        self.assertEqual(job_with_inputs(source,{'raw':{'schema':{'a':'number','u':{'type':'character','length':2}},'rows':[]}}).code,1)
        for rhs in ['roundz(1,.1)','modz(.,0)','ceilz(1e-20)','ceilz(1e-400)','intz(-1e-400)']:
            self.assertEqual(build_job('data d;if 0 then x='+rhs+';run;').code,2)
        self.assertEqual(build_job('data d;value=1e-400;x=ceilz(value);run;').code,2)
        self.assertEqual(build_job('data d;x=ceilz(0e-400);run;').code,0)
        self.assertEqual(build_job('data d;x=roundz(.5,.25);put x;run;').code,1)
        for exponent in range(-10,11):
            unit=2.**exponent
            for neighbor in [math.nextafter(unit,0.),math.nextafter(unit,math.inf)]:
                self.assertEqual(build_job('data d;if 0 then x=roundz(1,'+repr(neighbor)+');run;').code,2)

    def test_late_invalid_unit_is_atomic(self):
        inputs={'raw':{'schema':{'a':'number','u':'number'},'rows':[{'a':2.5,'u':1},{'a':2.5,'u':.1}]}}
        self.atomic_cli('data d;set raw;x=roundz(a,u);output;put x;run;',inputs,'power')

if __name__=='__main__':unittest.main()
