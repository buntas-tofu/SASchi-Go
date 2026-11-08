"""Local file boundary for the bounded typed catalog.

Status: importer and export contracts, not proof of native SAS equivalence.
SAS dates remain numbers. Character widths, format names, labels and supported
missing tags remain explicit. Unsupported encodings and ambiguous values fail.

The SAS adapter uses private pandas interfaces. Executed compatibility coverage
includes pandas 2.3.3 and 3.0.5; package CI must test its installed pandas version.
Missing adapter interfaces fail explicitly rather than dropping metadata.
"""
from __future__ import annotations

import codecs
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import struct
import tempfile
import warnings

from .values import column_type, normalize_catalog


SUPPORTED_EXTENSIONS = ('.sas7bdat', '.xpt', '.csv', '.json')
_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,31}\Z')
_NUMBER = re.compile(r'[+-]?(?:0|[1-9][0-9]*)(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?\Z|[+-]?\.[0-9]+(?:[eE][+-]?[0-9]+)?\Z')


class DataFileError(ValueError):
    """A file cannot be imported without an unsupported interpretation."""


def _encoding(value):
    try:
        name = codecs.lookup(value).name
    except (LookupError, TypeError) as exc:
        raise DataFileError('The file encoding is unknown. Choose UTF-8, ASCII or Latin-1 explicitly.') from exc
    aliases = {'utf-8': 'utf-8', 'ascii': 'ascii', 'iso8859-1': 'latin-1'}
    if name not in aliases:
        raise DataFileError(f'Encoding {value} is outside the supported UTF-8, ASCII and Latin-1 byte-width contract.')
    return aliases[name]


def _name(value):
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise DataFileError('Dataset names must start with a letter or underscore and contain at most 32 letters, digits or underscores.')
    return value.lower()


def _text(value, encoding):
    if isinstance(value, bytes):
        return value.decode(encoding, errors='strict')
    if isinstance(value, str):
        return value
    raise DataFileError('The reader returned unsupported text metadata.')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DataFileError('JSON contains a repeated object key.')
        result[key] = value
    return result


def _normalize(catalog):
    try:
        return normalize_catalog(catalog)
    except (ValueError, TypeError) as exc:
        raise DataFileError('Dataset validation failed: ' + str(exc)) from exc


def _json_catalog(raw, dataset_name, fallback_name):
    def invalid_constant(_):
        raise DataFileError('JSON non-finite numbers are unsupported; use null for ordinary missing values.')
    obj = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=invalid_constant)
    if isinstance(obj, dict) and isinstance(obj.get('datasets'), dict):
        obj = obj['datasets']
    if isinstance(obj, dict) and 'schema' in obj and 'rows' in obj:
        obj = {_name(dataset_name or fallback_name): obj}
    elif dataset_name is not None:
        if not isinstance(obj, dict) or len(obj) != 1:
            raise DataFileError('A dataset name can rename only a single-table JSON file.')
        obj = {_name(dataset_name): next(iter(obj.values()))}
    return _normalize(obj), {}, []


def _csv_catalog(raw, name, encoding):
    encoding = _encoding(encoding or 'utf-8')
    text = raw.decode('utf-8-sig' if encoding == 'utf-8' else encoding, errors='strict')
    records = list(csv.reader(io.StringIO(text, newline=''), strict=True))
    if not records or not records[0]:
        raise DataFileError('CSV must have a header row with variable names.')
    headers, values = records[0], records[1:]
    if any(not _NAME.fullmatch(header) for header in headers):
        raise DataFileError('CSV variable names must use SAS letters, digits and underscores, without spaces.')
    if len({header.lower() for header in headers}) != len(headers):
        raise DataFileError('CSV contains duplicate variable names.')
    if any(len(row) != len(headers) for row in values):
        raise DataFileError('CSV rows must have the same number of fields as the header.')
    schema, converters = {}, {}
    for index, header in enumerate(headers):
        column = [row[index] for row in values]
        nonblank = [value for value in column if value != '']
        numeric = bool(nonblank) and all(_NUMBER.fullmatch(value) or re.fullmatch(r'\.[A-Z_]?', value) for value in nonblank)
        if numeric:
            schema[header] = 'number'
            converters[header] = _csv_number
        else:
            width = max([1] + [len(value.encode(encoding)) for value in column])
            schema[header] = {'type': 'character', 'length': width}
            converters[header] = lambda value: value
    rows = [{header: converters[header](row[i]) for i, header in enumerate(headers)} for row in values]
    table = {'schema': schema, 'rows': rows, 'encoding': encoding}
    notes = ['CSV types and character widths are inferred from the complete file. Leading-zero values remain character data; labels and SAS formats are not supplied by CSV.']
    if not values:
        notes.append('The CSV has no observations. Each variable is provisionally character with length 1.')
    return _normalize({name: table}), {'inferred_schema': True}, notes


def _csv_number(value):
    if value in ('', '.'):
        return None
    if re.fullmatch(r'\.[A-Z_]', value):
        return {'missing': value[1]}
    number = float(value)
    if not math.isfinite(number):
        raise DataFileError('A CSV number exceeds the supported finite binary64 range.')
    if re.fullmatch(r'[+-]?[0-9]+', value) and int(value) != number:
        raise DataFileError('A CSV integer cannot be represented exactly as binary64; import it as character data in a typed catalog.')
    return number


def _sas_missing(raw, byte_order):
    """Decode SAS NaN tags before pandas or Python can canonicalize NaNs.

    SAS7BDAT tag-byte layouts are documented in the ReadStat SAS reader:
    https://github.com/WizardMac/ReadStat/blob/master/src/sas/readstat_sas7bdat_read.c
    Both ASCII tags and the older ordinal tags are recognized; other payloads
    are refused instead of being silently converted to ordinary missing.
    """
    number = struct.unpack(byte_order + 'd', raw)[0]
    if math.isfinite(number):
        return number
    if not math.isnan(number):
        raise DataFileError('A SAS numeric value is infinite, which is outside the typed catalog contract.')
    bits = int.from_bytes(raw, 'little' if byte_order == '<' else 'big')
    tag = (~(bits >> 40)) & 255
    if tag in (1, ord('.')):
        return None
    if tag == 0:
        return {'missing': '_'}
    if 2 <= tag <= 27:
        return {'missing': chr(ord('A') + tag - 2)}
    if tag == ord('_') or ord('A') <= tag <= ord('Z'):
        return {'missing': chr(tag)}
    raise DataFileError('A SAS numeric missing-value payload is not recognized. Import stopped to avoid losing its missing tag.')


def _sas7bdat_catalog(raw, name, encoding):
    try:
        from pandas.io.sas.sas7bdat import SAS7BDATReader
    except ImportError as exc:
        raise DataFileError('Direct SAS file loading requires pandas. Install the SASchi-Go desktop dependencies, then reopen the file.') from exc
    compatibility_error = ('This pandas SAS reader is incompatible with the metadata-preserving import adapter. '
                           'Use a supported desktop package or pandas 2.3.3 or 3.0.5, then reopen the file.')
    for method in ('column_data_lengths', 'column_data_offsets', 'column_types',
                   '_process_rowsize_subheader', '_read_bytes', '_chunk_to_dataframe'):
        if not callable(getattr(SAS7BDATReader, method, None)):
            raise DataFileError(compatibility_error)

    class Reader(SAS7BDATReader):
        def _process_rowsize_subheader(self, offset, length):
            super()._process_rowsize_subheader(offset, length)
            if length < 130:
                raise DataFileError('The SAS dataset label metadata is incomplete.')
            self.label_reference = struct.unpack(self.byte_order + 'HHH', self._read_bytes(offset + length - 130, 6))

        def _chunk_to_dataframe(self):
            # The caller consumes raw byte buffers, not a DataFrame. In
            # particular, no float conversion may canonicalize missing tags.
            return range(self._current_row_in_chunk_index)

    with Reader(io.BytesIO(raw), convert_dates=False, blank_missing=False,
                encoding=None, convert_text=False, convert_header_text=False,
                compression=None) as reader:
        for attribute in ('inferred_encoding', 'columns', 'column_count', 'col_count_p1',
                          'col_count_p2', '_column_data_offsets', 'column_names_raw', 'row_count', 'byte_order'):
            if not hasattr(reader, attribute):
                raise DataFileError(compatibility_error)
        selected_encoding = _encoding(encoding or reader.inferred_encoding)
        if (len(reader.columns) != reader.column_count
                or reader.col_count_p1 + reader.col_count_p2 != reader.column_count):
            raise DataFileError('The SAS reader did not provide complete variable metadata.')
        columns = list(reader.columns)
        names = [_text(column.name, selected_encoding) for column in columns]
        schema = {}
        for name_in_file, column in zip(names, columns):
            if column.ctype == b'd':
                if column.length != 8:
                    raise DataFileError('SAS numeric storage lengths other than 8 bytes require review before import.')
                spec = {'type': 'number'}
            elif column.ctype == b's':
                spec = {'type': 'character', 'length': int(column.length)}
            else:
                raise DataFileError('The SAS reader returned an unsupported variable type.')
            for key in ('label', 'format'):
                value = _text(getattr(column, key), selected_encoding)
                if value:
                    spec[key] = value
            if spec == {'type': 'number'}:
                spec = 'number'
            schema[name_in_file] = spec
        if len(schema) != len(names):
            raise DataFileError('The SAS file contains duplicate variable names.')
        table = {'schema': schema, 'rows': [], 'encoding': selected_encoding}
        label_index, label_offset, label_length = getattr(reader, 'label_reference', (0, 0, 0))
        if label_length:
            if label_index >= len(reader.column_names_raw) or label_offset + label_length > len(reader.column_names_raw[label_index]):
                raise DataFileError('The SAS dataset label points outside its metadata block.')
            table['label'] = _text(reader.column_names_raw[label_index][label_offset:label_offset + label_length], selected_encoding)
        expected_rows = int(reader.row_count)
        # pandas' character path strips trailing NUL bytes. Its raw numeric
        # path copies bytes without interpreting them. Split each field into
        # slices of at most eight bytes and use that path for every field;
        # reconstruct character bytes before decoding or width normalization.
        field_slices, offsets, lengths = [], [], []
        for column, offset in zip(columns, reader._column_data_offsets):
            slices = []
            for start in range(0, column.length, 8):
                length = min(8, column.length - start)
                slices.append((len(offsets), length))
                offsets.append(offset + start)
                lengths.append(length)
            field_slices.append(slices)
        reader._column_data_offsets = offsets
        reader._column_data_lengths = lengths
        reader._column_types = [b'd'] * len(offsets)
        reader.column_count = len(offsets)
        while len(table['rows']) < expected_rows:
            frame = reader.read(min(8192, expected_rows - len(table['rows'])))
            count = len(frame)
            if count == 0:
                raise DataFileError('The SAS file ended before its declared observation count.')
            if not hasattr(reader, '_byte_chunk') or reader._byte_chunk.shape != (len(offsets), count * 8):
                raise DataFileError(compatibility_error)
            buffers = [reader._byte_chunk[index].tobytes() for index in range(len(offsets))]
            decoded_columns = []
            for column, slices in zip(columns, field_slices):
                values = []
                for row in range(count):
                    chunks = []
                    for index, length in slices:
                        start = row * 8 + (8 - length if reader.byte_order == '<' else 0)
                        chunks.append(buffers[index][start:start + length])
                    payload = b''.join(chunks)
                    values.append(_sas_missing(payload, reader.byte_order) if column.ctype == b'd' else _text(payload, selected_encoding))
                decoded_columns.append(values)
            table['rows'].extend({column_name: decoded_columns[i][row] for i, column_name in enumerate(names)} for row in range(count))
        info = {'reader': 'pandas.sas7bdat', 'source_encoding': reader.inferred_encoding,
                'encoding': selected_encoding, 'declared_observations': expected_rows,
                'date_values': 'raw SAS numbers', 'format_metadata': 'names only'}
        notes = ['SAS date values remain numeric. Format names are retained; display widths and custom format catalog definitions are not imported.']
        if encoding is not None:
            notes.append('The selected text encoding overrides the SAS header encoding.')
        return _normalize({name: table}), info, notes


def _xpt_catalog(raw, name, encoding):
    try:
        from pandas.io.sas.sas_xport import XportReader
    except ImportError as exc:
        raise DataFileError('Direct SAS transport loading requires pandas. Install the SASchi-Go desktop dependencies, then reopen the file.') from exc
    selected_encoding = _encoding(encoding or 'latin-1')
    with XportReader(io.BytesIO(raw), encoding=None, compression=None) as reader:
        if not any(field['ntype'] == 'numeric' for field in reader.fields):
            raise DataFileError('Character-only XPORT files have ambiguous trailing blank observations and require a typed catalog.')
        data = raw[reader.record_start:]
        if b'HEADER RECORD*******MEMBER' in data:
            raise DataFileError('Only single-member XPORT files are supported. Separate the members before importing.')
        names, schema, offsets = [], {}, []
        offset = 0
        for field in reader.fields:
            key = _text(field['name'], selected_encoding)
            names.append(key)
            width = field['field_length']
            if field['ntype'] == 'numeric':
                if width != 8:
                    raise DataFileError('XPORT numeric storage lengths other than 8 bytes require review before import.')
                spec = {'type': 'number'}
            else:
                spec = {'type': 'character', 'length': width}
            label = _text(field['label'], selected_encoding)
            if label:
                spec['label'] = label
            fmt = _text(field['nform'], selected_encoding)
            if fmt:
                spec['format'] = fmt + (str(field['nfl']) if field['nfl'] else '') + '.' + (str(field['num_decimals']) if field['num_decimals'] else '')
            if spec == {'type': 'number'}:
                spec = 'number'
            schema[key] = spec
            offsets.append(offset)
            offset += width
        if len(schema) != len(names):
            raise DataFileError('The XPORT file contains duplicate variable names.')
        frame = reader.read() if reader.nobs else None
        count = len(frame) if frame is not None else 0
        table = {'schema': schema, 'rows': [], 'encoding': selected_encoding}
        label = reader.member_info.get('label', '')
        if label:
            table['label'] = label
        for row in range(count):
            result = {}
            for index, field in enumerate(reader.fields):
                key = names[index]
                start = row * reader.record_length + offsets[index]
                raw_value = data[start:start + field['field_length']]
                if field['ntype'] == 'char':
                    result[key] = _text(raw_value, selected_encoding)
                elif raw_value[1:] == b'\0' * 7 and raw_value[0] in b'._ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                    result[key] = None if raw_value[0] == ord('.') else {'missing': chr(raw_value[0])}
                else:
                    value = float(frame.iloc[row, index])
                    if not math.isfinite(value):
                        raise DataFileError('An XPORT numeric value could not be imported without losing its missing-value representation.')
                    result[key] = value
            table['rows'].append(result)
        info = {'reader': 'pandas.xport', 'encoding': selected_encoding,
                'declared_observations': int(reader.nobs), 'date_values': 'raw SAS numbers'}
        notes = ['XPORT does not declare a text encoding. Latin-1 is used unless an encoding is selected; custom format catalog definitions are not imported.']
        return _normalize({name: table}), info, notes


def load_data_file(path, dataset_name=None, *, encoding=None):
    """Read one local file without writing it or preparing a JSON file.

    Returns catalog, metadata, warnings and a content identity. JSON catalogs
    retain their names; a supplied name can rename a single-table file only.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise DataFileError('Choose a .sas7bdat, .xpt, .csv or typed .json dataset file.')
    try:
        raw = path.read_bytes()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            if suffix == '.json':
                catalog, metadata, notes = _json_catalog(raw, dataset_name, path.stem)
            else:
                name = _name(dataset_name or path.stem)
                reader = {'.csv': _csv_catalog, '.sas7bdat': _sas7bdat_catalog, '.xpt': _xpt_catalog}[suffix]
                catalog, metadata, notes = reader(raw, name, encoding)
            if caught:
                raise DataFileError('The file reader reported an incomplete or unsupported file condition. Import stopped without accepting partial data.')
    except DataFileError:
        raise
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, struct.error, csv.Error) as exc:
        raise DataFileError(f'The {suffix} file could not be read as a complete supported dataset: {type(exc).__name__}.') from exc
    metadata = {**metadata, 'file_type': suffix[1:], 'datasets': {
        name: {'observations': len(table['rows']), 'variables': len(table['schema'])} for name, table in catalog.items()}}
    return {'catalog': catalog, 'metadata': metadata, 'warnings': notes,
            'identity': {'name': path.name, 'sha256': hashlib.sha256(raw).hexdigest(), 'size_bytes': len(raw)}}


def load_data_files(paths, *, names=None):
    """Combine explicit file selections, refusing duplicate dataset names."""
    paths = list(paths)
    names = [None] * len(paths) if names is None else list(names)
    if len(names) != len(paths):
        raise DataFileError('Provide one dataset name for each selected file.')
    catalog, imports = {}, []
    for path, name in zip(paths, names):
        loaded = load_data_file(path, name)
        if catalog.keys() & loaded['catalog'].keys():
            raise DataFileError('Two selected files supply the same dataset name. Assign distinct names before running.')
        catalog.update(loaded['catalog'])
        imports.append({key: loaded[key] for key in ('identity', 'metadata', 'warnings')})
    return {'catalog': catalog, 'imports': imports,
            'warnings': [note for item in imports for note in item['warnings']]}


def write_parquet(table, path):
    """Publish Parquet plus its required metadata sidecar without overwriting.

    Tagged missing values are null in Parquet; the sidecar records their exact
    row/column tags, original ordered descriptors and file hash. Preserve both.
    """
    try:
        import duckdb
    except ImportError as exc:
        raise DataFileError('Parquet export requires DuckDB. Install the SASchi-Go desktop dependencies to enable this export.') from exc
    table = _normalize({'export': table})['export']
    path = Path(path)
    if path.suffix.lower() != '.parquet':
        raise DataFileError('Choose a .parquet output filename.')
    sidecar = path.with_suffix('.metadata.json')
    if path.exists() or path.is_symlink() or sidecar.exists() or sidecar.is_symlink():
        raise DataFileError('The Parquet file or metadata sidecar already exists. Choose a new filename.')
    if not table['schema']:
        raise DataFileError('Parquet export requires at least one variable.')
    names = list(table['schema'])
    definitions = ', '.join('"' + key + '" ' + ('DOUBLE' if column_type(table['schema'][key]) == 'number' else 'VARCHAR') for key in names)
    tags = [{'row': i, 'column': key, 'tag': row[key]['missing']}
            for i, row in enumerate(table['rows']) for key in names if isinstance(row[key], dict)]
    manifest = {'schema_version': 1, 'contract': 'saschi-parquet-with-metadata-v1',
                'row_count': len(table['rows']), 'column_order': names,
                'table_metadata': {key: value for key, value in table.items() if key != 'rows'},
                'missing_tags': tags, 'missing_tags_row_index': 'zero-based',
                'note': 'Keep this sidecar with the Parquet file. Tagged missing values are represented as null in Parquet.'}
    with tempfile.TemporaryDirectory(prefix='.saschi-export-', dir=path.parent) as temporary:
        parquet_tmp, metadata_tmp = Path(temporary) / 'data.parquet', Path(temporary) / 'metadata.json'
        connection = duckdb.connect(':memory:')
        try:
            connection.execute('CREATE TABLE exported (' + definitions + ')')
            if table['rows']:
                connection.executemany('INSERT INTO exported VALUES (' + ','.join('?' for _ in names) + ')',
                    [[None if isinstance(row[key], dict) else row[key] for key in names] for row in table['rows']])
            connection.execute('COPY exported TO ? (FORMAT PARQUET, COMPRESSION ZSTD)', [str(parquet_tmp)])
        finally:
            connection.close()
        manifest['parquet_sha256'] = hashlib.sha256(parquet_tmp.read_bytes()).hexdigest()
        metadata_tmp.write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        published = False
        try:
            os.link(parquet_tmp, path)
            published = True
            os.link(metadata_tmp, sidecar)
        except OSError:
            if published:
                path.unlink()
            raise
    return {'parquet': str(path), 'metadata': str(sidecar), 'rows': len(table['rows']),
            'columns': len(names), 'sha256': manifest['parquet_sha256']}


export_parquet = write_parquet
