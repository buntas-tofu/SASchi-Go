"""Seven printable ASCII masks, signed starts and stored padding."""
import unittest
from examples.verify_ascii_positions import GATE,REFUSALS
from .wave3_test_support import FamilyContract
from .test_do_counted import execute,job_with_inputs
from .job import build_job
import sas_semantics as sem

class AsciiPositionTests(FamilyContract,unittest.TestCase):
    gate=GATE;refusals=REFUSALS
    names=('anylower','anyupper','anypunct','anyxdigit','notalpha','notalnum','notspace');family='ascii-positions';rule='DS-110'

    def test_hex_and_punctuation_are_exact_ascii_masks(self):
        self.assertEqual(sem.sas_anyxdigit('GgF'),3)
        self.assertEqual(sem.sas_anyxdigit('xyz'),0)
        for value in ['_','[','`','~','!','/']:
            self.assertEqual(sem.sas_anypunct(' '+value),2)
        for value in [' ','a','Z','9']:
            self.assertEqual(sem.sas_anypunct(value),0)

    def test_signed_starts_and_omitted_missing_policies(self):
        self.assertEqual(sem.sas_anylower('aZb',-99),3)
        self.assertEqual(sem.sas_anylower('aZb',-2),1)
        for name in self.names:
            function=getattr(sem,'sas_'+name)
            self.assertEqual(function('aZ9_',0),0)
            self.assertEqual(function('aZ9_',99),0)
            if name!='anypunct':self.assertEqual(function('aZ9_',None),function('aZ9_'))
        with self.assertRaises(ValueError):sem.sas_anypunct('_',None)
        self.assertEqual(build_job("data d;if 0 then x=anypunct('_',.);run;").code,2)

    def test_stored_padding_participates_in_negative_classes(self):
        result,_=execute("data d;length code $4;code='AZ';x=notalpha(code);y=notalnum(code);z=notspace(code);run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'code':'AZ  ','x':3.,'y':3.,'z':1.}])
        self.assertEqual(sem.sas_notspace(' '*32766+'A'),32767)
        self.assertEqual(sem.sas_anylower('a'+' '*32766,-99999),1)

    def test_eager_empty_descriptor_and_bad_literal_checks(self):
        source='data d;set raw;if 0 then x=notalpha(code);run;'
        self.assertEqual(job_with_inputs(source,{'raw':{'schema':{'code':'number'},'rows':[]}}).code,1)
        result,_=execute(source,{'raw':{'schema':{'code':{'type':'character','length':8}},'rows':[]}})
        self.assertEqual(result['datasets']['d']['rows'],[])
        for rhs in ["anylower('')","notspace('é')","anyupper('A',0.5)","notalnum('A',.A)"]:
            self.assertEqual(build_job('data d;if 0 then x='+rhs+';run;').code,2)

    def test_late_invalid_start_is_atomic(self):
        inputs={'raw':{'schema':{'code':{'type':'character','length':8},'start':'number'},'rows':[{'code':'aZ','start':1},{'code':'aZ','start':.5}]}}
        self.atomic_cli('data d;set raw;x=anylower(code,start);output;put x;run;',inputs,'integral')

    def test_unreached_dynamic_start_and_held_consumers(self):
        inputs={'raw':{'schema':{'code':{'type':'character','length':8},'start':'number'},'rows':[{'code':'aZ','start':.5}]}}
        result,_=execute('data d;set raw;if 0 then x=anylower(code,start);run;',inputs)
        self.assertIsNone(result['datasets']['d']['rows'][0]['x'])
        for source in ["data d;if anyupper('A') then x=1;run;","data d;x=notalnum(upcase('a'));run;","data d;x=anylower('a');put anylower('a');run;"]:
            admitted={"data d;if anyupper('A') then x=1;run;":1.,"data d;x=notalnum(upcase('a'));run;":0.}
            if source in admitted:
                from .expression_test_support import assert_new_expression
                assert_new_expression(self,source,[admitted[source]])
            else:self.assertIn(build_job(source).code,(1,2))

if __name__=='__main__':unittest.main()
