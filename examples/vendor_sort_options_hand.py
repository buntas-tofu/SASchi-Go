"""Independent whole-source hand pins for three unchanged external SORT programs.

Vendor rows and derived bodies remain external. This module imports no translator.
"""
from copy import deepcopy
from functools import cmp_to_key
import hashlib
import json
import re

from vendor_sort_options_lex import scan, classify

CONFIG = {
 'descending': {'id':'sas-code-examples-sort-descending-v1', 'bytes':1854,
  'sha256':'70e8a5b6abd89e3427bf85d5d7d7eea920040b97b9a13fc97af97a9ab7025402',
  'lines':[13,14,15,19,35,37,38,39,41,42,43,45,46,47,48],
  'orders':[[13,3,5,2,6,10,8,14,1,4,12,11,9,7]],
  'kept':[[13,3,5,2,6,10,8,14,1,4,12,11,9,7]]},
 'all': {'id':'sas-code-examples-sort-all-v1', 'bytes':1856,
  'sha256':'23c6e50eee0b744377818d49c05e2e36669c99e5a31dd601c613c84f212edbc8',
  'lines':[15,16,17,21,37,39,40,41,43,44,45,47,48,49,50],
  'orders':[[3,5,4,10,11,12,13,14,2,1,6,7,8,9]],
  'kept':[[3,4,10,11,12,13,14,2,1,6,7,8,9]]},
 'survivors': {'id':'sas-code-examples-sort-survivors-v1', 'bytes':1886,
  'sha256':'d62f2d0563f8fd0f21a1a799f5a60cec930a485a86ab6862398e431abc34f361',
  'lines':[20,21,22,26,41,43,44,45,47,48,49],
  'orders':[[3,4,11,10,9,13,12,1,2,5,6,8,7],list(range(1,14))],
  'kept':[[3,4,11,10,9,13,12,1,2,5,6,8,7],[1,3,6,8,10,12]]},
}


def encode(value):
 return (json.dumps(value,ensure_ascii=True,separators=(',',':'),allow_nan=False)+'\n').encode()


def report(table,title):
 lines=(['TITLE: '+title] if title is not None else [])+['obs '+' '.join(table['schema'])]
 for i,row in enumerate(table['rows'],1):
  fields=[json.dumps(row[k].rstrip(' ')) if s['type']=='character' else
          '.' if row[k] is None else str(int(row[k])) for k,s in table['schema'].items()]
  if any(s['type']=='number' and row[k] is not None and row[k]!=int(row[k]) for k,s in table['schema'].items()):
   raise ValueError('integer report policy')
  lines.append(str(i)+' '+' '.join(fields))
 return '\n'.join(lines)+'\n'


def columns(text):
 rest=re.sub(r'^input\s+','',text,flags=re.I); schema={}
 while rest.strip():
  m=re.match(r'\s*([A-Za-z_][A-Za-z0-9_]*)(?:\s*:\s*\$([0-9]+)\.)?(?=\s|$)',rest)
  if m is None: raise ValueError('independent INPUT grammar')
  name=m[1].lower()
  if name in schema: raise ValueError('duplicate column')
  schema[name]={'type':'character' if m[2] else 'number','length':int(m[2]) if m[2] else 8}
  rest=rest[m.end():]
 return schema


def decode(card,schema):
 fields=card.split(',')
 if len(fields)!=len(schema): raise ValueError('field count')
 row={}
 for (key,spec),value in zip(schema.items(),fields):
  value=value.strip(' ')
  if spec['type']=='character':
   if value=='.' or len(value)>spec['length']: raise ValueError('character field')
   row[key]=value.ljust(spec['length'])
  else:
   if value not in ('','.') and re.fullmatch(r'[+-]?[0-9]+',value) is None: raise ValueError('finite integer oracle')
   row[key]=None if value in ('','.') else float(value)
 return row


def value_key(value):
 return value.rstrip(' ') if isinstance(value,str) else (0,0) if value is None else (1,value)


def order_rows(rows,keys):
 def compare(a,b):
  for name,descending in keys:
   aa,bb=value_key(rows[a-1][name]),value_key(rows[b-1][name])
   if aa!=bb: return ((aa>bb)-(aa<bb))*(-1 if descending else 1)
  return a-b
 return sorted(range(1,len(rows)+1),key=cmp_to_key(compare))


def build(original,variant=None):
 """Read complete source; vendor variants require fixed source and ordinal pins."""
 config=CONFIG[variant] if variant else None
 if config and (len(original)!=config['bytes'] or hashlib.sha256(original).hexdigest()!=config['sha256']):
  raise ValueError('whole immutable source required')
 statements,events=scan(original.decode('ascii'))
 if config and [s['line'] for s in statements]!=config['lines']: raise ValueError('statement accounting')
 tables={};reports={};trace=[];title=None;cursor=0;steps=0;attempts=0;records=0;sort_index=0
 title_sets=title_resets=0;report_records=[];last_order=[];last_kept=[];sort_rows=0
 while cursor<len(events):
  item=events[cursor]
  if item['kind']!='statement': raise ValueError('unowned payload')
  text=item['text'];normal=' '.join(text.lower().split())
  if normal.startswith('data '):
   name=re.fullmatch(r'data\s+([A-Za-z_][A-Za-z0-9_]*)',text,re.I)[1].lower()
   if ' '.join(events[cursor+1]['text'].lower().split())!='infile datalines dsd': raise ValueError('INFILE')
   declaration=events[cursor+2];schema=columns(declaration['text']);payload=events[cursor+4]
   if events[cursor+3]['text'].lower()!='datalines4' or payload['kind']!='opaque_data' or events[cursor+5]['text'].lower()!='run': raise ValueError('whole data block')
   rows=[decode(card,schema) for card in payload['records']]
   tables[name]={'schema':schema,'rows':rows}
   trace.append({'event':'data_begin','line':item['line'],'table':name})
   for i in range(len(rows)):
    trace.append({'event':'input_attempt','line':declaration['line'],'record':i+1,'record_line':payload['line']+i,'eof':False})
    trace.append({'event':'implicit_output','table':name,'observation':i+1})
   trace += [{'event':'input_attempt','line':declaration['line'],'record':len(rows)+1,'eof':True},
             {'event':'data_end','line':events[cursor+5]['line'],'table':name,'rows':len(rows)}]
   records+=len(rows);attempts+=len(rows)+1;cursor+=6
  elif normal=='title' or normal.startswith('title '):
   if normal=='title':
    title=None;title_resets+=1;trace.append({'event':'title_reset','line':item['line']})
   else:
    literal=text[5:].strip();q=literal[0]
    if q not in ('"',"'") or literal[-1]!=q: raise ValueError('TITLE literal')
    title=literal[1:-1].replace(q*2,q);title_sets+=1
    trace.append({'event':'title_set','line':item['line'],'text':title})
   cursor+=1
  elif normal.startswith('proc print '):
   name=re.fullmatch(r'proc\s+print\s+data\s*=\s*([A-Za-z_][A-Za-z0-9_]*)',text,re.I)[1].lower()
   if events[cursor+1]['text'].lower()!='run': raise ValueError('PRINT RUN')
   basename='print_%02d.txt'%(len(reports)+1);reports[basename]=report(tables[name],title)
   report_records.append(len(reports[basename].splitlines()))
   trace.append({'event':'print','line':item['line'],'table':name,'report':basename,'rows':len(tables[name]['rows']),'title':title});cursor+=2
  elif normal.startswith('proc sort '):
   m=re.fullmatch(r'proc\s+sort\s+data\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\s+out\s*=\s*([A-Za-z_][A-Za-z0-9_]*)(\s+nodupkey)?',text,re.I)
   if not m or events[cursor+2]['text'].lower()!='run': raise ValueError('SORT grammar')
   source,destination=m[1].lower(),m[2].lower();table=tables[source]
   terms=events[cursor+1]['text'].split()[1:];keys=[];pos=0
   if [t.lower() for t in terms]==['_all_']:
    if not m[3]: raise ValueError('ALL NODUPKEY required')
    keys=[(k,False) for k in table['schema']]
   else:
    while pos<len(terms):
     descending=terms[pos].lower()=='descending'
     if descending:pos+=1
     keys.append((terms[pos].lower(),descending));pos+=1
   order=order_rows(table['rows'],keys);kept=[];seen=[]
   for ordinal in order:
    key=[value_key(table['rows'][ordinal-1][k]) for k,_ in keys]
    if not m[3] or key not in seen: kept.append(ordinal)
    seen.append(key)
   if config and (order!=config['orders'][sort_index] or kept!=config['kept'][sort_index]): raise ValueError('pre-engine ordinal pin differs')
   last_order,last_kept=order,kept;sort_rows+=len(order);sort_index+=1
   tables[destination]={'schema':deepcopy(table['schema']),'rows':[deepcopy(table['rows'][i-1]) for i in kept]}
   trace.append({'event':'sort','line':item['line'],'source':source,'destination':destination,'source_ordinals':order,'kept_ordinals':kept});cursor+=3
  else: raise ValueError('unconsumed source')
  steps+=1
 result={'datasets':tables,'log':[]}
 if reports:result['reports']=reports
 accounting={'language_statements':len(statements),'opaque_payloads':sum(e['kind']=='opaque_data' for e in events),
             'steps':steps,'input_records':records,'data_iterations':records,'input_attempts':attempts,'implicit_outputs':records,
             'sort_rows':sort_rows,'sort_source_ordinals':last_order,'sort_kept_ordinals':last_kept,'title_sets':title_sets,
             'title_resets':title_resets,'prints':len(reports),'report_records':report_records,'final_title':title}
 return result,accounting,trace


def bodies(original,variant=None):
 result,accounting,trace=build(original,variant)
 return {'result.json':encode(result),'accounting.json':encode(accounting),'trace.json':encode(trace),
         **{k:v.encode('ascii') for k,v in result.get('reports',{}).items()}}
