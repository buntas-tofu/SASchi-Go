"""DS-029 integration evidence for maintainers, no live SAS verification."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from sas_semantics import sas_concat, sas_catx
from .emit_py import translate
from .functions import character_width
from .plan import compile_plan
from .runtime import run_plan
from .test_parser import ROKU_CORPUS
from .test_put_list import build_job

ROOT=Path(__file__).resolve().parent.parent


def execute(source, inputs=None):
    translation=translate(source)
    if translation.blocked:raise AssertionError(translation.tickets)
    namespace={'inputs':inputs or {}};printed=io.StringIO()
    with contextlib.redirect_stdout(printed):exec(translation.code,namespace)
    return namespace['result'],printed.getvalue()


class ConcatCatxTests(unittest.TestCase):
    def test_both_operator_spellings_and_mixed_chain_preserve_blanks(self):
        for op in ('!!','||'):
            result,_=execute(f"data d; a=' x '; b=' y '; c=a{op}'/'{op}b; run;")
            self.assertEqual(result['datasets']['d']['rows'][0]['c'],' x / y ')
            self.assertEqual(result['datasets']['d']['schema']['c'],{'type':'character','length':7})
        result,_=execute("data d; c='a '!!' b'||' c'; run;")
        self.assertEqual(result['datasets']['d']['rows'][0]['c'],'a  b c')

    def test_operator_text_and_doubled_quotes_remain_inside_literals(self):
        result,_=execute('data d; c="!!"||\'it\'\'s||\'; run;')
        self.assertEqual(result['datasets']['d']['rows'][0]['c'],"!!it's||")

    def test_operator_uses_declared_source_width_and_target_assignment_width(self):
        result,_=execute("data d; length a $4; length c $3; a='q'; c=a||'z'; d=a||'z'; run;")
        row=result['datasets']['d']['rows'][0]
        self.assertEqual(row['c'],'q  ')
        self.assertEqual(row['d'],'q   z')
        self.assertEqual(result['datasets']['d']['schema']['d']['length'],5)

    def test_catx_new_target_default_is_200_and_existing_width_survives(self):
        result,_=execute("data d; c=catx(' / ',' a ',' ',' b '); run;")
        self.assertEqual(result['datasets']['d']['schema']['c'],{'type':'character','length':200})
        self.assertEqual(result['datasets']['d']['rows'][0]['c'],'a / b'.ljust(200))
        result,_=execute("data d; c='xxxxxxxx'; c=catx(' ',' a ',' b '); run;")
        self.assertEqual(result['datasets']['d']['rows'][0]['c'],'a b'.ljust(8))

    def test_catx_all_blank_items_and_delimiter_spacing(self):
        self.assertEqual(sas_catx(' / ',' ','  '),'')
        self.assertEqual(sas_catx(' / ',' a ',' b '),'a / b')
        result,_=execute("data d; c=catx(' ',' ','  '); n=lengthc(c); run;")
        self.assertEqual(result['datasets']['d']['rows'][0]['c'],' '*200)
        self.assertEqual(result['datasets']['d']['rows'][0]['n'],200.)

    def test_direct_catx_rhs_under_if_obeys_execution_guard(self):
        result,_=execute("data d; length c $2; if 0 then c=catx(' ','a','b'); run;")
        self.assertEqual(result['datasets']['d']['rows'][0]['c'],'  ')
        self.assertEqual(build_job("data d; length c $2; if 1 then c=catx(' ','a','b'); run;").code,1)

    def test_empty_set_still_gets_static_concat_and_catx_widths(self):
        inputs={'raw':{'schema':{'a':{'type':'character','length':3},'b':{'type':'character','length':4}},'rows':[]}}
        result,_=execute("data d; set raw; c=a||b; x=catx(' ',a,b); run;",inputs)
        table=result['datasets']['d'];self.assertEqual(table['rows'],[])
        self.assertEqual(table['schema']['c']['length'],7)
        self.assertEqual(table['schema']['x']['length'],200)
        self.assertEqual(character_width({'kind':'concat','args':[{'kind':'variable','value':'a'},{'kind':'character','value':'!'}]},inputs['raw']['schema']),4)

    def test_numeric_operands_refuse_even_empty_or_filtered_inputs(self):
        for rows in ([],[{'a':7}]):
            inputs={'raw':{'schema':{'a':'number'},'rows':rows}}
            for tail in ("c=a||'x'", "c=catx(' ',a)"):
                for where in ('','where a=99;'):
                    job=build_job('data d; set raw; '+where+tail+'; run;',inputs)
                    self.assertEqual(job.code,1)
                    self.assertIsNone(job.result)

    def test_temporary_catx_contexts_are_compile_refusals(self):
        for rhs in ("length(catx(' ','a','b'))", "'x'||catx(' ','a','b')", "catx(' ',catx(' ','a','b'),'c')"):
            job=build_job('data d; c='+rhs+'; run;')
            self.assertEqual(job.code,2,rhs)
            self.assertIsNone(job.result)
        for source in ("data d; if catx(' ','a') then output; run;", "data d; set raw; where catx(' ',a)='a'; run;"):
            self.assertTrue(compile_plan(source).blocked)

    def test_temporary_catx_in_handwritten_plan_is_also_refused(self):
        plan=compile_plan("data d; c=catx(' ','a','b'); run;").to_dict()
        expr=plan['steps'][0]['operations'][0]['args']['value']
        plan['steps'][0]['operations'][0]['args']['value']={'kind':'call','name':'length','args':[expr]}
        with self.assertRaisesRegex(ValueError,'temporary contexts'):run_plan(plan)

    def test_destination_overflow_is_atomic_after_an_earlier_put(self):
        source="data d; length c $2; put 'earlier'; c=catx(' ','a','b'); run;"
        job=build_job(source);self.assertEqual(job.code,1);self.assertIsNone(job.result)
        self.assertIn('destination',job.receipt['error'])
        printed=io.StringIO()
        with contextlib.redirect_stdout(printed),self.assertRaises(ValueError):exec(translate(source).code,{})
        self.assertEqual(printed.getvalue(),'')

    def test_policy_boundaries_and_existing_put_record_limit(self):
        self.assertEqual(len(sas_concat(['x'*16383,'y'*16384])),32767)
        self.assertEqual(len(sas_catx(' ','x'*99,'y'*100)),200)
        for source in ("data d; c=catx(' ','"+'x'*100+"','"+'y'*100+"'); run;", "data d; c=catx(' ','"+'x'*64+"'); put c; run;"):
            job=build_job(source);self.assertEqual(job.code,1);self.assertIsNone(job.result)
        for value in ('',None,7,{'missing':'A'},'é','a\tb'):
            with self.subTest(value=value),self.assertRaises(ValueError):sas_concat([value,'x'])

    def test_malformed_operators_arithmetic_and_numeric_coercion_are_refused(self):
        for rhs in ("'a'| 'b'", "'a'! !'b'", "'a'||| 'b'", "'a'||", "||'a'", "'a'||'b'+1", "'a'|/*x*/|'b'"):
            self.assertTrue(compile_plan('data d; c='+rhs+'; run;').blocked,rhs)
        self.assertEqual(build_job("data d; c=7||'x'; run;").code,1)
        self.assertEqual(build_job("data d; c=catx(' ',7); run;").code,2)

    def test_string_construct_guards_apply_without_put(self):
        for body in ("c='a'||'b'; unused=\"&x\";", "c=catx(' ','a'); unused=\"%call\";", "c='a'||'b'; unused='é';", "c=catx(' ','a'); unused='a\tb';"):
            self.assertEqual(build_job('data d; '+body+' run;').code,2)
        result,_=execute("data d; c='&x'||'%literal'; run;")
        self.assertEqual(result['datasets']['d']['rows'][0]['c'],'&x%literal')

    def test_where_only_concat_enforces_source_guards_even_empty_inputs(self):
        schema = {'a': {'type': 'character', 'length': 1},
                  'b': {'type': 'character', 'length': 1}}
        for rows in ([], [{'a': 'A', 'b': 'B'}]):
            inputs = {'raw': {'schema': schema, 'rows': rows}}
            for prefix, suffix in (
                    ('data prior; unused="&x"; run;', ''),
                    ('', 'unused="%call";'),
                    ("data prior; unused='é'; run;", ''),
                    ('', "unused='a\tb';")):
                source = prefix + 'data d; set raw; where length(a||b)=2; ' + suffix + 'run;'
                with self.subTest(rows=rows, source=source):
                    job = build_job(source, inputs)
                    self.assertEqual(job.code, 2)
                    self.assertIsNone(job.result)
            source = 'data d; set raw; where length(a||b)=2; run;'
            job = build_job(source, inputs)
            self.assertEqual(job.code, 0)
            self.assertEqual(len(job.result['datasets']['d']['rows']), len(rows))

    def test_substr_global_quarantine_is_replaced_by_local_context_checks(self):
        sources = (
                "data prior; x=substr('abcd',2,1); run; data d; c='a'||'b'; run;",
                "data d; c=catx(' ','a'); run; data later; x=substr('abcd',2,1); run;",
                "data d; if 0 then x=substr('abcd',2,1); c='a'||'b'; run;",
                "data d; set raw; where substr(a,1,1)='A'; c='a'||'b'; run;",
                "data d; x=substr('abcd',2,1); y=x; c=catx(' ',y); run;",
                "data d; c=substr('abc',2,5)||'Z'; run;",
                "data d; c=substr('a!!b',1,4)||'x'; run;",
                "data d; c=length(substr('abc',2,1)||'x'); run;")
        inputs={'raw':{'schema':{'a':{'type':'character','length':4}},'rows':[{'a':'AB'}]}}
        pins=[('prior','x','b   '),('d','c','a'.ljust(200)),('d','x',' '*4),
              ('d','c','ab'),('d','c','b'.ljust(200))]
        for index,source in enumerate(sources):
            with self.subTest(source=source):
                plan=compile_plan(source)
                if index < len(pins):
                    self.assertFalse(plan.blocked,plan.tickets)
                    result=run_plan(plan.to_dict(),inputs)
                    dataset,column,value=pins[index]
                    self.assertEqual(result['datasets'][dataset]['rows'][0][column],value)
                else:
                    self.assertTrue(plan.blocked)
                    self.assertIn('SUBSTR temporary',str(plan.tickets))
                    with self.assertRaisesRegex(ValueError,'SUBSTR temporary'):
                        run_plan(plan.to_dict(),inputs,allow_partial=True)
        result,_ = execute('''data d; c='a'||'b'; note="substr('abc',2,5)"; run;''')
        self.assertEqual(result['datasets']['d']['rows'][0]['c'], 'ab')
        # The original standalone path retains its corrected DS-030 descriptor.
        self.assertFalse(compile_plan("data d; x=substr('abcd',2,1); run;").blocked)

    def test_handwritten_plan_checks_actual_substr_consumers(self):
        plan = compile_plan("data d; x=substr('abc',2,1); run;").to_dict()
        plan['matched'] = []
        plan['steps'][0]['operations'].append({'kind': 'assign', 'line': 1, 'args': {
            'name': 'c', 'value': {'kind': 'concat', 'args': [
                {'kind': 'character', 'value': 'a'}, {'kind': 'character', 'value': 'b'}]}}})
        self.assertEqual(run_plan(plan)['datasets']['d']['rows'],[{'x':'b  ','c':'ab'}])
        plan['steps'][0]['operations'][-1]['args']['value']['args'][0] = plan['steps'][0]['operations'][0]['args']['value']
        with self.assertRaisesRegex(ValueError, 'SUBSTR temporary'):
            run_plan(plan,allow_partial=True)

    def test_where_uses_input_width_before_pdv_length_changes(self):
        for width in (1, 4):
            for rows in ([], [{'a': 'AB'}]):
                inputs = {'raw': {'schema': {'a': {'type': 'character', 'length': 2}}, 'rows': rows}}
                source = f"data d; length a ${width}; set raw; where length(a||'C')=3; run;"
                with self.subTest(width=width, rows=rows):
                    job = build_job(source, inputs)
                    self.assertEqual(job.code, 0)
                    table = job.result['datasets']['d']
                    self.assertEqual(table['schema']['a']['length'], width)
                    self.assertEqual(table['rows'], [] if not rows else [{'a': 'AB'[:width].ljust(width)}])

    def test_zero_trip_loop_schema_and_current_pdv_values(self):
        result,_=execute("data d; a='q '; do i=2 to 1; c=a||'z'; x=catx(' ',a); end; run;")
        self.assertEqual(result['datasets']['d']['schema']['c']['length'],3)
        self.assertEqual(result['datasets']['d']['schema']['x']['length'],200)
        self.assertEqual(result['datasets']['d']['rows'][0]['c'],'   ')
        result,_=execute("data d; a='q'; do i=1 to 2; a=a||'x'; c=catx(' ',a,'z'); end; run;")
        self.assertEqual(result['datasets']['d']['rows'][0]['a'],'q')
        self.assertEqual(result['datasets']['d']['rows'][0]['c'],'q z'.ljust(200))

    def test_cpp_and_put_all_remain_refused(self):
        self.assertEqual(build_job("data _null_; c='a'||'b'; run;",target='cpp').code,2)
        self.assertEqual(build_job("data d; c=catx(' ','a'); put _all_; run;").code,1)
        for expression in ("'a'||'b'", "length('a'||'b')", "catx(' ','a')"):
            source='data d; x='+expression+'; put _all_; run;'
            job=build_job(source);self.assertEqual(job.code,1);self.assertIsNone(job.result)
            printed=io.StringIO()
            with contextlib.redirect_stdout(printed),self.assertRaises(ValueError):exec(translate(source).code,{})
            self.assertEqual(printed.getvalue(),'')



class ConcatCorpusTests(unittest.TestCase):
    def test_unmodified_external_program_hashes_job_and_independent_r(self):
        path=ROKU_CORPUS/'string_concatenation.sas'
        if not path.is_file():self.skipTest('Roku corpus not present')
        source=path.read_text();self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),'be42363a757aeb8822283782fe80a6c31ad9f4becd8a7c126295ad3849649f5f')
        result,printed=execute(source)
        self.assertEqual(hashlib.sha256(printed.encode()).hexdigest(),'f0f280d53b27245e18c0b2ddce6bf1f9cb6c39d009dc365597967f9956e7c1fa')
        self.assertEqual(hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'54cba1edd3b7cd9b6b7022d99df6a675bbb51a193e690a62573f76e100cea2a3')
        r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        run=subprocess.run([r,str(ROOT/'examples/concat_catx.R'),'program',str(path)],capture_output=True,text=True,check=True,timeout=60)
        lines=run.stdout.splitlines();self.assertEqual(lines[0],'STATE:2:3')
        independent=[bytes.fromhex(line[7:]).decode('ascii') for line in lines[1:]]
        self.assertEqual(result['log'],independent)
        job=build_job(source);self.assertEqual(job.code,0);self.assertTrue(job.receipt['accepted']);self.assertEqual(job.result,result)
        self.assertEqual(job.receipt['source_sha256'],'be42363a757aeb8822283782fe80a6c31ad9f4becd8a7c126295ad3849649f5f')
        print('VERIFIED corpus: string_concatenation.sas; source/stdout/complete-result hashes and independent base R agree; no live SAS')
