"""Composed bounded string evidence for maintainer review, no live SAS."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from .emit_py import translate
from .job import build_job


def execute(source):
    translated = translate(source)
    if translated.blocked:
        raise AssertionError(translated.tickets)
    namespace, printed = {}, io.StringIO()
    with contextlib.redirect_stdout(printed):
        exec(translated.code, namespace)
    return namespace['result'], printed.getvalue()


class StringCompositionTests(unittest.TestCase):
    def test_reverse_concat_and_concat_reverse_preserve_operand_widths(self):
        source = ("data d; length a b $4; a='XY'; b='Q'; "
                  "r=reverse(a!!b); s=reverse(a)||reverse(b); run;")
        result, printed = execute(source)
        self.assertEqual(printed, '')
        self.assertEqual(result['datasets']['d'], {
            'schema': {'a': {'type': 'character', 'length': 4},
                       'b': {'type': 'character', 'length': 4},
                       'r': {'type': 'character', 'length': 8},
                       's': {'type': 'character', 'length': 8}},
            'rows': [{'a': 'XY  ', 'b': 'Q   ', 'r': '   Q  YX', 's': '  YX   Q'}]})

    def test_loop_assignments_share_static_character_schema(self):
        source = ("data d; length a b $4; do i=1 to 2; a='XY'; "
                  "b=reverse(a); c=a!!b; n=_n_; output; end; run;")
        result, printed = execute(source)
        self.assertEqual(printed, '')
        dataset = result['datasets']['d']
        self.assertEqual(dataset['schema']['c'], {'type': 'character', 'length': 8})
        self.assertEqual(dataset['rows'], [
            {'a': 'XY  ', 'b': '  YX', 'i': float(i), 'c': 'XY    YX', 'n': 1.}
            for i in (1, 2)])

    def test_direct_catx_then_reverse_keeps_first_concat_target_width(self):
        source = ("data d; length a b $4; a=' A '; b='B'; c=a!!b; "
                  "c=catx('|',a,b); r=reverse(c); run;")
        result, _ = execute(source)
        dataset = result['datasets']['d']
        self.assertEqual(dataset['schema']['c'], {'type': 'character', 'length': 8})
        self.assertEqual(dataset['schema']['r'], {'type': 'character', 'length': 8})
        self.assertEqual(dataset['rows'][0]['c'], 'A|B     ')
        self.assertEqual(dataset['rows'][0]['r'], '     B|A')

    def test_operator_tokens_inside_literals_are_not_structure(self):
        result, _ = execute("data d; a='a!!b'; c=reverse(a)||'|'; run;")
        self.assertEqual(result['datasets']['d']['rows'][0]['c'], 'b!!a|')

    def test_later_catx_capacity_failure_cannot_publish_prior_records(self):
        source = ("data prior; put 'earlier'; run; data d; length a b $2; set raw; "
                  "c='xx'; c=catx('|',a,b); put c; run;")
        inputs = {'raw': {'schema': {'a': {'type': 'character', 'length': 2},
                                     'b': {'type': 'character', 'length': 2}},
                          'rows': [{'a': 'A', 'b': ' '}, {'a': 'AA', 'b': 'BB'}]}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'inputs.json'; path.write_text(json.dumps(inputs))
            job = build_job(source, path)
        self.assertEqual(job.code, 1)
        self.assertFalse(job.receipt['accepted'])
        self.assertIsNone(job.result)
        translated = translate(source)
        self.assertFalse(translated.blocked, translated.tickets)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed), self.assertRaises(ValueError):
            exec(translated.code, {'inputs': inputs})
        self.assertEqual(printed.getvalue(), '')

    def test_nested_catx_remains_deferred_after_reverse_wiring(self):
        for source in ("data d; c=reverse(catx('|','A','B')); run;",
                       "data d; c='X'||catx('|','A','B'); run;",
                       "data d; c=catx('|',reverse('A'),'B'); run;"):
            with self.subTest(source=source):
                job = build_job(source)
                self.assertEqual(job.code, 2)
                self.assertIsNone(job.result)


    def test_substr_quarantine_covers_all_new_entry_points_and_steps(self):
        sources = (
            "data d; length a b $5; a=substr('ABCDE',2,3); run;",
            "data prior; x=substr('ABCDE',2,3); run; data d; r=reverse('AB'); run;",
            "data prior; x=length(substr('ABCDE',2,3)); run; data d; c='A'!!'B'; run;",
            "data d; do i=2 to 1; x=substr('ABCDE',2,3); end; c=catx('|','A','B'); run;",
            "data d; set raw; where substr(a,1,1)='A'; r=reverse(a); run;",
        )
        for source in sources:
            with self.subTest(source=source):
                job = build_job(source)
                self.assertEqual(job.code, 2)
                self.assertIsNone(job.result)
                self.assertIn('substr', str(job.receipt['tickets']).lower())

    def test_quarantine_does_not_treat_literal_text_as_a_function_call(self):
        job = build_job("data d; a='substr(x,1,2)'; b=reverse(a); c=a!!b; run;")
        self.assertEqual(job.code, 0)
        self.assertTrue(job.receipt['accepted'])
        # Legacy-only source keeps its recorded path pending the separate repair.
        legacy = build_job("data d; length a $5; a='ABCDE'; x=substr(a,2,3); run;")
        self.assertEqual(legacy.code, 0)
        self.assertTrue(legacy.receipt['accepted'])

    def test_where_input_width_is_independent_of_output_length(self):
        inputs = {'raw': {'schema': {'a': {'type': 'character', 'length': 2}},
                          'rows': [{'a': 'AB'}]}}
        for width in (1, 4):
            for predicate in ("reverse(a)='BA'", "length(a||'C')=3"):
                source = f'data d; length a ${width}; set raw; where {predicate}; run;'
                with self.subTest(width=width, predicate=predicate), tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / 'inputs.json'; path.write_text(json.dumps(inputs))
                    job = build_job(source, path)
                    self.assertEqual(job.code, 0, job.receipt)
                    self.assertEqual(job.result['datasets']['d'], {
                        'schema': {'a': {'type': 'character', 'length': width}},
                        'rows': [{'a': 'A' if width == 1 else 'AB  '}]})
