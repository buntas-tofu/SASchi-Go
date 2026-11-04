"""Strict portable scaffolding shared by separately bounded FORMAT families."""
from copy import deepcopy

from .character_input import STEP_KEYS,ordinary


def selected(plan,kinds,profile):
    pending=[(plan,False)];active=set();done=set();found=False
    while pending:
        value,leaving=pending.pop()
        if type(value) not in (dict,list,tuple):continue
        identity=id(value)
        if leaving:active.remove(identity);done.add(identity);continue
        if identity in active:raise ValueError('FORMAT programs refuse cyclic containers')
        if identity in done:continue
        active.add(identity);pending.append((value,True))
        if type(value) is dict:
            found |= type(value.get('kind')) is str and value['kind'] in kinds or value.get('profile')==profile
            children=value.values()
        else:children=value
        pending.extend((child,False) for child in children if type(child) in (dict,list,tuple))
    if found and len(done)>100000:raise ValueError('FORMAT portable container bound exceeded')
    return found


def line(value):return type(value) is int and value>0


def program(plan,catalog,kinds,profile,routes):
    if not selected(plan,kinds,profile):return False
    if (type(plan) is not dict or set(plan)!={'version','steps','tickets','matched'}
            or type(plan.get('version')) is not int or plan['version']!=2
            or type(plan.get('steps')) is not list or not 1<=len(plan['steps'])<=64
            or type(plan.get('tickets')) is not list or plan['tickets']
            or type(plan.get('matched')) is not list
            or catalog is not None and (type(catalog) is not dict or catalog)):
        raise ValueError('FORMAT family requires exact complete version2 and an empty initial catalog')
    for item in plan['matched']:
        if (type(item) not in (list,tuple) or len(item)!=3 or type(item[0]) is not str
                or item[0] not in routes or item[1]!=routes[item[0]] or not line(item[2])):
            raise ValueError('FORMAT matched routes require exact known triples')
    return True


def step_args(step,kinds,profile,*,input_arg=None):
    if (type(step) is not dict or set(step)!=STEP_KEYS or type(step.get('kind')) is not str
            or step['kind'] not in kinds or not ordinary(step.get('name')) or not line(step.get('line'))
            or type(step.get('inputs')) is not list or type(step.get('by')) is not list or step['by']
            or step.get('where') is not None or step.get('nodupkey') is not False
            or any(type(step.get(k)) is not dict or step[k] for k in ('retained','lengths','display_names'))
            or type(step.get('operations')) is not list or len(step['operations'])!=1):
        raise ValueError('FORMAT family requires exact Step defaults')
    op=step['operations'][0]
    if (type(op) is not dict or set(op)!={'kind','line','args'} or op.get('kind')!=step['kind']
            or not line(op.get('line')) or op['line']!=step['line'] or type(op.get('args')) is not dict
            or op['args'].get('profile')!=profile):
        raise ValueError('FORMAT family requires one same-kind header-line operation')
    expected_inputs=([op['args'].get(input_arg)] if input_arg is not None else
                     [step['name']] if step['kind'].endswith(('_print','_report')) else [])
    if step['inputs']!=expected_inputs:
        raise ValueError('FORMAT Step inputs differ from its kind')
    return op['args']


def source_lines(value,step,count):
    if (type(value) is not list or len(value)!=count or not all(line(n) for n in value)
            or value!=sorted(value) or value[0]!=step['line']):
        raise ValueError('FORMAT source provenance differs')


def retag(step,kind,profile):
    step.kind=kind;step.operations[0].kind=kind;step.operations[0].args['profile']=profile
    return step


def date_data(step,args):
    from . import date_program as old
    old_step=deepcopy(step);old_step['kind']='date_data';old_step['operations'][0]['kind']='date_data'
    old_step['operations'][0]['args']['profile']=old.PROFILE
    old._step(old_step)
    return old._data(old_step['operations'][0]['args'],old_step)


def text(value,maximum=64):
    if (type(value) is not str or not 1<=len(value)<=maximum
            or any(not 32<=ord(c)<=126 for c in value) or '&' in value):
        raise ValueError('FORMAT text requires bounded printable nonmacro ASCII')
    return value
