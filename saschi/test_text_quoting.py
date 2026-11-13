"""Text quoting bytes, temporary lengths, descriptors and atomic errors."""
import unittest
from copy import deepcopy
from examples.verify_text_quoting import GATE,REFUSALS
from .wave3_test_support import FamilyContract
from .test_do_counted import execute,job_with_inputs
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from sas_semantics import sas_propcase,sas_quote,sas_dequote,sas_countc,sas_transtrn

class TextQuotingTests(FamilyContract,unittest.TestCase):
    gate=GATE;refusals=REFUSALS
    names=('propcase','quote','dequote','countc','transtrn');family='text-and-quoting';rule='DS-109'

    def test_propcase_uses_explicit_delimiters_and_character_positions(self):
        self.assertEqual(sas_propcase('9ABC/DEF-GHI','-'),'9abc/def-Ghi')
        self.assertEqual(sas_propcase('AB CD','-'),'Ab cd')
        self.assertEqual(sas_propcase('AB CD',' '),'Ab Cd')
        result,_=execute("data d;length x $3;x=propcase('AB-CD','-');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'x':'Ab-'}])

    def test_quote_preserves_all_stored_blanks_and_doubles_selected_quotes(self):
        result,_=execute('data d;length a $4;a=\'A"\';x=quote(a);y=quote("a\'b", "\'");run;')
        row=result['datasets']['d']['rows'][0]
        self.assertEqual(row['x'],'"A""  "'.ljust(200))
        self.assertEqual(row['y'],"'a''b'".ljust(200))
        with self.assertRaisesRegex(ValueError,'destination|buffer'):
            execute("data d;length x $2;x=quote('A');run;")
        self.assertEqual(len(sas_quote(' '*198)),200)

    def test_dequote_termination_doubled_and_unclosed_quotes(self):
        for text,wanted in [('"A""B"tail','A"B'),('"open','open'),('""tail',''),('"""A','"A'),(' "A"',' "A"'),('"','')]:
            self.assertEqual(sas_dequote(text),wanted)
        result,_=execute("data d;length x $2;x=dequote('\"ABCD\"tail');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'x':'AB'}])

    def test_countc_set_complement_case_and_trim_are_distinct(self):
        self.assertEqual(sas_countc('Aa a  ','a'),2)
        self.assertEqual(sas_countc('Aa a  ','a','i'),3)
        self.assertEqual(sas_countc('Aa a  ','a','iv'),3)
        self.assertEqual(sas_countc('Aa a  ','a','ivt'),1)
        self.assertEqual(sas_countc('a   ',' ','vt'),0)

    def test_transtrn_blanks_and_zero_length_are_distinct(self):
        self.assertEqual(sas_transtrn('abcxabc','abc',''),'x')
        self.assertEqual(sas_transtrn('abcxabc','abc',' '),' x ')
        self.assertEqual(sas_transtrn('CATFISH','FISH ','X'),'CATFISH')
        result,_=execute("data d;length target $5;target='FISH';x=transtrn('CATFISH',target,'X');run;")
        self.assertEqual(result['datasets']['d']['rows'][0]['x'],'CATFISH'.ljust(200))
        self.assertEqual(build_job("data d;x=transtrn('a-b','-','');run;").code,2)

    def test_empty_and_skipped_paths_still_validate_literals_and_descriptors(self):
        for rhs in ["propcase('A')","propcase('A','')","quote('A','x')","countc('A','A','d')","transtrn('A','','X')","quote('"+'A'*199+"')"]:
            self.assertEqual(build_job('data d;if 0 then x='+rhs+';run;').code,2)
        source='data d;set raw;if 0 then x=quote(a);run;'
        self.assertEqual(job_with_inputs(source,{'raw':{'schema':{'a':'number'},'rows':[]}}).code,1)
        result,_=execute(source,{'raw':{'schema':{'a':{'type':'character','length':4}},'rows':[]}})
        self.assertEqual(result['datasets']['d']['rows'],[])
        self.assertEqual(result['datasets']['d']['schema']['x'],{'type':'character','length':200})
        self.assertEqual(build_job("data d;length x $2;if 0 then x=quote('A');run;").code,1)
        inputs={'raw':{'schema':{'a':'number'},'rows':[]}}
        self.assertEqual(job_with_inputs("data d;length x $2;set raw;x=quote('A');run;",inputs).code,1)

    def test_countc_has_separate_new_profile_and_legacy_refusal(self):
        source="data d;x=countc('abc','a');run;";plan=compile_plan(source)
        self.assertFalse(plan.blocked,plan.tickets)
        self.assertIn(('text-and-quoting','DS-109',1),plan.matched)
        self.assertEqual(run_plan(plan.to_dict())['datasets']['d']['rows'],[{'x':1.}])
        old=plan.to_dict();old['version']=1
        with self.assertRaises(ValueError):run_plan(old)

    def test_late_quote_buffer_failure_is_atomic_in_cli_and_emission(self):
        inputs={'raw':{'schema':{'a':{'type':'character','length':120}},'rows':[{'a':'ok'},{'a':'"'*120}]}}
        self.atomic_cli("data d;set raw;x=quote(a);output;put 'row';run;",inputs,'QUOTE')

    def test_unreached_dynamic_quote_does_not_run(self):
        inputs={'raw':{'schema':{'a':{'type':'character','length':120}},'rows':[{'a':'"'*120}]}}
        result,_=execute('data d;set raw;if 0 then x=quote(a);output;run;',inputs)
        self.assertEqual(result['datasets']['d']['rows'][0]['x'],' '*200)

    def test_profile_joins_and_unqualified_nested_forms_stay_held(self):
        for source in ["data d;x=quote(propcase('A',' '));run;","data d;retain n 0;x=quote('A');run;","data d;array z a;x=quote('A');run;","data d;set raw;where a=1;x=quote('A');run;"]:
            self.assertIn(build_job(source).code,(1,2))

if __name__=='__main__':unittest.main()
