"""DS-025 execution and external corpus evidence, not a live SAS capture."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import unittest

from examples.verify_put_all import program_records
from sas_semantics import sas_put_all
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .rules import load_rulebook, route_statement
from .runtime import run_plan
from .test_parser import ROKU_CORPUS

TAIL = '_ERROR_=0 _N_=1 '


def emitted(source):
    translation = translate(source)
    if translation.blocked:
        raise AssertionError(translation.tickets)
    namespace, output = {}, io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(translation.code, namespace)
    return namespace['result'], output.getvalue()


class AllPutTests(unittest.TestCase):
    def test_complete_pdv_order_and_original_name_spelling(self):
        result, printed = emitted("data d; Z=3; b=length(c); A='  Q  '; put _all_; run;")
        self.assertEqual(result['log'], ['Z=3 b=12 c=. A=Q ' + TAIL])
        self.assertEqual(printed, result['log'][0] + '\n')
        table = result['datasets']['d']
        self.assertEqual(list(table['schema']), ['z', 'b', 'c', 'a'])
        self.assertEqual(table['rows'], [{'z': 3., 'b': 12., 'c': None, 'a': '  Q  '}])

    def test_later_numeric_reference_is_visible_before_assignment(self):
        result, _ = emitted('data d; put _ALL_; Later=7; put _all_; run;')
        self.assertEqual(result['log'], ['Later=. ' + TAIL, 'Later=7 ' + TAIL])
        self.assertNotIn('_n_', result['datasets']['d']['schema'])
        self.assertNotIn('_error_', result['datasets']['d']['rows'][0])

    def test_declared_width_and_safe_substr_then_length(self):
        result, _ = emitted("data d; length Word $3; Word='peppermint'; Part=substr(Word,2,2); n=length(Part); put _all_; run;")
        self.assertEqual(result['log'], ['Word=pep Part=ep n=2 ' + TAIL])

    def test_names_that_match_functions_keep_variable_case(self):
        result, _ = emitted('data _null_; n=LENGTH(3); Length=7; PUT _ALL_; run;')
        self.assertEqual(result['log'], ['n=12 Length=7 ' + TAIL])
        result, _ = emitted('data _null_; n=1E3; e3=7; put _all_; run;')
        self.assertEqual(result['log'], ['n=1000 e3=7 ' + TAIL])
        result, _ = emitted('data _null_; n=length(.A); a=7; put _all_; run;')
        self.assertEqual(result['log'], ['n=12 a=7 ' + TAIL])

    def test_scalar_automatic_reference_and_steps_reset(self):
        result, _ = emitted('data _null_; n=_n_; put _all_; run; data _null_; put _all_; run;')
        self.assertEqual(result['log'], ['n=1 ' + TAIL, TAIL])

    def test_explicit_output_preserves_data_and_does_not_repeat_put(self):
        result, _ = emitted('data d; n=1; output; n=2; put _all_; output; run;')
        self.assertEqual(result['datasets']['d']['rows'], [{'n': 1.}, {'n': 2.}])
        self.assertEqual(result['log'], ['n=2 ' + TAIL])

    def test_route_and_rule_provenance(self):
        self.assertEqual(route_statement('PUT _ALL_;'), ('put-all', 'DS-025'))
        plan = compile_plan('data _null_;\nput _all_; run;')
        self.assertEqual(plan.matched, [('put-all', 'DS-025', 2)])
        self.assertIn('verify_put_all.py', load_rulebook()['DS-025'].validation_test)

    def test_source_boundaries_refuse_before_execution(self):
        bodies = ['set raw; put _all_', 'if 1 then n=7; put _all_',
                  'retain n 0; put _all_', 'output; put _all_', 'put _all_ n', 'put _all_=',
                  "put '[' _all_ ']'", 'put _numeric_', 'put _character_',
                  'file print; put _all_', 'put _all_ @', 'put _all_ /',
                  'n=1; format n 8.2; put _all_', 'n=round(1,1); put _all_']
        for body in bodies:
            with self.subTest(body=body):
                job = build_job('data _null_; ' + body + '; run;')
                self.assertEqual(job.code, 2)
                self.assertIsNone(job.result)

    def test_macro_and_encoding_guards_cover_the_complete_program(self):
        for source in ('data _null_; put _all_; x="&name"; run;',
                       'data _null_; x="%call(x)"; run; data _null_; put _all_; run;',
                       "data _null_; n=length('é'); put _all_; run;"):
            job = build_job(source)
            self.assertEqual(job.code, 2)
        result, _ = emitted("data _null_; c='&x %go'; put _all_; run;")
        self.assertEqual(result['log'], ['c=&x %go ' + TAIL])

    def test_runtime_refusals_do_not_publish_partial_output(self):
        bodies = ['n=1.5; put _all_', 'n=100000000000; put _all_',
                  'n=.A; put _all_', "c=' '; put _all_", 'n=1+2; put _all_',
                  "c=substr('abc',0,2); put _all_",
                  "c=substr('abc',2,9); put _all_", 'c=substr(.,1,1); put _all_',
                  "c='A'; put _all_; c=' '; put _all_", 'n=1; put _all_; n=mod(7,3)',
                  "n=lengthc(''); put _all_"]
        for body in bodies:
            source = 'data d; ' + body + '; run;'
            with self.subTest(body=body):
                job = build_job(source)
                self.assertEqual(job.code, 1)
                self.assertIsNone(job.result)
                printed = io.StringIO()
                with contextlib.redirect_stdout(printed), self.assertRaises(ValueError):
                    exec(translate(source).code, {})
                self.assertEqual(printed.getvalue(), '')

    def test_plan_descriptor_and_display_validation(self):
        for mutate in ('format', 'spelling', 'arguments', 'reserved'):
            plan = compile_plan('data d; n=1; put _all_; run;').to_dict()
            step = plan['steps'][0]
            if mutate == 'format':
                step['operations'].insert(0, {'kind': 'declare', 'line': 1,
                    'args': {'name': 'n', 'spec': {'type': 'number', 'format': '8.2'}}})
            elif mutate == 'spelling': step['display_names']['n'] = 'unrelated'
            elif mutate == 'arguments': step['operations'][-1]['args']['names'] = ['n']
            else: step['operations'][0]['args']['name'] = '_error_'
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                run_plan(plan)

    def test_width_includes_names_automatics_and_last_separator(self):
        result, printed = emitted("data _null_; x='" + 'q' * 45 + "'; put _all_; run;")
        self.assertEqual(len(result['log'][0]), 64)
        self.assertEqual(len(printed), 65)
        self.assertEqual(build_job("data _null_; x='" + 'q' * 46 + "'; put _all_; run;").code, 1)

    def test_invalid_reference_fields_refuse(self):
        for value in (None, 'x', {}, [1], [{'name': 'a', 'kind': 'number', 'value': 1, 'format': '8.'}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                sas_put_all(value)

    def test_cpp_stays_blocked(self):
        job = build_job('data _null_; n=1; put _all_; run;', target='cpp')
        self.assertEqual(job.code, 2)
        self.assertIsNone(job.result)


# These hashes describe external source and independently hand-derived output.
# No corpus source or corpus-derived text is copied into this repository.
CORPUS = {
    'string_length.sas': ('3bc3c50966b3c74e2171e4f22492efb6f3da581662b0fd257f2bda672bbc879f',
                          '4bce911a1d8f03fdc6a47aa2cbfd60dd4c0bf274870039d60f30361d3ae29988', 'e31b4bb926a3e133bc7089c47215b453aefcae8450c3c78ca98104a9b9556f2b'),
    'substring.sas': ('acba68aa47ae7970221841a7c7f459ce5c47d8401a7ace72d1bb95f70801ded9',
                      '3f3ffc0f67eee873fe7edf706ebc161aab837c67ec1485635bf17e1a2f422e08', '084e0b62ebf99ce307d5df71a69e740e6995a1d415595bf064de6e3c24e55103'),
}


class CorpusProgramsTests(unittest.TestCase):
    def check_program(self, name):
        path = ROKU_CORPUS / name
        if not path.is_file():
            self.skipTest('Roku corpus not present')
        source_hash, stdout_hash, result_hash = CORPUS[name]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), source_hash)
        source = path.read_text()
        result, printed = emitted(source)
        self.assertEqual(hashlib.sha256(printed.encode()).hexdigest(), stdout_hash)
        encoded = json.dumps(result, sort_keys=True, separators=(',', ':')).encode()
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), result_hash)
        independent = program_records(path)
        self.assertEqual(result['log'], independent)
        self.assertEqual(hashlib.sha256(('\n'.join(independent) + '\n').encode()).hexdigest(), stdout_hash)
        job = build_job(source)
        self.assertTrue(job.receipt['accepted'])
        self.assertEqual(job.result, result)
        self.assertEqual(job.receipt['source_sha256'], source_hash)
        self.assertEqual(job.receipt['tickets'], [])
        self.assertEqual(result['datasets'], {})
        print(f'VERIFIED corpus: {name}; source={source_hash}; stdout={stdout_hash}; independent base R agrees; no live SAS')
        return {'file': name, 'source_sha256': source_hash, 'stdout_sha256': stdout_hash,
                'result_sha256': result_hash, 'base_r_agrees': True, 'passed': True}

    def test_string_length_unmodified_program(self):
        self.check_program('string_length.sas')

    def test_substring_unmodified_program(self):
        self.check_program('substring.sas')


if __name__ == '__main__':
    unittest.main()
