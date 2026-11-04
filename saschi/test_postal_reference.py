"""Pinned-data, cache isolation and offline controls for the finite postal policy."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from . import postal_reference as reference

ROOT=Path(__file__).resolve().parents[1]


class PostalReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.path=reference.reference_path();cls.raw=cls.path.read_bytes();cls.mapping=reference.load_reference()

    def test_exact_raw_and_semantic_pins_domain_leading_zero(self):
        self.assertEqual(len(self.raw),reference.RAW_BYTES);self.assertEqual(hashlib.sha256(self.raw).hexdigest(),reference.RAW_SHA256)
        self.assertEqual(len(self.mapping),19);self.assertTrue(set(self.mapping)==set(reference.DOMAIN),'finite-domain identities differ');self.assertTrue('01040' in self.mapping,'leading-zero identity is absent');reference._semantic_pin(self.mapping)
        self.assertTrue(reference.zip_state('01040',self.mapping)==self.mapping['01040'],'leading-zero mapping differs')

    def test_numeric_short_unknown_extended_unicode_zip_refusal(self):
        for value in [1040,True,None,'1040','00000','59017','01040 ','01040-0000','１２３４５']:
            with self.subTest(value=value),self.assertRaises(ValueError):reference.zip_state(value,self.mapping)

    def test_loader_never_fetches(self):
        with patch.object(reference,'urlopen',side_effect=AssertionError('runtime network')):self.assertTrue(reference.load_reference()==self.mapping,'complete qualified mapping differs')

    def test_missing_cache_never_fetches(self):
        with tempfile.TemporaryDirectory(prefix='saschi-postal-missing-') as temp,patch.object(reference,'urlopen',side_effect=AssertionError('runtime network')):
            with self.assertRaisesRegex(ValueError,'prepare_postal_reference'):reference.load_reference(temp)

    def test_corrupt_raw_refuses_and_is_not_replaced(self):
        with tempfile.TemporaryDirectory(prefix='saschi-postal-corrupt-') as temp:
            p=reference.reference_path(temp);p.write_bytes(b'not a workbook')
            with self.assertRaises(ValueError):reference.prepare(temp,fetch=lambda url:self.raw)
            self.assertTrue(p.read_bytes()==b'not a workbook','conflicting cache bytes were replaced')

    def test_raw_rechecked_after_decode_cache_hit(self):
        with tempfile.TemporaryDirectory(prefix='saschi-postal-recheck-') as temp:
            p=reference.prepare(temp,fetch=lambda url:self.raw);self.assertTrue(reference.load_reference(temp)==self.mapping,'complete qualified mapping differs')
            damaged=bytearray(self.raw);damaged[-1]^=1;p.write_bytes(damaged)
            with self.assertRaises(ValueError):reference.load_reference(temp)

    def test_caller_map_mutation_does_not_change_cached_reference(self):
        value=reference.load_reference();value['01040']='XX';self.assertTrue(reference.load_reference()==self.mapping,'complete qualified mapping differs')
        with self.assertRaises(ValueError):reference._semantic_pin(value)

    def test_semantic_shape_missing_domain_and_wrong_value_refuse(self):
        for value in [{},[],{**self.mapping,'99999':'XX'},{key:value for key,value in self.mapping.items() if key!='01040'}]:
            with self.assertRaises(ValueError):reference._semantic_pin(value)

    def test_no_repo_git_or_symlink_cache(self):
        with self.assertRaises(ValueError):reference.reference_path(ROOT/'telemetry/forbidden-postal-cache')
        with tempfile.TemporaryDirectory(prefix='saschi-postal-paths-') as temp:
            area=Path(temp);repo=area/'repo';repo.mkdir();(repo/'.git').mkdir()
            with self.assertRaises(ValueError):reference.reference_path(repo/'cache')
            real=area/'real';real.mkdir();link=area/'link';link.symlink_to(real,target_is_directory=True)
            with self.assertRaises(ValueError):reference.reference_path(link)
            dest=area/'dest';dest.mkdir();(dest/'Zip_Locale_Detail.xlsx').symlink_to(self.path)
            with self.assertRaises(ValueError):reference.reference_path(dest)

    def test_explicit_preparation_pin_before_exclusive_write(self):
        with tempfile.TemporaryDirectory(prefix='saschi-postal-prepare-') as temp:
            cache=Path(temp)/'cache';calls=[]
            with self.assertRaises(ValueError):reference.prepare(cache,fetch=lambda url:b'bad')
            self.assertFalse(cache.exists())
            p=reference.prepare(cache,fetch=lambda url:(calls.append(url),self.raw)[1]);self.assertEqual(calls,[reference.URL]);self.assertTrue(p.read_bytes()==self.raw,'prepared workbook bytes differ')
            reference.prepare(cache,fetch=lambda url:(_ for _ in ()).throw(AssertionError('refetched')))

    def test_metadata_has_only_pins_policy_and_domain_size(self):
        value=reference.metadata();self.assertEqual(value['n_codes'],19);self.assertNotIn('mapping',value);self.assertIn('not live SAS',value['evidence'])

    def test_complete_expectation_and_witness_scratch_cannot_enter_go(self):
        sys.path.insert(0,str(ROOT/'examples'))
        from format_gate_common import external_temporary
        with external_temporary('postal-isolation-') as temp:self.assertFalse(Path(temp).resolve().is_relative_to(ROOT))
        with patch('tempfile.gettempdir',return_value=str(ROOT/'telemetry')):
            with self.assertRaises(ValueError):external_temporary('forbidden-')

    def test_preparation_cli_check_is_offline(self):
        run=subprocess.run([sys.executable,'tools/prepare_postal_reference.py','--check'],capture_output=True,text=True,cwd=ROOT,timeout=120)
        self.assertEqual(run.returncode,0,run.stderr);self.assertTrue(json.loads(run.stdout)['offline'])


if __name__=='__main__':unittest.main()
