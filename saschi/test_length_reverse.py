"""DS-028 bounded declaration/reversal proofs, repository and R evidence only."""
import contextlib
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from examples.verify_length_reverse import program_records
from sas_semantics import sas_reverse
from .emit_py import translate
from .functions import character_width
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .test_parser import ROKU_CORPUS

SOURCE_SHA = 'e6e28f873fd9b2a468ad34bc21a7759eca7ecd482dbdbd2f6d154d15a8064299'
STDOUT_SHA = '6c6da5277ce04c4871076e61906da8ff7fc0cc31656f82ff1cb34ec651fd324b'
RESULT_SHA = 'eb97990f8c832fa72099192ba78fc7adbee1b436eb2665e89e80b783fb2ee45e'


def execute(source, inputs=None):
    plan = compile_plan(source)
    if plan.blocked:
        raise AssertionError(plan.tickets)
    return run_plan(plan.to_dict(),inputs)


class LengthReverseTests(unittest.TestCase):
    def test_length_list_declares_in_source_order(self):
        plan = compile_plan('data d; length B a C $4; run;')
        self.assertFalse(plan.blocked,plan.tickets)
        self.assertEqual([asdict(op) for op in plan.steps[0].operations], [
            {'kind':'declare','line':1,'args':{'name':name,'spec':{'type':'character','length':4}}}
            for name in ('b','a','c')])
        result = run_plan(plan.to_dict())['datasets']['d']
        self.assertEqual(list(result['schema']),['b','a','c'])
        self.assertEqual(result['rows'],[{'b':'    ','a':'    ','c':'    '}])

    def test_existing_single_name_length_and_functions_keep_behavior(self):
        row = execute("data d; length a $3; a='abcdef'; n=length(a); nn=lengthn(a); nc=lengthc(a); run;")['datasets']['d']['rows'][0]
        self.assertEqual(row,{'a':'abc','n':3.,'nn':3.,'nc':3.})

    def test_invalid_lists_never_emit_partial_declarations(self):
        for declaration in ('length a A $3','length a _n_ $3','length a _infile_ $3',
                            'length a b $0','length a b $32768','length a b $٣',
                            'length a K $3','length a İ $3','length a ı $3',
                            'length a-b $3','length a: $3','length a $3 b $4',
                            'length a b 3','length a b $'+'9'*5000):
            plan = compile_plan('data d; '+declaration+'; run;')
            with self.subTest(declaration=declaration[:80]):
                self.assertTrue(plan.blocked)
                self.assertEqual(plan.steps[0].operations,[])
                self.assertEqual(plan.steps[0].lengths,{})

    def test_late_or_body_declarations_remain_refused(self):
        for source in ('data d; a=1; length b c $3; run;',
                       'data d; set raw; length b c $3; run;',
                       'data d; do i=1 to 2; length b c $3; end; run;',
                       'data d; length a $2; length b a $3; run;'):
            self.assertTrue(compile_plan(source).blocked,source)

    def test_function_shaped_identifiers_remain_ordinary(self):
        row = execute("data d; length reverse length $3; reverse='ab'; length=reverse(reverse); run;")['datasets']['d']['rows'][0]
        self.assertEqual(row,{'reverse':'ab ','length':' ba'})

    def test_return_width_uses_fixed_argument_not_trimmed_value(self):
        table = execute("data d; length a $7; a=' Qz'; b=reverse(a); n=lengthc(b); run;")['datasets']['d']
        self.assertEqual(table['schema']['b'],{'type':'character','length':7})
        self.assertEqual(table['rows'][0],{'a':' Qz    ','b':'    zQ ','n':7.})

    def test_predeclared_target_truncation_and_padding(self):
        row = execute("data d; length a $5; length b $2; length c $7; a='ab'; b=reverse(a); c=reverse(a); run;")['datasets']['d']['rows'][0]
        self.assertEqual(row,{'a':'ab   ','b':'  ','c':'   ba  '})

    def test_literal_and_nested_call_widths(self):
        table = execute("data d; b=reverse(' xY '); c=reverse(reverse(b)); d=reverse(put(1,5.0)); run;")['datasets']['d']
        self.assertEqual(table['schema']['b'],{'type':'character','length':4})
        self.assertEqual(table['schema']['d'],{'type':'character','length':5})
        self.assertEqual(table['rows'][0],{'b':' Yx ','c':' Yx ','d':'1    '})
        expression = compile_plan("data d; x=reverse('abc'); run;").steps[0].operations[0].args['value']
        self.assertEqual(character_width(expression),3)

    def test_substr_compositions_use_local_context_and_corrected_descriptors(self):
        sources = [
            "data d; a=reverse(substr('abcde',2,3)); run;",
            "data prior; a=substr('abcde',2,3); run; data d; b=reverse('xy'); run;",
            "data d; a=reverse('xy'); unused=substr('abcde',2,3); run;",
            "data d; do i=2 to 1; unused=substr('abcde',2,3); end; a=reverse('xy'); run;",
            "data d; if 0 then unused=substr('abcde',2,3); a=reverse('xy'); run;",
            "data d; set raw; where substr(a,1,1)='x'; b=reverse(a); run;",
            "data d; a=substr('abcde',2,3); copy=a; b=reverse(copy); run;",
            "data d; length a b $4; c=substr('abcde',2,3); run;",
            "data prior; c=substr('abcde',2,3); run; data d; length a b $4; run;",
        ]
        expected=[None,('d','b','yx'),('d','a','yx'),('d','unused',' '*5),
                  ('d','unused',' '*5),('d','b','   Yx'),('d','b','  dcb'),
                  ('d','c','bcd  '),('prior','c','bcd  ')]
        inputs={'raw':{'schema':{'a':{'type':'character','length':5}},'rows':[{'a':'xY'}]}}
        for source,pin in zip(sources,expected):
            with self.subTest(source=source):
                plan=compile_plan(source)
                if pin is None:
                    self.assertTrue(plan.blocked)
                    with self.assertRaisesRegex(ValueError,'SUBSTR temporary'):
                        run_plan(plan.to_dict(),inputs,allow_partial=True)
                else:
                    self.assertFalse(plan.blocked,plan.tickets)
                    dataset,column,value=pin
                    result=run_plan(plan.to_dict(),inputs)
                    self.assertEqual(result['datasets'][dataset]['rows'][0][column],value)

    def test_function_text_and_single_declarations_retain_behavior(self):
        source="data d; length a b $16; a='substr(x,2,3)'; b=reverse(a); run;"
        self.assertFalse(compile_plan(source).blocked)
        self.assertTrue(build_job(source).receipt['accepted'])
        # DS-030 corrected descriptors also apply to the original single-name paths.
        for source in ("data d; x=substr('abcde',2,3); run;",
                       "data d; length a $5; a='abcde'; b=substr(a,2,3); run;",
                       "data d; length a $5; length b $3; a='abcde'; b=substr(a,2,3); run;"):
            self.assertFalse(compile_plan(source).blocked)
            self.assertTrue(build_job(source).receipt['accepted'])

    def test_where_reverse_uses_input_descriptors_before_filtering(self):
        source = "data d; set raw; where reverse(a)='  ba'; run;"
        for rows in ([],[{'a':'ab'},{'a':'cd'}]):
            result = execute(source,{'raw':{'schema':{'a':{'type':'character','length':4}},'rows':rows}})['datasets']['d']
            self.assertEqual(result['rows'],[{'a':'ab  '}] if rows else [])
        for rows in ([],[{'a':7}]):
            with self.subTest(rows=rows),self.assertRaisesRegex(ValueError,'REVERSE'):
                execute(source,{'raw':{'schema':{'a':'number'},'rows':rows}})
        guarded = build_job("data d; set raw; where reverse(a)='ab'; unused='é'; run;")
        self.assertEqual(guarded.code,2)

    def test_where_width_precedes_length_override_and_pdv_coercion(self):
        for input_width, target_width, comparison, expected in ((2,4,'BA','AB  '),(4,2,'  BA','AB')):
            source=f"data d; length a ${target_width}; set raw; where reverse(a)='{comparison}'; run;"
            for rows in ([],[{'a':'AB'}]):
                with self.subTest(input_width=input_width,target_width=target_width,rows=rows):
                    result=execute(source,{'raw':{'schema':{'a':{'type':'character','length':input_width}},'rows':rows}})['datasets']['d']
                    self.assertEqual(result['rows'],[{'a':expected}] if rows else [])
                    self.assertEqual(result['schema']['a'],{'type':'character','length':target_width})

    def test_copy_and_input_schema_supply_return_width(self):
        source='data d; set raw; copy=a; rev=reverse(copy); run;'
        for rows in ([],[{'a':'ab'}]):
            result = execute(source,{'raw':{'schema':{'a':{'type':'character','length':4,'format':'$4.'}},'rows':rows}})['datasets']['d']
            self.assertEqual(result['schema']['copy'],{'type':'character','length':4})
            self.assertEqual(result['schema']['rev'],{'type':'character','length':4})
            if rows:self.assertEqual(result['rows'][0]['rev'],'  ba')

    def test_zero_trip_body_still_defines_reverse_descriptor(self):
        result = execute("data d; length a $5; a='ab'; do i=2 to 1; b=reverse(a); end; run;")['datasets']['d']
        self.assertEqual(result['schema']['b'],{'type':'character','length':5})
        self.assertEqual(result['rows'][0]['b'],'     ')

    def test_call_checks_run_inside_sized_and_numeric_destinations(self):
        for source in ('data d; set raw; length_of_reverse=length(reverse(n)); run;',
                       'data d; length b $5; set raw; b=reverse(n); run;',
                       'data d; set raw; do i=2 to 1; b=reverse(n); end; run;'):
            for rows in ([],[{'n':7}]):
                with self.subTest(source=source,rows=rows),self.assertRaisesRegex(ValueError,'REVERSE'):
                    execute(source,{'raw':{'schema':{'n':'number'},'rows':rows}})

    def test_filtered_inputs_still_validate_reverse_type(self):
        with self.assertRaisesRegex(ValueError,'REVERSE'):
            execute('data d; set raw; where n=0; x=length(reverse(n)); run;',
                    {'raw':{'schema':{'n':'number'},'rows':[{'n':7}]}})

    def test_invalid_literal_values_refuse_even_without_rows(self):
        for value in ("''","7",'.A'):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'REVERSE'):
                execute(f'data d; set raw; x=reverse({value}); run;',{'raw':{'schema':{},'rows':[]}})

    def test_ascii_macro_guards_cover_unused_prior_and_zero_trip_values(self):
        for source in ("data d; x=reverse('ab'); unused='é'; run;",
                       'data prior; unused="&name"; run; data d; x=reverse(\'ab\'); run;',
                       'data d; do i=2 to 1; x=reverse(\'ab\'); end; unused="%call"; run;'):
            job = build_job(source)
            self.assertEqual(job.code,2,source)
            self.assertIsNone(job.result)

    def test_printable_quoted_tokens_and_ampersand_in_single_quotes(self):
        result = execute("data d; x=reverse('a;!!b'); y=reverse('&x'); run;")
        self.assertEqual(result['datasets']['d']['rows'][0],{'x':'b!!;a','y':'x&'})

    def test_later_bad_runtime_value_is_atomic(self):
        source='data _null_; set raw; b=reverse(a); put b; run;'
        inputs={'raw':{'schema':{'a':{'type':'character','length':2}},'rows':[{'a':'ab'},{'a':'é'}]}}
        printed=io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'inputs.json';path.write_text(json.dumps(inputs))
            job=build_job(source,path)
            self.assertEqual(job.code,1)
            self.assertIsNone(job.result)
        with contextlib.redirect_stdout(printed),self.assertRaisesRegex(ValueError,'REVERSE'):
            exec(translate(source).code,{'inputs':inputs})
        self.assertEqual(printed.getvalue(),'')

    def test_existing_blank_put_and_cpp_boundaries_remain(self):
        with self.assertRaises(ValueError):execute("data _null_; x=reverse('   '); put x; run;")
        self.assertEqual(build_job("data _null_; x=reverse('ab'); put x; run;",target='cpp').code,2)

    def test_helper_boundary_and_type_refusals(self):
        self.assertEqual(len(sas_reverse('x'*32767)),32767)
        for value in ('',None,True,7,{'missing':'A'},'x'*32768,'é','a\tb','a\x00b'):
            with self.subTest(value=str(value)[:20]),self.assertRaises(ValueError):sas_reverse(value)


class ReverseCorpusTests(unittest.TestCase):
    def test_unmodified_external_program_hashes_job_and_independent_r(self):
        path=ROKU_CORPUS/'reverse_a_string.sas'
        if not path.is_file():self.skipTest('Roku corpus not present')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),SOURCE_SHA)
        source=path.read_text();translation=translate(source)
        self.assertFalse(translation.blocked,translation.tickets)
        namespace={};printed=io.StringIO()
        with contextlib.redirect_stdout(printed):exec(translation.code,namespace)
        result=namespace['result']
        self.assertEqual(hashlib.sha256(printed.getvalue().encode()).hexdigest(),STDOUT_SHA)
        packed=json.dumps(result,sort_keys=True,separators=(',',':')).encode()
        self.assertEqual(hashlib.sha256(packed).hexdigest(),RESULT_SHA)
        records=program_records(path)
        self.assertEqual(len(records),2)
        self.assertEqual(result,{'datasets':{},'log':records})
        self.assertEqual(hashlib.sha256(('\n'.join(records)+'\n').encode()).hexdigest(),STDOUT_SHA)
        job=build_job(source)
        self.assertEqual(job.code,0)
        self.assertTrue(job.receipt['accepted'])
        self.assertEqual(job.receipt['source_sha256'],SOURCE_SHA)
        self.assertEqual(job.result,result)
        print('VERIFIED corpus: reverse_a_string.sas; source/stdout/complete-result hashes; independent base R; no live SAS')
