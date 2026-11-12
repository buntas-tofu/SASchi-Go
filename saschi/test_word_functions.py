"""DS-097 explicit delimiters, versioned widths and source/portable boundaries."""
from copy import deepcopy
import json
import os
import subprocess
import sys
import unittest

from examples.verify_word_functions import GATE,REFUSALS
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .test_do_counted import execute,job_with_inputs


def catalog(values,spec=None):
    return {'raw':{'schema':{'text':spec or {'type':'character','length':8}},'rows':[{'text':v} for v in values]}}


class WordFunctionTests(unittest.TestCase):
    def test_original_full_hand_r_and_emitted_results(self):
        GATE.qualify(REFUSALS)
        result,stdout=execute(GATE.source.read_text(),json.loads(GATE.inputs.read_text()))
        self.assertEqual(result,json.loads(GATE.expected.read_text()))
        self.assertEqual(stdout,''.join(x+'\n' for x in result['log']))

    def test_source_width_inherits_pinned_current_edition(self):
        result,_=execute("data d;a=scan('a b',1,' ');run;")
        self.assertEqual(result['datasets']['d'],{'schema':{'a':{'type':'character','length':3}},'rows':[{'a':'a  '}]})
        result,_=execute("data d;length a $2;a=scan('long word',1,' ');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':'lo'}])

    def test_padding_is_part_of_delimiter_contract(self):
        result,_=execute("data d;length a $6;a='x|';n=countw(a,'|');m=countw(a,'|','M');tail=scan(a,-1,'|');run;")
        row=result['datasets']['d']['rows'][0]
        self.assertEqual((row['n'],row['m'],row['tail']),(2.,2.,'      '))

    def test_empty_fields_and_out_of_range_positions(self):
        result,_=execute("data d;a=scan('|a||',2,'|','M');b=scan('|a||',-1,'|','M');c=scan('ab',2,'|');n=countw('|||','|');m=countw('|||','|','M');run;")
        row=result['datasets']['d']['rows'][0]
        self.assertEqual(row,{'a':'a   ','b':'    ','c':'  ','n':0.,'m':4.})

    def test_numeric_variable_positions_and_negative_direction(self):
        result,_=execute("data d;n=-2;a=scan('one|two|three',n,'|');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'n':-2.,'a':'two          '}])

    def test_delimiter_metacharacters_are_literal(self):
        result,_=execute("data d;a=scan('a-b]c^d',3,'-]^');n=countw('a-b]c^d','-]^');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':'c      ','n':4.}])

    def test_unknown_defaults_other_modifiers_and_nested_consumers_refuse(self):
        for rhs in ("scan('a b',1)","countw('a b')","scan('a b',1,' ','Q')","countw('a b',' ','I')",
                    "scan('a',0,' ')","scan('a',.,' ')","scan('a',.A,' ')","scan('a',1.5,' ')",
                    "scan('a',1,'')","scan('a',1,delimiters)","length(scan('a b',1,' '))","scan(upcase('a'),1,' ')"):
            with self.subTest(rhs=rhs):self.assertIn(build_job('data d;x='+rhs+';run;').code,(1,2))

    def test_empty_and_skipped_input_statically_checks_descriptors(self):
        result,_=execute("data d;set raw;if 0 then a=scan(text,1,' ');run;",catalog([]))
        self.assertEqual(result['datasets']['d']['schema']['a'],{'type':'character','length':8})
        for rows in ([],[1]):
            self.assertEqual(job_with_inputs("data d;set raw;if 0 then a=scan(text,1,' ');run;",catalog(rows,'number')).code,1)
        self.assertIn(build_job("data d;if 0 then a=scan('a',0,' ');run;").code,(1,2))

    def test_skipped_dynamic_invalid_values_remain_lazy(self):
        result,_=execute("data d;set raw;if 0 then a=scan(text,1,' ');run;",catalog(['é']))
        self.assertEqual(result['datasets']['d']['rows'][0]['a'],' '*8)

    def test_input_metadata_preserved_and_output_is_fresh(self):
        spec={'type':'character','length':8,'label':'Original','format':'$CHAR8.'}
        result,_=execute("data d;set raw;a=scan(text,1,' ');run;",catalog(['A B'],spec))
        self.assertEqual(result['datasets']['d']['schema'],{'text':spec,'a':{'type':'character','length':8}})

    def test_portable_shape_version_and_control_checks(self):
        original=compile_plan("data d;a=scan('a b',1,' ');run;").to_dict()
        for mutation in ('args','count','delimiter','modifier','extra','version'):
            plan=deepcopy(original);call=plan['steps'][0]['operations'][0]['args']['value']
            if mutation=='args':call['args']=None
            elif mutation=='count':call['args'][1]['value']=True
            elif mutation=='delimiter':call['args'][2]={'kind':'variable','value':'text'}
            elif mutation=='modifier':call['args'].append({'kind':'character','value':'Q'})
            elif mutation=='extra':call['extra']=0
            else:plan['version']=2.0
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):run_plan(plan)

    def test_new_arrays_names_and_prior_names_remain_available(self):
        for name in ('scan','countw'):
            result,_=execute(f'data d;array {name} a b;a=1;b=2;x={name}[2];run;')
            self.assertEqual(result['datasets']['d']['rows'],[{'a':1.,'b':2.,'x':2.}])

    def test_case_and_word_groups_compose_only_through_stored_values(self):
        result,_=execute("data d;upper=upcase('a|B');first=scan(upper,1,'|');n=countw(upper,'|');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'upper':'A|B','first':'A  ','n':2.}])

    def test_late_invalid_character_or_count_failure_is_atomic(self):
        for source,inputs in [("data d;set raw;a=scan(text,1,' ');put a;output;run;",catalog(['A','é'])),
            ("data d;set raw;a=scan('A B',n,' ');put a;output;run;",{'raw':{'schema':{'n':'number'},'rows':[{'n':1},{'n':0}]}})]:
            job=job_with_inputs(source,inputs)
            self.assertEqual(job.code,1);self.assertIsNone(job.result);self.assertFalse(job.receipt['accepted'])

    def test_other_profiles_and_cpp_stay_refused(self):
        for source in ["data d;retain n 0;a=scan('a b',1,' ');run;","data d;set raw;where countw(text,' ');run;",
                       "data d;array z x;a=scan('a',1,' ');run;","data d;n=0;do while(n<1);a=scan('a',1,' ');n=n+1;end;run;"]:
            self.assertIn(build_job(source).code,(1,2))
        self.assertEqual(build_job("data _null_;n=countw('a b',' ');run;",target='cpp').code,2)

    def test_source_guard_ignores_literal_names_and_refuses_macro_triggers(self):
        self.assertEqual(build_job("data d;x='countw(a)';y='é';run;").code,0)
        for suffix in ('y="&value";',"y='é';"):
            self.assertEqual(build_job("data d;x=countw('a b',' ');"+suffix+'run;').code,2)

    def test_plan_and_emitted_provenance_are_stable_across_hash_seeds(self):
        code=("from pathlib import Path;from saschi.plan import compile_plan;from saschi.emit_py import translate;"
              "import hashlib,json;paths=['examples/case_search_capture.sas','examples/word_functions_capture.sas'];"
              "print(json.dumps([[hashlib.sha256(json.dumps(compile_plan(Path(p).read_text()).to_dict(),sort_keys=True).encode()).hexdigest(),"
              "hashlib.sha256(translate(Path(p).read_text()).code.encode()).hexdigest()] for p in paths]))")
        observed=[]
        for seed in (1,2,3):
            result=subprocess.run([sys.executable,'-c',code],cwd=GATE.root,env={**os.environ,'PYTHONHASHSEED':str(seed)},capture_output=True,text=True,check=True,timeout=30)
            observed.append(result.stdout)
        self.assertEqual(len(set(observed)),1)


if __name__=='__main__':unittest.main()
