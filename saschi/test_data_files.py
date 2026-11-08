"""Original synthetic file contracts; no estate data or native-SAS proof."""
import hashlib
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from .data_files import DataFileError, load_data_file, load_data_files, write_parquet


PANDAS = importlib.util.find_spec('pandas') is not None
DUCKDB = importlib.util.find_spec('duckdb') is not None


def sas_fixture(*, endian='<', u64=False, missing_tag='A', encoding=20,
                numeric_width=8, empty=False, character_width=4,
                nul_padding=False, compressed=False, variable_metadata=True,
                last_numeric=False):
    """Construct a minimal uncompressed SAS container from original values.

    The file has one metadata page and one observation page. Its variables are
    amount, day (raw DATE format) and code (four UTF-8 bytes). Structural fields
    are the public SAS container layout, not copied fixture bytes.
    """
    header = bytearray(1024)
    header[:32] = bytes.fromhex('000000000000000000000000c2ea8160b31411cfbd92080009c7318c181f1011')
    header[37], header[70] = int(endian == '<'), encoding
    if u64:
        header[32] = ord('3')
    struct.pack_into(endian + 'III', header, 196, 1024, 4096, 2)
    integer, width, page_offset, pointer_width = ('Q', 8, 32, 24) if u64 else ('I', 4, 16, 12)
    rowsize = bytearray(808 if u64 else 480)
    rowsize[:4] = b'\xf7' * 4
    if last_numeric:
        character_width = 8
    row_length = 16 + character_width
    struct.pack_into(endian + integer, rowsize, 5 * width, row_length)
    struct.pack_into(endian + integer, rowsize, 6 * width, 0 if empty else 3)
    struct.pack_into(endian + integer, rowsize, 9 * width, 3)
    colsize = (b'\xf6' * 4).ljust(width, b'\0') + struct.pack(endian + integer, 3)
    text = bytearray(196 + width)
    text[:4] = b'\xfd\xff\xff\xff'
    if u64:
        text[4:8] = b'\xff' * 4
    struct.pack_into(endian + 'H', text, width, 196)
    strings = [b'amount', b'day', b'code', b'Amount label', b'DATE', b'Synthetic table']
    positions, at = [], 20
    for value in strings:
        text[width + at:width + at + len(value)] = value
        positions.append((at, len(value)))
        at += len(value)
    if compressed:
        text[width + 165:width + 173] = b'SASYZCRL'
    struct.pack_into(endian + 'HHH', rowsize, len(rowsize) - 130, 0, *positions[5])
    names = bytearray(2 * width + 36)
    names[:width] = b'\xff' * width
    for i in range(3):
        struct.pack_into(endian + 'HHH', names, width + 8 + i * 8, 0, *positions[i])
    attributes = bytearray(2 * width + 12 + 3 * (width + 8))
    attributes[:4] = b'\xfc\xff\xff\xff'
    if u64:
        attributes[4:8] = b'\xff' * 4
    for i, (offset, column_width, kind) in enumerate([(0, numeric_width, 1), (8, 8, 1), (16, character_width, 1 if last_numeric else 2)]):
        struct.pack_into(endian + integer + 'I', attributes, width + 8 + i * (width + 8), offset, column_width)
        attributes[2 * width + 14 + i * (width + 8)] = kind
    formats = []
    for i in range(3):
        data = bytearray(3 * width + 34)
        data[:4] = b'\xfe\xfb\xff\xff'
        if u64:
            data[4:8] = b'\xff' * 4
        if i == 0 and variable_metadata:
            struct.pack_into(endian + 'HHH', data, 3 * width + 28, 0, *positions[3])
        if i == 1 and variable_metadata:
            struct.pack_into(endian + 'HHH', data, 3 * width + 22, 0, *positions[4])
        formats.append(data)
    subheaders = [rowsize, colsize, text, names, attributes] + formats
    meta = bytearray(4096)
    struct.pack_into(endian + 'HHH', meta, page_offset, 0, len(subheaders), len(subheaders))
    at = 256
    for i, data in enumerate(subheaders):
        struct.pack_into(endian + integer * 2, meta, page_offset + 8 + i * pointer_width, at, len(data))
        meta[at:at + len(data)] = data
        at += len(data)
    page = bytearray(4096)
    struct.pack_into(endian + 'HHH', page, page_offset, 0 if compressed else 256, 0 if empty else 3, 3 if compressed else 0)
    tag_bits = 0xFFFF000000000000 | ((~ord(missing_tag)) & 255) << 40
    numbers = [struct.pack(endian + 'd', 12.5), tag_bits.to_bytes(8, 'little' if endian == '<' else 'big'),
               (0xFFFFD10000000000).to_bytes(8, 'little' if endian == '<' else 'big')]
    at = 256
    for row, code in enumerate([b'A', 'é'.encode(), b'']):
        number_bytes = numbers[row] + struct.pack(endian + 'd', row + 1)
        if last_numeric:
            code = struct.pack(endian + 'd', row + 1)
        if compressed:
            payload = b'\x8f' + number_bytes
            if code:
                payload += bytes([0x80 + len(code) - 1]) + code
            payload += bytes([0x70 if nul_padding else 0x60, character_width - len(code) - 17])
            struct.pack_into(endian + integer * 2, page, page_offset + 8 + row * pointer_width, at, len(payload))
            page[page_offset + 8 + row * pointer_width + 2 * width] = 4
            page[page_offset + 9 + row * pointer_width + 2 * width] = 1
            page[at:at + len(payload)] = payload
            at += len(payload)
        else:
            start = page_offset + 8 + row * row_length
            page[start:start + row_length] = number_bytes + code.ljust(character_width, b'\0' if nul_padding else b' ')
    return bytes(header + meta + page)


def xpt_fixture():
    """Original V5 transport records with numeric and tagged missing pins."""
    line = lambda value: value.encode('ascii').ljust(80)
    date = b'01JAN24:00:00:00'
    header = line('HEADER RECORD*******LIBRARY HEADER RECORD!!!!!!!000000000000000000000000000000')
    header += b'SAS     SAS     SASLIB'.ljust(24) + b'9.4'.ljust(8) + b'LINUX'.ljust(8) + b' ' * 24 + date
    header += line('01JAN24:00:00:00')
    header += b'HEADER RECORD*******MEMBER  HEADER RECORD!!!!!!!000000000000000001600000000'.ljust(75) + b'140  '
    header += line('HEADER RECORD*******DSCRPTR HEADER RECORD!!!!!!!000000000000000000000000000000')
    header += b'SAS'.ljust(8) + b'SAMPLE'.ljust(8) + b'SASDATA'.ljust(8) + b'9.4'.ljust(8) + b'LINUX'.ljust(8) + b' ' * 24 + date
    header += date + b' ' * 16 + b'Synthetic transport'.ljust(40) + b' ' * 8
    names_header = bytearray(line('HEADER RECORD*******NAMESTR HEADER RECORD!!!!!!!000000000000000000000000000000'))
    names_header[54:58] = b'0002'
    header += names_header
    fields = b''
    for kind, width, index, name, label, offset in [(1, 8, 1, b'VALUE', b'Value label', 0), (2, 4, 2, b'CODE', b'', 8)]:
        fields += struct.pack('>hhhh8s40s8shhh2s8shhl52s', kind, 0, width, index, name.ljust(8), label.ljust(40), b' ' * 8,
                              0, 0, 0, b'  ', b' ' * 8, 0, 0, offset, b' ' * 52)
    header += fields.ljust(320)
    header += line('HEADER RECORD*******OBS     HEADER RECORD!!!!!!!000000000000000000000000000000')
    observations = bytes.fromhex('4110000000000000') + b'AB  ' + b'A' + b'\0' * 7 + b'    ' + b'.' + b'\0' * 7 + b'CD  '
    return bytes(header + observations.ljust(80))


class DataFilesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def file(self, name, content):
        path = self.root / name
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
        return path

    def test_json_preserves_typed_metadata_and_supports_result_wrapper(self):
        table = {'schema': {'Code': {'type': 'character', 'length': 3, 'label': 'Code label'}, 'Value': 'number'},
                 'rows': [{'Code': 'x', 'Value': {'missing': 'A'}}], 'encoding': 'ascii', 'label': 'Test label'}
        path = self.file('result.json', json.dumps({'datasets': {'Out': table}, 'log': []}))
        imported = load_data_file(path, 'expected')
        result = imported['catalog']['expected']
        self.assertEqual(result['rows'], [{'code': 'x  ', 'value': {'missing': 'A'}}])
        self.assertEqual(result['schema']['code']['label'], 'Code label')
        self.assertEqual(result['label'], 'Test label')
        self.assertEqual(imported['identity']['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_json_duplicate_names_bad_metadata_and_multi_rename_fail(self):
        for text in ['{"x":1,"x":2}', '{"x":{"schema":{"v":"number"},"rows":[],"extra":1}}',
                     '{"a":{"schema":{},"rows":[]},"b":{"schema":{},"rows":[]}}']:
            with self.subTest(text=text), self.assertRaises(DataFileError):
                load_data_file(self.file('raw.json', text), 'renamed')

    def test_csv_inference_keeps_identifier_zeros_and_missing_tags(self):
        imported = load_data_file(self.file('raw.csv', 'ID,amount,name\n001,12.5,A\n002,.A,é\n003,,\n'))
        table = imported['catalog']['raw']
        self.assertEqual(table['schema']['id'], {'type': 'character', 'length': 3})
        self.assertEqual(table['schema']['name'], {'type': 'character', 'length': 2})
        self.assertEqual(table['rows'][1], {'id': '002', 'amount': {'missing': 'A'}, 'name': 'é'})
        self.assertEqual(table['rows'][2]['amount'], None)
        self.assertTrue(imported['warnings'])

    def test_csv_refuses_ragged_duplicate_header_and_lost_integer_precision(self):
        for text in ['a,b\n1\n', 'A,a\n1,2\n', 'a\n9007199254740993\n']:
            with self.subTest(text=text), self.assertRaises(DataFileError):
                load_data_file(self.file('raw.csv', text))

    def test_duplicate_dataset_bindings_refuse_instead_of_replacing(self):
        path = self.file('raw.csv', 'a\n1\n')
        with self.assertRaisesRegex(DataFileError, 'same dataset name'):
            load_data_files([path, path])

    @unittest.skipUnless(PANDAS, 'pandas is the optional SAS file reader')
    def test_sas7bdat_real_reader_preserves_both_byte_orders_tags_dates_and_metadata(self):
        for endian, u64 in [('<', False), ('>', False), ('<', True), ('>', True)]:
            with self.subTest(endian=endian, u64=u64):
                imported = load_data_file(self.file('native.sas7bdat', sas_fixture(endian=endian, u64=u64)))
                table = imported['catalog']['native']
                self.assertEqual(table['label'], 'Synthetic table')
                self.assertEqual(table['schema']['amount'], {'type': 'number', 'label': 'Amount label'})
                self.assertEqual(table['schema']['day']['format'], 'DATE')
                self.assertEqual(table['rows'], [{'amount': 12.5, 'day': 1.0, 'code': 'A   '},
                    {'amount': {'missing': 'A'}, 'day': 2.0, 'code': 'é  '},
                    {'amount': None, 'day': 3.0, 'code': '    '}])
                self.assertEqual(imported['metadata']['declared_observations'], 3)

    @unittest.skipUnless(PANDAS, 'pandas is the optional SAS file reader')
    def test_sas7bdat_empty_table_and_explicit_refusals(self):
        table = load_data_file(self.file('empty.sas7bdat', sas_fixture(empty=True)))['catalog']['empty']
        self.assertEqual(len(table['schema']), 3)
        self.assertEqual(table['rows'], [])
        for options, reason in [({'missing_tag': '?'}, 'missing-value payload'), ({'encoding': 62}, 'Encoding'),
                                ({'numeric_width': 4}, 'storage lengths')]:
            with self.subTest(options=options), self.assertRaisesRegex(DataFileError, reason):
                load_data_file(self.file('bad.sas7bdat', sas_fixture(**options)))

    @unittest.skipUnless(PANDAS, 'pandas is the optional SAS file reader')
    def test_sas7bdat_long_character_bytes_survive_rle_and_nul_padding(self):
        for endian, compressed in [('<', False), ('>', False), ('<', True), ('>', True)]:
            with self.subTest(endian=endian, compressed=compressed):
                table = load_data_file(self.file('long.sas7bdat', sas_fixture(
                    endian=endian, u64=True, character_width=40, nul_padding=True,
                    compressed=compressed)))['catalog']['long']
                self.assertEqual(table['schema']['code']['length'], 40)
                self.assertEqual(table['rows'][0]['code'], 'A' + '\0' * 39)
                self.assertEqual(table['rows'][1]['code'], 'é' + '\0' * 38)
                self.assertEqual(table['rows'][2]['code'], '\0' * 40)

    @unittest.skipUnless(PANDAS, 'pandas is the optional SAS file reader')
    def test_native_unadorned_numeric_schema_matches_new_runtime_variables(self):
        from .compare import table_equal
        from .plan import compile_plan
        from .runtime import run_plan
        expected = load_data_file(self.file('expected.sas7bdat', sas_fixture(
            variable_metadata=False, last_numeric=True)))['catalog']['expected']
        self.assertEqual(expected['schema'], {'amount': 'number', 'day': 'number', 'code': 'number'})
        raw = deepcopy(expected)
        del raw['schema']['code']
        for row in raw['rows']:
            del row['code']
        plan = compile_plan('data expected; set raw; code=_n_; run;')
        actual = run_plan(plan.to_dict(), {'raw': raw})['datasets']['expected']
        self.assertTrue(table_equal(actual, expected))

    @unittest.skipUnless(PANDAS, 'pandas is the optional SAS file reader')
    def test_changed_private_reader_interface_has_actionable_failure(self):
        from pandas.io.sas.sas7bdat import SAS7BDATReader
        path = self.file('native.sas7bdat', sas_fixture())
        with patch.object(SAS7BDATReader, 'column_data_offsets', None):
            with self.assertRaisesRegex(DataFileError, 'pandas SAS reader is incompatible'):
                load_data_file(path)

    @unittest.skipUnless(PANDAS, 'pandas is the optional SAS file reader')
    def test_xport_real_reader_retains_raw_missing_tags_and_labels(self):
        table = load_data_file(self.file('transport.xpt', xpt_fixture()))['catalog']['transport']
        self.assertEqual(table['label'], 'Synthetic transport')
        self.assertEqual(table['schema']['value']['label'], 'Value label')
        self.assertEqual(table['rows'], [{'value': 1.0, 'code': 'AB  '},
                         {'value': {'missing': 'A'}, 'code': '    '}, {'value': None, 'code': 'CD  '}])

    @unittest.skipUnless(DUCKDB, 'DuckDB is the optional Parquet writer')
    def test_parquet_publishes_metadata_tags_empty_schema_and_refuses_overwrite(self):
        import duckdb
        table = {'schema': {'id': 'number', 'code': {'type': 'character', 'length': 3, 'format': '$CHAR3.'}},
                 'rows': [{'id': 2, 'code': 'a'}, {'id': {'missing': 'Z'}, 'code': 'b'}], 'label': 'Export'}
        path = self.root / 'result.parquet'
        exported = write_parquet(table, path)
        connection = duckdb.connect(':memory:')
        try:
            self.assertEqual(connection.execute('SELECT * FROM read_parquet(?)', [str(path)]).fetchall(), [(2.0, 'a  '), (None, 'b  ')])
            sidecar = json.loads(Path(exported['metadata']).read_text())
            self.assertEqual(sidecar['missing_tags'], [{'row': 1, 'column': 'id', 'tag': 'Z'}])
            self.assertEqual(sidecar['table_metadata']['label'], 'Export')
            self.assertEqual(sidecar['parquet_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
            with self.assertRaisesRegex(DataFileError, 'already exists'):
                write_parquet(table, path)
            empty = write_parquet({**table, 'rows': []}, self.root / 'empty.parquet')
            self.assertEqual(connection.execute('SELECT * FROM read_parquet(?)', [empty['parquet']]).description[0][0], 'id')
            self.assertEqual(connection.execute('SELECT count(*) FROM read_parquet(?)', [empty['parquet']]).fetchone(), (0,))
        finally:
            connection.close()

    @unittest.skipUnless(DUCKDB, 'DuckDB is the optional Parquet writer')
    def test_parquet_second_publication_failure_cleans_first_file(self):
        import os
        link = os.link
        def fail_metadata(source, destination):
            if str(destination).endswith('.metadata.json'):
                raise OSError('synthetic publication failure')
            return link(source, destination)
        path = self.root / 'failed.parquet'
        with patch('saschi.data_files.os.link', side_effect=fail_metadata), self.assertRaises(OSError):
            write_parquet({'schema': {'a': 'number'}, 'rows': []}, path)
        self.assertFalse(path.exists())
        self.assertFalse(path.with_suffix('.metadata.json').exists())


if __name__ == '__main__':
    unittest.main()
