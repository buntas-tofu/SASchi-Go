"""DS-044 bounded numeric inline INPUT, validated before row execution."""
import re

from sas_semantics import sas_input_records
from .operations import walk_operations

RESERVED = {'_n_', '_error_', '_all_', '_numeric_', '_character_', '_infile_',
            '_file_', '_ods_', '_page_', '_blankpage_'}


def names_valid(names):
    return (isinstance(names, list) and 1 <= len(names) <= 32
            and all(isinstance(n, str) and re.fullmatch(r'[a-z_][a-z0-9_]{0,31}', n)
                    and n not in RESERVED for n in names)
            and len(set(names)) == len(names))


def source_records(raw):
    """Keep opaque physical lines, dropping only the header's empty remainder."""
    raw = raw.replace('\r\n', '\n')
    lines = raw.split('\n')
    if len(lines) < 2 or lines[0].strip(' ') or lines[-1] != '':
        raise ValueError('CARDS/DATALINES data must start on the next line')
    return lines[1:-1]


def validate_step(step, version=2):
    from .numeric_pipeline import validate_step as validate_pipeline
    pipeline = validate_pipeline(step, version)
    if pipeline is not None:
        return pipeline['inline_rows']
    flat = list(walk_operations(step['operations'], all_containers=True))
    found = [op for op in flat if op['kind'] == 'input_list']
    if not found:
        return None
    if (version != 2 or step.get('kind') != 'data' or step.get('inputs')
            or step.get('by') or step.get('where') or len(found) != 1):
        raise ValueError('numeric INPUT requires one version2 DATA inline source, without SET/BY/WHERE')
    op = found[0]
    executable = [o for o in step['operations'] if o['kind'] not in ('declare', 'projection')]
    if not executable or executable[0] is not op:
        raise ValueError('numeric INPUT must be the first top-level executable statement')
    allowed = {'declare', 'projection', 'input_list', 'assign', 'round', 'sum_statement', 'if',
               'subset', 'put', 'put_literal', 'put_numeric_list', 'put_mixed_numeric', 'output'}
    if any(o['kind'] not in allowed for o in flat):
        raise ValueError('numeric INPUT supports scalar DATA actions only; arrays, loops and other input require review')
    args = op['args']
    if (set(args) != {'names', 'records', 'data_line'} or not names_valid(args.get('names'))
            or type(op.get('line')) is not int or op['line'] < 1
            or type(args.get('data_line')) is not int or args['data_line'] <= op['line']):
        raise ValueError('numeric INPUT requires unique ordinary names, raw records and positive source lines')
    # Data parsing is eager, including an eventual incomplete observation. A
    # consumed invalid token cannot disappear merely because EOF follows it.
    values = sas_input_records(args['records'], len(args['names']))
    return [dict(zip(args['names'], row)) for row in values]
