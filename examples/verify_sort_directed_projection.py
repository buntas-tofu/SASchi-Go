#!/usr/bin/env python3
"""Independent KEEP/DROP with directed BY qualification for maintainer review."""
import json
import random
import verify_sort_input_drop as shared


def batch_witness(sources):
    return shared.batch_witness(sources,'sort_directed_projection.R')


def key_text(keys):
    return ' '.join(('descending ' if item['descending'] else '')+item['name'] for item in keys)


def generated_cases(count=80):
    rng=random.Random(7901);cases=[]
    patterns=[(['z','n'],[True,False]),(['z','n'],[False,True]),(['z','n'],[True,True]),
              (['n','z'],[True,False]),(['n','z'],[False,True])]
    for i in range(count):
        fractional=i%4==0
        values=[(rng.choice(['','A','B','a','Aa']),rng.choice([None,-2,-.5,0,.5,2] if fractional else [None,-2,0,2]),
                 rng.randrange(6),rng.choice(['X','Y','']),rng.choice(['M','N',''])) for _ in range(rng.randrange(26))]
        mode='keep' if i%2 else 'drop';names=['payload','n','z','q'] if mode=='keep' else ['tail','q']
        if i%3==0:names=list(reversed(names))
        key_names,directions=patterns[i%len(patterns)];keys=shared.key_specs(key_names,directions);nodup=i%3!=0;reports=0 if fractional else i%3
        cards=[','.join('.' if value is None else str(value) for value in row) for row in values]
        text=shared.source(cards,mode=mode,names=' '.join(names),keys=key_text(keys),nodupkey=nodup,reports=reports)
        cases.append((text,shared.hand_case(values,mode,names,keys,nodup,reports)))
    return cases


def boundary_cases():
    full=shared.source([],mode='keep',names='payload n z',keys='descending z n')
    for i in range(62):full+=f'proc sort data=raw(drop=q tail) out=s{i};by descending z;run;\n'
    return [shared.source([],keys='descending z descending n'),
            shared.source(['A,1,2,X,M']*1000,mode='keep',names='payload n z',keys='z descending n'),
            shared.source(['A,.5,1,X,M','A,.,2,Y,N','a,-.5,3,Z,P'],keys='descending n z'),
            shared.source(['Z'*64+',1,X'],columns='z :$64. n q :$1.',mode='keep',names='n z',keys='descending z'),
            shared.source([],columns='z :$1. '+' '.join('n'+str(i) for i in range(31)),names=' '.join('n'+str(i) for i in reversed(range(31))),keys='descending z'),
            shared.source([],columns='z :$1. '+' '.join('n'+str(i) for i in range(31)),mode='keep',names=' '.join('n'+str(i) for i in reversed(range(31)))+' z',keys='descending z'),
            shared.source([],columns='z :$1. '+' '.join('n'+str(i) for i in range(8)),names='n7',keys='descending z '+' '.join('descending n'+str(i) for i in range(7))),
            full,shared.source([],keys='z descending n',reports=2)]


def refusal_cases():
    keep=lambda **kwargs:shared.source([],mode='keep',names='payload n z',keys='z descending n',**kwargs)
    base=keep();result=[]
    for label,names,keys in [('keep-removed-by','z payload','z descending n'),('keep-unknown','absent z n','z descending n'),
                            ('keep-duplicate','z n z','z descending n'),('numeric-only','n payload','descending n'),
                            ('empty-keep','','descending z'),('dangling-direction','z n','z descending'),
                            ('doubled-direction','z n','descending descending z'),('descending-special','z n','descending _all_'),
                            ('direction-duplicate-key','z n','z descending z'),('ascending-unknown','z n','absent descending n'),
                            ('descending-unknown','z n','z descending absent')]:
        result.append((label,shared.source([],mode='keep',names=names,keys=keys)))
    for label,names,keys in [('drop-key','n','z descending n'),('drop-all-char','z q tail','descending n'),
                            ('drop-all','z n payload q tail','descending z'),('drop-unknown','absent','descending z')]:
        result.append((label,shared.source([],names=names,keys=keys)))
    result+=[('projected-dupout',base.replace(' nodupkey',' dupout=removed nodupkey')),
             ('projected-replacement',base.replace(' out=ordered','')),('projected-all',base.replace('z descending n','_all_')),
             ('both-selection-options',base.replace('keep=payload n z','keep=payload n z drop=q')),
             ('excluded-invalid',shared.source(['A,1,.1,X,M'],mode='keep',names='z n',keys='z descending n')),
             ('excluded-character-invalid',shared.source(['A,1,2,é,M'],mode='keep',names='z n',keys='z descending n')),
             ('unused-invalid-producer',base+'data unused;infile datalines dsd;input z :$1. n;datalines4;\nA,.1\n;;;;\nrun;\n'),
             ('third-report',shared.source([],keys='z descending n',reports=2)+'proc print data=raw;run;\n'),
             ('fractional-PRINT',shared.source(['A,.5,1,X,M'],keys='z descending n',reports=1)),
             ('by9',shared.source([],columns='z :$1. '+' '.join('n'+str(i) for i in range(9)),names='n8',keys='descending z '+' '.join('n'+str(i) for i in range(8)))),
             ('step65',boundary_cases()[7]+'proc sort data=raw(drop=q) out=excess;by descending z;run;\n')]
    return result


def qualify():
    q=shared.qualify_anchor(batch_witness);generated=generated_cases();boundaries=boundary_cases();refused=refusal_cases();selection=shared.family_selection_controls()
    answers=batch_witness([text for text,_ in generated]+boundaries+[text for _,text in refused]+[text for _,text in selection])
    for (_,expected),answer in zip(generated,answers[:len(generated)],strict=True):shared.exact(answer,expected)
    assert all(answer is not None for answer in answers[len(generated):len(generated)+len(boundaries)])
    start=len(generated)+len(boundaries)
    for (label,_),answer in zip(refused,answers[start:start+len(refused)],strict=True):assert answer is None,label
    for (label,_),answer in zip(selection,answers[start+len(refused):],strict=True):assert answer is None,label
    return {**q,'generated':generated,'boundaries':boundaries,'refused':refused,'selection':selection,'independent':answers}


def qualification_record(q):
    record=shared.qualification_record(q);record['construct']='DS-079 KEEP/DROP with directed BY and optional stable NODUPKEY'
    record['distinct_obligations']=['KEEP and DROP preserve descriptor order','DESCENDING binds one key','multiple and mixed directions',
      'ordinary missing reverses with numeric direction','exact fractions without PRINT','stable equal/unequal ties and optional deduplication',
      'earlier snapshots immutable across later projected sorts','existing ascending KEEP remains outside the new profile']
    return record



# Post-freeze directed runtime adapters, sharing the completed DROP plumbing.
def wrong_directed_cases(truth):
    cases=[]
    for mode in ('ascending-instead-of-directed','last-survivor','ignored-KEEP','descriptor-order','padding','raw-mutated','lost-equal-multiplicity'):
        wrong=shared.deepcopy(truth);tables=wrong['datasets'];directed=tables['directed']
        if mode=='ascending-instead-of-directed':
            directed['rows']=[shared.deepcopy(directed['rows'][i-1]) for i in [2,1,5,4,3,7,6,8]]
        elif mode=='last-survivor':directed['rows'][2].update(payload=50.,scrap='V ')
        elif mode=='ignored-KEEP':
            directed['schema']['echo']=shared.deepcopy(tables['raw']['schema']['echo'])
            for row in directed['rows']:row['echo']='p '
        elif mode=='descriptor-order':directed['schema']=dict(reversed(list(directed['schema'].items())))
        elif mode=='padding':directed['rows'][0]['zebra']=''
        elif mode=='raw-mutated':tables['raw']['rows'].pop()
        else:tables['legacy_directed']['rows'].pop(8)
        cases.append((mode,wrong))
    return cases


if __name__=='__main__':shared.finish_runtime_gate(qualify,'sort-directed-projection',wrong_directed_cases,directed=True)
