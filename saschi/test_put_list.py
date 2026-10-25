"""DS-024 integration boundaries. Repository evidence, not live-SAS output."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from sas_semantics import sas_put_character_list
from .emit_py import translate
from .job import build_job as _build_job
from .parser import Kind, Statement, Token, split_statements, tokenize
from .plan import compile_plan
from .rules import load_rulebook, route_statement
from .runtime import run_plan


def build_job(source, inputs=None, **kwargs):
    if inputs is None:
        return _build_job(source, **kwargs)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'inputs.json'
        path.write_text(json.dumps(inputs), encoding='utf-8')
        return _build_job(source, path, **kwargs)


def catalog(rows, *, width=10, fmt=None):
    spec = {'type': 'character', 'length': width}
    if fmt:
        spec['format'] = fmt
    return {'raw': {'schema': {'c': spec}, 'rows': [{'c': row} for row in rows]}}


class CharacterListPutTests(unittest.TestCase):
    def execute(self, source, inputs=None):
        translation = translate(source)
        self.assertFalse(translation.blocked, translation.tickets)
        namespace = {'inputs': inputs or {}}
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            exec(translation.code, namespace)
        return namespace['result'], captured.getvalue()

    def test_mixed_items_have_distinct_spacing_and_preserve_pdv(self):
        result, printed = self.execute("data d; c='  A  '; d='B'; put '[' c ']' d; run;")
        self.assertEqual(result['log'], ['[A ]B '])
        self.assertEqual(printed, '[A ]B \n')
        self.assertEqual(result['datasets']['d']['rows'], [{'c': '  A  ', 'd': 'B'}])
        self.assertEqual(set(result['datasets']['d']['schema']), {'c', 'd'})

    def test_variable_values_are_data_and_quote_literals_decode(self):
        result, _ = self.execute("data _null_; set raw; put 'O''Neil:' c '!' ''; run;",
                                 catalog(['&name %call', 'a  b'], width=20))
        self.assertEqual(result['log'], ["O'Neil:&name %call !'", "O'Neil:a  b !'"])

    def test_source_macros_refuse_across_the_complete_program(self):
        for source in ('data _null_; c="&name"; put c; run;',
                       'data _null_; c="%upcase(ab)"; put c; run;',
                       'data _null_; c=substr("&name",1,2); put c; run;',
                       'data _null_; if 1 then c="&name"; put c; run;',
                       'data _null_; c="A"; if 0 then unused="&name"; put c; run;',
                       'data _null_; c="A"; put c; later="&name"; run;',
                       'data raw; c="%upcase(ab)"; run; data _null_; set raw; put c; run;'):
            job = build_job(source)
            self.assertEqual(job.code, 2, source)
            self.assertIsNone(job.result)
            self.assertIn('macro review', str(job.receipt['tickets']))
        result, _ = self.execute("data raw; c='&name %upcase(ab)'; run; data _null_; set raw; put c; run;")
        self.assertEqual(result['log'], ['&name %upcase(ab) '])

    def test_character_width_is_applied_before_output(self):
        result, _ = self.execute("data d; length c $3; c='ABCDEF'; put '[' c ']'; run;")
        self.assertEqual(result['log'], ['[ABC ]'])
        self.assertEqual(result['datasets']['d']['rows'], [{'c': 'ABC'}])

    def test_function_result_and_conditional_assignment(self):
        result, _ = self.execute("data _null_; if 1 then c='a'; d=substr(c,1,1); put c d; run;")
        self.assertEqual(result['log'], ['a a '])

    def test_mod_predicate_composes_with_character_output(self):
        result, printed = self.execute(
            "data d; length c $5; c='zero'; if mod(-7,3)=-1 then c='minus'; put '[' c ']'; run;")
        self.assertEqual(result['log'], ['[minus ]'])
        self.assertEqual(printed, '[minus ]\n')
        self.assertEqual(result['datasets']['d']['rows'], [{'c': 'minus'}])

    def test_iteration_subsetting_and_empty_input(self):
        inputs = catalog([' A ', 'B'])
        source = "data _null_; set raw; put '[' c ']'; if _n_=1; put c; run;"
        result, _ = self.execute(source, inputs)
        self.assertEqual(result['log'], ['[A ]', 'A ', '[B ]'])
        result, _ = self.execute(source, catalog([]))
        self.assertEqual(result['log'], [])

    def test_put_runs_before_explicit_output_without_extra_rows(self):
        result, _ = self.execute("data d; c='A'; put c; output; put c; run;")
        self.assertEqual(result['log'], ['A ', 'A '])
        self.assertEqual(result['datasets']['d']['rows'], [{'c': 'A'}])

    def test_old_literal_and_named_paths_are_unchanged(self):
        result, _ = self.execute("data _null_; c=' A '; put 'x' 'y'; put c=; put c; run;")
        self.assertEqual(result['log'], ['xy', 'c= A', 'A '])

    def test_source_provenance_and_route(self):
        plan = compile_plan("data _null_; c='A';\nput '[' c ']'; run;")
        self.assertEqual(plan.matched, [('put-character-list', 'DS-024', 2)])
        self.assertEqual(plan.steps[0].operations[-1].line, 2)
        self.assertEqual(route_statement("put '[' c ']'"), ('put-character-list', 'DS-024'))
        self.assertEqual(route_statement('put c'), ('put-character-list', 'DS-024'))
        self.assertEqual(route_statement("put 'a' 'b'"), ('put-literal', 'DS-023'))
        self.assertIn('verify_put_list.py', load_rulebook()['DS-024'].validation_test)

    def test_original_spans_preserve_parser_text_and_equality(self):
        source = "put 'a''b' /* comment */ c;"
        stmt = split_statements(source)[0]
        self.assertEqual(stmt, Statement("put 'a''b' c", 1))
        self.assertEqual(stmt.tokens[1], Token(Kind.STRING, "'a''b'", 1))
        for token in stmt.tokens:
            self.assertEqual(source[token.start:token.end], token.text)
        self.assertEqual(tokenize("'41'x")[1], Token(Kind.WORD, 'x', 1))

    def test_suffix_and_prefix_adjacency_are_refused(self):
        for name in ('x', 'n', 'd', 'dt', 't', 'b', 'dog', 'then', 'neighbor'):
            for literal in ("'41'", "'a''b'", '"a""b"'):
                source = f"data _null_; {name}='A'; put {literal}{name}; run;"
                with self.subTest(source=source):
                    job = build_job(source)
                    self.assertEqual(job.code, 2)
                    self.assertIsNone(job.result)
                    self.assertIn('source whitespace', str(job.receipt['tickets']))

    def test_whitespace_separation_and_conservative_comment_boundary(self):
        for gap in (' ', '\n', '\t', ' /* c */', '\n/* c */'):
            result, _ = self.execute("data _null_; x='A'; put '41'" + gap + 'x; run;')
            self.assertEqual(result['log'], ['41A '])
        for gap in ('/*c*/', '/*c*/ ', '/*\nc*/'):
            job = build_job("data _null_; x='A'; put '41'" + gap + 'x; run;')
            self.assertEqual(job.code, 2)
        result, _ = self.execute("data _null_; x='A'; put x/*c*/'!'; run;")
        self.assertEqual(result['log'], ['A !'])

    def test_automatic_variables_and_put_control_keywords_refuse(self):
        for name in ('_n_', '_error_', '_infile_', '_file_', '_ods_', '_page_',
                     '_blankpage_', '_all_', '_numeric_', '_character_'):
            inputs = {'raw': {'schema': {name: {'type': 'character', 'length': 1}},
                              'rows': [{name: 'A'}]}}
            job = build_job('data _null_; set raw; put ' + name + '; run;', inputs)
            self.assertEqual(job.code, 2, name)
            self.assertIsNone(job.result)

    def test_numeric_missing_tagged_and_unknown_variables_refuse(self):
        for value in (7, None, {'missing': 'A'}):
            inputs = {'raw': {'schema': {'c': 'number'}, 'rows': [{'c': value}]}}
            job = build_job('data _null_; set raw; put c; run;', inputs)
            self.assertEqual(job.code, 1)
            self.assertIsNone(job.result)
        for rows in ([], [{'c': 1}]):
            inputs = {'raw': {'schema': {'c': 'number'}, 'rows': rows}}
            self.assertEqual(build_job('data _null_; set raw; put unknown; run;', inputs).code, 1)
        self.assertEqual(build_job('data _null_; put unknown; run;').code, 2)

    def test_attached_format_refuses_even_without_rows_or_after_length(self):
        for rows in ([], ['ab']):
            for source in ('data _null_; set raw; put c; run;',
                           'data _null_; length c $5; set raw; put c; run;',
                           'data d; length c $5; set raw; run; data _null_; set d; put c; run;'):
                job = build_job(source, catalog(rows, fmt='$UPCASE10.'))
                self.assertEqual(job.code, 1, (rows, source))
                self.assertIsNone(job.result)
                self.assertIn('unformatted character', str(job.receipt))

    def test_plain_assigned_copy_does_not_inherit_source_format(self):
        result, _ = self.execute('data _null_; set raw; d=c; put d; run;',
                                 catalog(['ab'], fmt='$UPCASE10.'))
        self.assertEqual(result['log'], ['ab '])

    def test_inherited_format_survives_length_and_by_without_put(self):
        result, _ = self.execute('data d; length c $10; set raw; by c; run;',
                                 catalog(['ab'], fmt='$UPCASE10.'))
        self.assertEqual(result['datasets']['d']['schema']['c']['format'], '$UPCASE10.')

    def test_lookup_empty_format_does_not_hide_driving_format(self):
        for defaults in ([], ['def']):
            for rows in ([], ['abc']):
                inputs = catalog(rows, fmt='$UPCASE10.')
                inputs['defaults'] = catalog(defaults)['raw']
                inputs['defaults']['schema']['c']['format'] = ''
                source = 'data _null_; if _n_=1 then set defaults; set raw; put c; run;'
                job = build_job(source, inputs)
                self.assertEqual(job.code, 1, (defaults, rows))
                self.assertIn('unformatted character', str(job.receipt))

    def test_where_cannot_skip_descriptor_validation(self):
        for inputs, predicate in ((catalog(['abc'], fmt='$UPCASE10.'), "c='absent'"),
                                  ({'raw': {'schema': {'c': 'number'}, 'rows': [{'c': 7}]}}, 'c=0')):
            source = 'data _null_; set raw; where ' + predicate + '; put c; run;'
            job = build_job(source, inputs)
            self.assertEqual(job.code, 1)
            self.assertIsNone(job.result)
            self.assertIn('unformatted character', str(job.receipt))

    def test_labels_and_encodings_do_not_imply_a_format(self):
        inputs = catalog([' A '])
        inputs['raw']['schema']['c']['label'] = 'Caption'
        inputs['raw']['encoding'] = 'latin-1'
        result, _ = self.execute('data _null_; set raw; put c; run;', inputs)
        self.assertEqual(result['log'], ['A '])

    def test_value_refusals_are_atomic(self):
        for value in ('', '   ', None, 'café', 'a\tb', 'a\nb', 'x' * 64):
            inputs = catalog(['A', value], width=64)
            source = "data _null_; set raw; put 'before'; put c; run;"
            job = build_job(source, inputs)
            self.assertEqual(job.code, 1, value)
            self.assertIsNone(job.result)
            self.assertFalse(job.receipt['accepted'])
            translation = translate(source)
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured), self.assertRaises(ValueError):
                exec(translation.code, {'inputs': inputs})
            self.assertEqual(captured.getvalue(), '')

    def test_record_bound_includes_final_separator_and_all_literals(self):
        result, _ = self.execute('data _null_; set raw; put c; run;', catalog(['x' * 63], width=64))
        self.assertEqual(result['log'], ['x' * 63 + ' '])
        source = "data _null_; set raw; put '[' c ']'; run;"
        self.assertEqual(build_job(source, catalog(['x' * 62], width=64)).code, 1)
        self.assertEqual(build_job("data _null_; c='A'; put '" + 'x' * 63 + "' c; run;").code, 2)

    def test_formats_numeric_literals_modifiers_and_conditional_put_refuse(self):
        for statement in ('put c $10.', 'put c : $10.', 'put c ~', 'put c @',
                          'put c @@', 'put @4 c', 'put c /', 'put c +2',
                          "put c= 'x'", 'put c 7', 'put (c)', 'put c*2',
                          'if 1 then put c', 'file log; put c'):
            job = build_job("data _null_; c='A'; " + statement + '; run;')
            self.assertEqual(job.code, 2, statement)
            self.assertIsNone(job.result)

    def test_forged_plan_revalidated_without_rows(self):
        for items in (None, [], ['c'], [{'kind': 'numeric', 'value': '1'}],
                      [{'kind': 'variable', 'value': 'c', 'format': '$10.'}],
                      [{'kind': 'literal', 'value': '"&name"'}, {'kind': 'variable', 'value': 'c'}]):
            plan = compile_plan('data _null_; set raw; put c; run;').to_dict()
            plan['steps'][0]['operations'][-1]['args']['items'] = items
            with self.subTest(items=items), self.assertRaises(ValueError):
                run_plan(plan, catalog([]))
        for items in (None, [], 'c', [1], [{'kind': 'character', 'value': 'x', 'extra': 1}]):
            with self.subTest(items=items), self.assertRaises(ValueError):
                sas_put_character_list(items)

    def test_cpp_target_has_no_character_list_fallback(self):
        job = build_job("data _null_; c='A'; put c; run;", target='cpp')
        self.assertEqual(job.code, 2)
        self.assertIsNone(job.result)
        self.assertFalse(job.receipt['accepted'])


if __name__ == '__main__':
    unittest.main()
