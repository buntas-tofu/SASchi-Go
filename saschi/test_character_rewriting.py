"""DS-098 stored bytes, strict controls and atomic character rewrite failures."""
from copy import deepcopy
import json
import unittest

from examples.verify_character_rewriting import GATE,REFUSALS
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .rules import route_function
from .test_do_counted import execute,job_with_inputs
from .test_word_functions import catalog


class CharacterRewritingTests(unittest.TestCase):
    def test_original_complete_independent_witness_and_emitted_output(self):
        GATE.qualify(REFUSALS)
        result,stdout=execute(GATE.source.read_text(),json.loads(GATE.inputs.read_text()))
        self.assertEqual(result,json.loads(GATE.expected.read_text()))
        self.assertEqual(stdout,''.join(line+'\n' for line in result['log']))

    def test_source_widths_and_empty_compress_storage(self):
        result,_=execute("data d;a=compress('   ');b=translate(' a ','x','a');c=tranwrd('ab','a','X');run;")
        table=result['datasets']['d']
        self.assertEqual([spec['length'] for spec in table['schema'].values()],[3,3,200])
        self.assertEqual(table['rows'],[{'a':'   ','b':' x ','c':'Xb'+' '*198}])

    def test_keep_case_and_literal_metacharacters(self):
        result,_=execute("data d;a=compress('A b-aB','ab','IK');b=compress('x-y]z','-]');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':'AbaB  ','b':'xyz  '}])

    def test_non_ascii_modifiers_refuse_before_case_mapping(self):
        from sas_semantics import sas_compress
        from wave_gate_common import REFUSED
        for modifier in ('ı','K'):
            with self.subTest(modifier=modifier),self.assertRaises(ValueError):sas_compress('aA','a',modifier)
            self.assertIs(GATE.r_cases([('compress',['aA','a',modifier])])[0],REFUSED)
            self.assertEqual(build_job("data d;x=compress('aA','a','"+modifier+"');run;").code,2)

    def test_nonoverlap_no_rescan_and_empty_replacement(self):
        result,_=execute("data d;length a b c $6;a=tranwrd('aaaaa','aa','b');b=tranwrd('ab','a','aa');c=tranwrd('a a','a','');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':'bba   ','b':'aab   ','c':'      '}])

    def test_target_blanks_are_significant(self):
        result,_=execute("data d;length a b $6;a=tranwrd('ab ab ','ab ','X');b=tranwrd('ab ab ','ab','X');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':'XX    ','b':'X X   '}])

    def test_exact200_boundary_and_declared_truncation(self):
        result,_=execute("data d;length a $2;a=tranwrd('aaaa','a','"+'x'*50+"');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':'xx'}])
        self.assertIn(build_job("data d;length a $2;if 0 then a=tranwrd('aaaa','a','"+'x'*51+"');run;").code,(1,2))

    def test_invalid_literals_validate_on_empty_and_skipped_paths(self):
        for rhs in ("compress('abc','')","compress('abc','a','Q')","translate('abc','x','ab')",
                    "translate('abc','xy','aa')","tranwrd('abc','','x')","tranwrd('abc','a','é')"):
            with self.subTest(rhs=rhs):self.assertIn(build_job('data d;if 0 then a='+rhs+';run;').code,(1,2))
        for rows in ([],[1]):
            self.assertEqual(job_with_inputs("data d;set raw;if 0 then a=compress(text);run;",catalog(rows,'number')).code,1)

    def test_dynamic_values_are_lazy_but_late_errors_are_atomic(self):
        result,_=execute("data d;set raw;if 0 then a=compress(text);run;",catalog(['é']))
        self.assertEqual(result['datasets']['d']['rows'][0]['a'],' '*8)
        job=job_with_inputs("data d;set raw;a=compress(text);output;put a;run;",catalog(['A','é']))
        self.assertEqual(job.code,1);self.assertIsNone(job.result);self.assertFalse(job.receipt['accepted'])

    def test_late_overflow_is_atomic_even_with_small_destination(self):
        inputs=catalog(['b'*4,'a'*4],{'type':'character','length':4})
        job=job_with_inputs("data d;length a $2;set raw;a=tranwrd(text,'a','"+'x'*51+"');output;put a;run;",inputs)
        self.assertEqual(job.code,1);self.assertIsNone(job.result)

    def test_portable_call_controls_are_closed(self):
        original=compile_plan("data d;a=translate('abc','12','ab');run;").to_dict()
        for mutation in ('shape','pair','variable','kind','version'):
            plan=deepcopy(original);call=plan['steps'][0]['operations'][0]['args']['value']
            if mutation=='shape':call['extra']=False
            elif mutation=='pair':call['args'][1]['value']='1'
            elif mutation=='variable':call['args'][2]={'kind':'variable','value':'text'}
            elif mutation=='kind':call['args'][0]={'kind':'number','value':True}
            else:plan['version']=True
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):run_plan(plan)

    def test_nested_consumers_and_variable_controls_refuse(self):
        for rhs in ("compress(upcase('a'))","length(compress('a'))","tranwrd('a',text,'x')","translate('a','x',text)","compress('a','a',text)"):
            with self.subTest(rhs=rhs):self.assertIn(build_job('data d;x='+rhs+';run;').code,(1,2))

    def test_stored_values_compose_with_earlier_character_groups(self):
        result,_=execute("data d;a=upcase('a|b');b=scan(a,2,'|');c=compress(b);d=translate(c,'x','B');e=tranwrd(d,'x','Z');run;")
        self.assertEqual(result['datasets']['d']['rows'][0]['e'],'Z'+' '*199)

    def test_numeric_array_names_stay_legal(self):
        for name in ('compress','translate','tranwrd'):
            result,_=execute(f'data d;array {name} a b;a=1;b=2;x={name}[2];run;')
            self.assertEqual(result['datasets']['d']['rows'],[{'a':1.,'b':2.,'x':2.}])

    def test_preexisting_metadata_survives_new_descriptors(self):
        spec={'type':'character','length':8,'label':'Original','format':'$CHAR8.'}
        result,_=execute("data d;set raw;a=compress(text);b=tranwrd(text,'a','X');run;",catalog(['a'],spec))
        self.assertEqual(result['datasets']['d']['schema'],{'text':spec,'a':{'type':'character','length':8},'b':{'type':'character','length':200}})

    def test_unqualified_profiles_and_cpp_stay_refused(self):
        for source in ("data d;retain n 0;a=compress('a');run;","data d;set raw;where compress(text)='a';run;",
                       "data d;array z x;a=compress('a');run;","data d;do while(0);a=compress('a');end;run;"):
            self.assertIn(build_job(source).code,(1,2))
        self.assertEqual(build_job("data _null_;a=compress('a');run;",target='cpp').code,2)

    def test_routes_name_the_new_evidence(self):
        for name in ('compress','translate','tranwrd'):
            self.assertEqual(route_function(f'x={name}(s);')[1],'DS-098')


if __name__=='__main__':unittest.main()
