"""Bounded descriptor-only PROC SQL creation, separate from general SQL."""
import re

NAME = re.compile(r'[a-z_][a-z0-9_]{0,31}\Z', re.ASCII)
MAX_COLUMNS = 64
MAX_WIDTH = 32767
MAX_SOURCE_BYTES = 16384
# Conservative tool policy. SAS reserves some SQL words only in context.
RESERVED = frozenset('proc sql create table char character varchar numeric num integer int '
    'decimal float real double quit run select from where as like case when then else end '
    'join inner left right full outer on group by order having union intersect except '
    'insert into values update delete drop alter view constraint primary foreign key '
    'references not null check unique default distinct all _null_ _n_ _error_ _all_ '
    '_numeric_ _character_ _temporary_ _infile_ _file_ _ods_ _page_ _blankpage_'.split())
STEP_KEYS = frozenset(('kind','name','line','inputs','by','operations','nodupkey',
                       'where','retained','lengths','display_names'))


def ordinary(name):
    return type(name) is str and NAME.fullmatch(name) is not None and name not in RESERVED


def validate_columns(columns):
    if type(columns) is not list or not 1 <= len(columns) <= MAX_COLUMNS:
        raise ValueError('SQL CREATE requires an ordered list of1..64 columns')
    seen = set()
    for column in columns:
        if (type(column) is not dict or set(column) != {'name','type','length'}
                or not ordinary(column.get('name')) or column.get('type') != 'character'
                or type(column.get('length')) is not int or not 1 <= column['length'] <= MAX_WIDTH
                or column['name'] in seen):
            raise ValueError('SQL CREATE requires unique normalized ordinary CHAR descriptors')
        seen.add(column['name'])
    return columns


def parse_create(text):
    """Consume exactly one splitter-delimited CREATE, without a final semicolon."""
    if type(text) is not str or len(text) > MAX_SOURCE_BYTES or not text.isascii():
        raise ValueError('SQL CREATE requires bounded ASCII declaration text')
    match = re.fullmatch(r'\s*create\s+table\s+([a-z_][a-z0-9_]{0,31})\s*\((.*)\)\s*',
                         text,re.I|re.S|re.ASCII)
    if not match or not ordinary(match[1].lower()):
        raise ValueError('SQL CREATE supports one unqualified ordinary destination and explicit columns')
    fields = match[2].split(',')
    if not 1 <= len(fields) <= MAX_COLUMNS:
        raise ValueError('SQL CREATE permits1..64 explicit columns')
    columns = []
    for field in fields:
        column = re.fullmatch(r'\s*([a-z_][a-z0-9_]{0,31})\s+char\s*\(\s*([1-9][0-9]{0,4})\s*\)\s*',
                              field,re.I|re.ASCII)
        if not column:
            raise ValueError('SQL CREATE supports explicit name CHAR(unpadded width) declarations only')
        columns.append({'name':column[1].lower(),'type':'character','length':int(column[2])})
    validate_columns(columns)
    return match[1].lower(),columns


def validate_step(step,version=2):
    """Validate portable shape before materialization, independently of parsing."""
    if (type(version) is not int or version != 2 or type(step) is not dict
            or set(step) != STEP_KEYS or step['kind'] != 'sql_create'
            or not ordinary(step['name']) or type(step['line']) is not int or step['line'] < 1
            or type(step['inputs']) is not list or step['inputs'] != []
            or type(step['by']) is not list or step['by'] != []
            or step['nodupkey'] is not False or step['where'] is not None
            or type(step['retained']) is not dict or step['retained'] != {}
            or type(step['lengths']) is not dict or step['lengths'] != {}
            or type(step['display_names']) is not dict or step['display_names'] != {}
            or type(step['operations']) is not list or len(step['operations']) != 1):
        raise ValueError('SQL CREATE requires one version2 descriptor-only step with default metadata')
    operation = step['operations'][0]
    if (type(operation) is not dict or set(operation) != {'kind','line','args'}
            or operation['kind'] != 'sql_create' or type(operation['line']) is not int
            or operation['line'] < step['line'] or type(operation['args']) is not dict
            or set(operation['args']) != {'columns'}):
        raise ValueError('SQL CREATE requires one source-ordered sql_create operation')
    return validate_columns(operation['args']['columns'])


def materialize(step,catalog,version=2):
    """Return a fresh empty table; refuse every existing destination atomically."""
    columns = validate_step(step,version)
    if type(catalog) is not dict or any(type(name) is not str for name in catalog):
        raise ValueError('SQL CREATE requires a named catalog')
    if any(name.lower() == step['name'] for name in catalog):
        raise ValueError('SQL CREATE existing destination requires separate overwrite evidence')
    return {'schema':{c['name']:{'type':'character','length':c['length']} for c in columns},'rows':[]}
