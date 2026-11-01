"""Original mock bytes exercise acquisition refusal and offline cache behavior."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.vendor_sources import prepare_sources, read_manifest, validate_manifest, verify_sources


class VendorSourcesTests(unittest.TestCase):
    def setUp(self):
        self.area = tempfile.TemporaryDirectory()
        self.addCleanup(self.area.cleanup)
        self.base = Path(self.area.name)
        self.cache = self.base / 'cache'
        self.source = b'original mock source bytes\n'
        self.license = b'original mock license bytes\n'
        def item(path, body):
            return {'path': path, 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
                    'git_blob_sha1': hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest()}
        self.manifest = {'schema_version': 1, 'status': 'Original authored mock for cache tests only.',
                         'programs': [{'id': 'owned-mock', 'repository': 'fixture/owned-mock',
                                       'commit': '1' * 40, 'license_identifier': 'Apache-2.0',
                                       'source': item('examples/original mock.sas', self.source),
                                       'license': item('LICENSE', self.license)}]}
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        return self.license if url.endswith('/LICENSE') else self.source

    def test_prepare_pins_bytes_and_cached_reuse_is_offline(self):
        result = prepare_sources(self.manifest, self.cache, fetch=self.fetch)
        self.assertEqual(len(self.calls), 2)
        self.assertIn('original%20mock.sas', self.calls[0])
        self.assertEqual(result['owned-mock']['source'].read_bytes(), self.source)
        def no_network(_):
            raise AssertionError('cached preparation attempted network')
        self.assertEqual(prepare_sources(self.manifest, self.cache, fetch=no_network), result)
        self.assertEqual(verify_sources(self.manifest, self.cache), result)

    def test_missing_offline_cache_is_a_failure(self):
        with self.assertRaisesRegex(ValueError, 'missing'):
            verify_sources(self.manifest, self.cache)
        self.assertFalse(self.cache.exists())

    def test_wrong_download_refuses_before_any_body_write(self):
        def wrong_license(url):
            return b'wrong' if url.endswith('/LICENSE') else self.source
        with self.assertRaisesRegex(ValueError, 'immutable pin'):
            prepare_sources(self.manifest, self.cache, fetch=wrong_license)
        self.assertFalse(self.cache.exists())

    def test_corrupted_existing_cache_is_not_replaced(self):
        result = prepare_sources(self.manifest, self.cache, fetch=self.fetch)
        result['owned-mock']['source'].write_bytes(b'altered')
        count = len(self.calls)
        with self.assertRaisesRegex(ValueError, 'immutable pin'):
            prepare_sources(self.manifest, self.cache, fetch=self.fetch)
        self.assertEqual(len(self.calls), count)
        self.assertEqual(result['owned-mock']['source'].read_bytes(), b'altered')

    def test_unsafe_and_noncanonical_paths_refuse(self):
        for path in ['../escape.sas', '/absolute.sas', 'a//b.sas', 'a/./b.sas',
                     'a\\b.sas', 'drive:file.sas', '.', '']:
            with self.subTest(path=path):
                value = deepcopy(self.manifest)
                value['programs'][0]['source']['path'] = path
                with self.assertRaises(ValueError):
                    validate_manifest(value)

    def test_bad_identity_size_and_shape_refuse(self):
        changes = [('commit', 'main'), ('id', '../escape'), ('repository', 'https://elsewhere'),
                   ('license_identifier', 'unspecified'), ('source', None)]
        for key, bad in changes:
            with self.subTest(key=key):
                value = deepcopy(self.manifest)
                value['programs'][0][key] = bad
                with self.assertRaises(ValueError):
                    validate_manifest(value)
        value = deepcopy(self.manifest)
        value['programs'][0]['source']['bytes'] = True
        with self.assertRaises(ValueError):
            validate_manifest(value)

    def test_conflicting_shared_pin_and_duplicate_ids_refuse(self):
        value = deepcopy(self.manifest)
        value['programs'].append(deepcopy(value['programs'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            validate_manifest(value)
        value['programs'][1]['id'] = 'different-id'
        value['programs'][1]['source']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            validate_manifest(value)

    def test_symlinks_and_git_checkout_cache_refuse(self):
        real = self.base / 'real'
        real.mkdir()
        self.cache.symlink_to(real, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            prepare_sources(self.manifest, self.cache, fetch=self.fetch)
        self.cache.unlink()
        (real / '.git').mkdir()
        with self.assertRaisesRegex(ValueError, 'Git checkouts'):
            prepare_sources(self.manifest, real / 'cache', fetch=self.fetch)

    def test_symlink_body_refuses_without_following(self):
        result = prepare_sources(self.manifest, self.cache, fetch=self.fetch)
        source = result['owned-mock']['source']
        source.unlink()
        external = self.base / 'outside'
        external.write_bytes(self.source)
        source.symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            verify_sources(self.manifest, self.cache)

    def test_nested_git_checkout_refuses_before_download_or_read(self):
        marked = self.cache / 'fixture' / 'owned-mock'
        (marked / '.git').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'nested Git'):
            prepare_sources(self.manifest, self.cache, fetch=self.fetch)
        self.assertEqual(self.calls, [])
        with self.assertRaisesRegex(ValueError, 'nested Git'):
            verify_sources(self.manifest, self.cache)

    def test_duplicate_and_nonfinite_manifest_json_refuse(self):
        path = self.base / 'manifest.json'
        path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            read_manifest(path)
        path.write_text('{"schema_version":NaN}')
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            read_manifest(path)
        path.write_text(json.dumps(self.manifest))
        self.assertEqual(read_manifest(path), self.manifest)


if __name__ == '__main__':
    unittest.main()
