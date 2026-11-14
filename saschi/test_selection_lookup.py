"""Selection and lookup missing states, eager validation and signed choices."""
import unittest
from examples.verify_selection_lookup import GATE,REFUSALS
from .wave3_test_support import FamilyContract
from .test_do_counted import execute,job_with_inputs
from .job import build_job
import sas_semantics as sem

class SelectionLookupTests(FamilyContract,unittest.TestCase):
    gate=GATE;refusals=REFUSALS
    names=('ifn','ifc','choosen','choosec','whichn','whichc');family='selection-and-lookup';rule='DS-111'

    def test_missing_condition_uses_false_without_fourth_argument(self):
        self.assertEqual(sem.sas_ifn(None,7,8),8)
        self.assertEqual(sem.sas_ifn(None,7,8,9),9)
        self.assertEqual(sem.sas_ifc(None,'Y','N'),'N')
        self.assertEqual(sem.sas_ifc(None,'Y','N','M'),'M')
        self.assertEqual(sem.sas_ifn(-.5,7,8),7)

    def test_unselected_arguments_are_validated(self):
        for name,args in [('ifn',[1,2,'bad']),('ifc',[1,'OK','é']),('choosen',[1,2,'bad']),('whichn',[1,1,True]),('whichc',['a','a','é'])]:
            with self.assertRaises(ValueError):getattr(sem,'sas_'+name)(*args)
        self.assertEqual(build_job("data d;if 0 then x=ifn(1,2,'bad');run;").code,2)

    def test_negative_choose_indexes_count_from_the_end(self):
        self.assertEqual(sem.sas_choosen(-1,10,20,30),30)
        self.assertEqual(sem.sas_choosen(-3,10,20,30),10)
        self.assertEqual(sem.sas_choosec(-2,'A','B','C'),'B')
        for index in [0,None,.5,4,-4]:
            with self.assertRaises(ValueError):sem.sas_choosen(index,1,2,3)

    def test_first_duplicate_padded_equality_and_missing_search(self):
        self.assertEqual(sem.sas_whichn(2,3,2,2),2)
        self.assertEqual(sem.sas_whichc('A  ','B','A','A '),2)
        self.assertEqual(sem.sas_whichc('a','A','B'),0)
        self.assertIsNone(sem.sas_whichn(None,None,2))
        self.assertIsNone(sem.sas_whichc('   ',' ','A'))

    def test_character_width_storage_and_metadata(self):
        result,_=execute("data d;length x $2;x=ifc(1,'LONG','NO');y=choosec(-1,'A','BBB');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'x':'LO','y':'BBB'.ljust(200)}])
        self.assertEqual(result['datasets']['d']['schema'],{'x':{'type':'character','length':2},'y':{'type':'character','length':200}})

    def test_empty_and_skipped_descriptors_validate_all_branches(self):
        source="data d;set raw;if 0 then x=ifc(1,'OK',bad);run;"
        self.assertEqual(job_with_inputs(source,{'raw':{'schema':{'bad':'number'},'rows':[]}}).code,1)
        result,_=execute(source,{'raw':{'schema':{'bad':{'type':'character','length':4}},'rows':[]}})
        self.assertEqual(result['datasets']['d']['rows'],[])

    def test_late_invalid_index_is_atomic(self):
        inputs={'raw':{'schema':{'index':'number'},'rows':[{'index':1},{'index':0}]}}
        self.atomic_cli('data d;set raw;x=choosen(index,10,20);output;put x;run;',inputs,'index')

    def test_unreached_invalid_index_does_not_evaluate(self):
        inputs={'raw':{'schema':{'index':'number'},'rows':[{'index':0}]}}
        result,_=execute('data d;set raw;if 0 then x=choosen(index,10,20);run;',inputs)
        self.assertIsNone(result['datasets']['d']['rows'][0]['x'])
        for source in ["data d;x=ifn(1,largest(1,2,3),4);run;","data d;x=whichc(dequote('A'),'A');run;"]:
            if source=="data d;x=ifn(1,largest(1,2,3),4);run;":
                from .expression_test_support import assert_new_expression
                assert_new_expression(self,source,[3.])
            else:self.assertIn(build_job(source).code,(1,2))

if __name__=='__main__':unittest.main()
