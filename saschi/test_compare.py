"""Adversarial comparator witnesses; a type error must never become a match."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from .compare import equal, table_equal
from .cli import main
import synth


class TypedComparisonTests(unittest.TestCase):
    def test_type_boundaries(self):
        for a, b in [(1., '1.0'), (1, True), (0, False), (None, ''), ({'missing':'A'}, None),
                     ({'missing':'A'}, {'missing':'B'}), ('007', '7')]:
            with self.subTest(a=a, b=b):
                self.assertFalse(equal(a, b))
                self.assertFalse(synth.col_eq([a], [b]))

    def test_binary64_boundary_is_not_rounded_during_comparison(self):
        self.assertTrue(equal(2**53, float(2**53)))
        self.assertFalse(equal(2**53+1, float(2**53)))
        self.assertTrue(equal(10**500, 10**500))

    def test_tolerance_is_explicit_and_missing_policy_is_local(self):
        self.assertFalse(equal(1., 1.00000000001))
        self.assertTrue(equal(1., 1.00000000001, atol=1e-10))
        self.assertFalse(equal(None, float('nan')))
        self.assertTrue(synth.col_eq([None], [float('nan')]))
        self.assertFalse(equal(float('inf'), float('inf')))
        for tolerance in (-1, float('inf'), float('nan')):
            with self.assertRaises(ValueError):
                equal(1, 1, atol=tolerance)

    def test_shape_and_metadata(self):
        base = {'schema': {'id':'number', 'x':'number'}, 'rows':[{'id':1., 'x':2.}, {'id':2.,'x':3.}]}
        variants = [dict(base, rows=base['rows'][::-1]), dict(base, rows=base['rows'][:1]),
                    dict(base, schema={'x':'number', 'id':'number'}), dict(base, label='other'),
                    dict(base, schema={'id': {'type':'number', 'format':'Z3.'}, 'x':'number'})]
        self.assertTrue(table_equal(base, base))
        for variant in variants:
            self.assertFalse(table_equal(base, variant))
        self.assertFalse(synth.frames_equal({'a':[1], 'b':[2]}, {'b':[2], 'a':[1]}))

    def test_cli_does_not_accept_boolean_as_number(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/'job.sas').write_text('data d; x=1; run;')
            (root/'expected.json').write_text(json.dumps({'d':{'schema':{'x':'number'},'rows':[{'x':True}]}}))
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(['run', str(root/'job.sas'), '--expect', str(root/'expected.json'), '--output', str(root/'out')])
            self.assertEqual(code, 1)
            receipt = json.loads((root/'out/receipt.json').read_text())
            self.assertFalse(receipt['accepted'])
            self.assertEqual(receipt['comparison'], 'failed')
            self.assertFalse((root/'out/result.json').exists())
