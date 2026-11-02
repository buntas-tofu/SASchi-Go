"""Whole-source gate support for approved directed and descriptor SORT profiles."""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from vendor_sort_options_hand import CONFIG,build,bodies,encode
from verify_vendor_sorted_copy import ordered_equal,need,cli

FROZEN = {
 'descending': {'result.json':'8084e59a515da05cac85274da4fcf26a2a1e9621632b5244cc91918ab2edc314',
 'accounting.json':'1f172f071b0613a91ce80f4b05e50cf26085a369d16f1c56400cfa2f39e5116a',
 'trace.json':'ce9babed0ea1327a6fbbf69fc9a24ef6564f662864e13ffed3643015b6d4097b',
 'print_01.txt':'965c813bf45fcd5a95ee4d557820536b7126ad67dd3e207d729f7af78574d997',
 'print_02.txt':'b0a201e2bf8fa2a1d89cb3c23c6616be6a8360dda06e3a5f8ce242f3f21fa3c1'},
 'all': {'result.json':'7cc5a692cac03e2d7919b71c8db4092d6fe45675f378caeaff203131b41f8466',
 'accounting.json':'d84b7ed3b6275ee4b52e3cca6b43734a175b6de9373fac71b8f2cb0a6c36b778',
 'trace.json':'903c25165151917415768c24ca6b9c658d54c2b1921f341431d78f3604858c3c',
 'print_01.txt':'965c813bf45fcd5a95ee4d557820536b7126ad67dd3e207d729f7af78574d997',
 'print_02.txt':'5ded3b6171f4ef53ccd81a7318f1206fd9a97a8c2ea783a2f95fefdc73a7c5c0'},
 'survivors': {'result.json':'49a92e0267f5c84645f61f9f4ef6185116c0a78f9cea4c7a665eaa711677d3cf',
 'accounting.json':'22202b5638f501c5a12d4ccdb73054553ca5de16791531fa0179bdf908623f57',
 'trace.json':'b1b68e41d0be26e19bb8661a54d8c24efcc81015726741c09fab9a35fa874e67'},
}


PERMUTATIONS = {'0': {'source_sha256': '1422463ef46541a3e8747f2bf44ae7c533f3ac0b044fe4b36070229cec30cf58', 'schema_order': ['z', 'a', 'n'], 'kept_ordinals': [5, 4, 2, 1], 'artifact_sha256': {'result.json': '857acb716fb54b6c1b1c14549c5550c109ba7a02b9eea2602571e316751be508', 'accounting.json': 'dc9b0354d02a99fbe737c57cf643afc851cc80b88ff3fd9582f9f842f79ecd91', 'trace.json': '69330b973f97cfc5349060b0392ba71e966358609d7eca698cb3a22c3bb5da62'}}, '1': {'source_sha256': 'a78484458d1a25120bae6aedd3ebc65f634315c42d55ccdfddb8c7089b1c727e', 'schema_order': ['a', 'z', 'n'], 'kept_ordinals': [5, 1, 4, 2], 'artifact_sha256': {'result.json': 'f7dd2c7f826d71982dd3745a2961f44caa7584e449343e8b35e97340a1c8de5d', 'accounting.json': 'b58fec1a5fe19115a0a67f3a774720f50f9dfc3e2de16b994f10cadf54f43d7d', 'trace.json': 'bb1248367ab35b4abbe965ea593c1d82dedc55f30e239d1976aef33e8167c4eb'}}}


def traced_run(plan):
 from saschi import character_input,mixed_reports,runtime,sort_options
 trace=[]
 input_engine,title_engine=character_input.execute_step,mixed_reports.execute_title
 print_engine,sort_engine=mixed_reports.execute_print,sort_options.execute_sort
 def input_observer(step,tables,version=2,**kwargs):
  observations=[];table,logs=input_engine(step,tables,version,trace=observations)
  lines=step['operations'][0]['args']['source_lines']
  trace.append({'event':'data_begin','line':step['line'],'table':step['name']})
  for item in observations:
   if item['kind']=='character_input':
    event={'event':'input_attempt','line':item['line'],'record':item['attempt']}
    if item['complete']:event['record_line']=lines[3]+item['attempt']
    event['eof']=not item['complete'];trace.append(event)
   else:
    need(item['kind']=='character_output','unowned input event')
    trace.append({'event':'implicit_output','table':step['name'],'observation':item['observation']})
  trace.append({'event':'data_end','line':lines[-1],'table':step['name'],'rows':len(table['rows'])})
  return table,logs
 def title_observer(step,version=2,**kwargs):
  title=title_engine(step,version)
  event={'event':'title_reset' if title is None else 'title_set','line':step['line']}
  if title is not None:event['text']=title
  trace.append(event);return title
 def print_observer(step,tables,title=None,ordinal=1,version=2,**kwargs):
  value=print_engine(step,tables,title,ordinal,version)
  trace.append({'event':'print','line':step['line'],'table':step['inputs'][0],'report':next(iter(value)),
                'rows':len(tables[step['inputs'][0]]['rows']),'title':title})
  return value
 def sort_observer(step,tables,version=2,**kwargs):
  observations=[];value=sort_engine(step,tables,version,trace=observations)
  need(len(observations)==1,'one sort event required');trace.extend(observations);return value
 with patch.object(character_input,'execute_step',input_observer),patch.object(mixed_reports,'execute_title',title_observer),\
      patch.object(mixed_reports,'execute_print',print_observer),patch.object(sort_options,'execute_sort',sort_observer):
  result=runtime.run_plan(plan)
 return result,trace


def independent_r(source,area,expected):
 reference=area/'R'
 run=subprocess.run([os.environ.get('ROSETTA_RSCRIPT','Rscript'),str(ROOT/'examples/vendor_sort_options.R'),str(source),str(reference)],
                    capture_output=True,timeout=120)
 need(run.returncode==0,'whole-source R failed: '+run.stderr.decode(errors='replace'))
 need({p.name for p in reference.iterdir()}==set(expected),'R artifact set differs')
 for name,raw in expected.items():need((reference/name).read_bytes()==raw,'whole-source hand/R differs: '+name)


def permutation_source(order):
 schema={'z':':$2.','a':':$2.','n':''}
 rows=[{'z':'B','a':'A','n':'2'},{'z':'A','a':'Z','n':'1'},{'z':'B','a':'A','n':'2'},
       {'z':'A','a':'Y','n':'.'},{'z':'','a':'A','n':'3'}]
 text='data owned;\ninfile datalines dsd;\ninput '+' '.join(k+' '+schema[k] for k in order)+';\ndatalines4;\n'
 text+='\n'.join(','.join(row[k] for k in order) for row in rows)+'\n;;;;\nrun;\n'
 text+='proc sort data=owned out=ordered nodupkey;\nby _all_;\nrun;\n'
 return text.encode('ascii')


def qualify_permutations(area):
 from saschi.plan import compile_plan
 from saschi.runtime import run_plan
 orders=[]
 for index,order in enumerate((['z','a','n'],['a','z','n'])):
  work=area/('permutation-'+str(index));work.mkdir();raw=permutation_source(order)
  source=work/'owned.sas';source.write_bytes(raw)
  expected=bodies(raw);frozen=PERMUTATIONS[str(index)]
  need(hashlib.sha256(raw).hexdigest()==frozen['source_sha256'] and
       {n:hashlib.sha256(b).hexdigest() for n,b in expected.items()}==frozen['artifact_sha256'],
       'pre-engine descriptor permutation freeze differs')
  independent_r(source,work,expected)
  result,accounting,trace=build(raw)
  sort_event=trace[-1];orders.append(sort_event['kept_ordinals'])
  plan=compile_plan(raw.decode('ascii'));need(not plan.blocked,'owned descriptor permutation refused')
  actual,observed=traced_run(plan.to_dict())
  need(ordered_equal(actual,result) and ordered_equal(observed,trace),'descriptor-order source/runtime qualification differs')
  need(ordered_equal(run_plan(plan.to_dict()),result),'descriptor-order dispatcher differs')
 need(orders==[[5,4,2,1],[5,1,4,2]],'original descriptor-permutation pin differs')


def late_failure(area,variant):
 from saschi import sort_options
 from saschi.job import build_job
 # Owned source only. The fractional second table sorts successfully and then
 # fails the established integer-only PRINT renderer after an earlier sort.
 raw=('data first;infile datalines dsd;input c :$2. n;datalines4;\nA,2\n;;;;\nrun;\n'
      'proc sort data=first out=ordered;by c descending n;run;\n'
      'data second;infile datalines dsd;input c :$2. n;datalines4;\nB,0.5\n;;;;\nrun;\n'
      'proc sort data=second out=late;by c descending n;run;\nproc print data=late;run;')
 seen=[];engine=sort_options.execute_sort
 def observer(*args,**kwargs):
  result=engine(*args,**kwargs);seen.append(args[0]['name']);return result
 with patch.object(sort_options,'execute_sort',observer):job=build_job(raw)
 need(not job.plan.blocked and job.code==1 and job.result is None and seen==['ordered','late'],
      'actual late renderer failure did not follow completed SORTs')
 source=area/'owned-late.sas';source.write_text(raw);output=area/'late'
 run,receipt=cli(source,output)
 need(run.returncode==1 and receipt['accepted'] is False,'late CLI accepted')
 need(not any((output/n).exists() for n in ('reports','exports','result.json','observed.json')),'late failure leaked artifacts')


def run_variant(variant):
 from tools.vendor_sources import verify_sources
 from saschi.plan import compile_plan
 from saschi.emit_py import translate
 from saschi.emit_cpp import translate as translate_cpp
 config=CONFIG[variant]
 with patch('tools.vendor_sources.urlopen',side_effect=AssertionError('offline vendor gate attempted network')):
  bound=verify_sources()[config['id']]
 original=bound['source'].read_bytes();license_bytes=bound['license'].read_bytes()
 expected,accounting,expected_trace=build(original,variant);artifacts=bodies(original,variant)
 need({name:hashlib.sha256(raw).hexdigest() for name,raw in artifacts.items()}==FROZEN[variant],
      'pre-engine frozen expectation changed')
 external=Path(tempfile.gettempdir())/'saschi-sort-clusters-20261101'
 need(not external.is_symlink() and not external.resolve().is_relative_to(ROOT),'external work root is redirected')
 external.mkdir(exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='oracle-'+variant+'-',dir=external) as temporary:
  area=Path(temporary).resolve();need(not area.is_relative_to(ROOT),'vendor bodies require external storage')
  source=area/'original.sas';source.write_bytes(original);independent_r(source,area,artifacts)
  plan=compile_plan(original.decode('ascii'))
  need(not plan.blocked and len(plan.steps)==accounting['steps'],'whole source admission differs')
  rule_lines=[line for line in config['lines'] if variant!='survivors' or line not in (48,49)]
  need([line for _,_,line in plan.matched]==rule_lines,'whole source rule-application lines differ')
  actual,trace=traced_run(plan.to_dict())
  need(ordered_equal(actual,expected),'whole runtime datasets/reports differ')
  need(ordered_equal(trace,expected_trace),'whole source/runtime event schedule differs')
  emitted=translate(original.decode('ascii'));need(not emitted.blocked,'whole Python emission refused')
  namespace={};stdout=io.StringIO()
  with redirect_stdout(stdout):exec(emitted.code,namespace)
  need(stdout.getvalue()=='' and ordered_equal(namespace['result'],expected),'whole emitted outcome differs')
  need(translate_cpp(original.decode('ascii')).blocked,'unadmitted C++ accepted')
  data_path=area/'expected.json';data_path.write_bytes(encode(expected['datasets']))
  reports=expected.get('reports');report_path=area/'reports.json'
  if reports:report_path.write_bytes(encode(reports))
  output=area/'accepted';run,receipt=cli(source,output,expected=data_path,reports=report_path if reports else None)
  need(run.returncode==0 and receipt['accepted'] and receipt['comparison']=='passed','actual CLI whole comparison failed')
  need(ordered_equal(json.loads((output/'result.json').read_text()),expected),'CLI whole result differs')
  completeness=receipt['completeness']
  expected_counts=[12,9,3,0,0] if variant=='survivors' else [16,15,1,0,0]
  need([completeness[k] for k in ('n_statements','n_routed','n_unrouted','n_functions','n_tickets')]==expected_counts,
       'whole-source CLI catalog accounting differs')
  if reports:
   need(receipt['report_comparison']=='passed','CLI report comparison missing')
   for name,text in reports.items():need((output/'reports'/name).read_bytes()==text.encode('ascii'),'published report differs')
  else:need(not (output/'reports').exists(),'reportless source published reports')
  tables=expected['datasets'];first=next(iter(tables));last=list(tables)[-1]
  wrong=[]
  value=deepcopy(tables);value[first]['schema']['name']['length']=8;wrong.append(value)
  value=deepcopy(tables);value[last]['rows'][0]['score']+=1;wrong.append(value)
  value=deepcopy(tables);value[last]['rows'].reverse();wrong.append(value)
  value=deepcopy(tables);value[first]['rows'][0]['name']=value[first]['rows'][0]['name'].rstrip(' ');wrong.append(value)
  value=deepcopy(tables);value['unexpected']=deepcopy(value[first]);wrong.append(value)
  value=deepcopy(tables);value[last]['schema'].pop('score')
  for row in value[last]['rows']:row.pop('score')
  wrong.append(value)
  value=deepcopy(tables);value[last]['rows'].append(deepcopy(value[last]['rows'][0]));wrong.append(value)
  value=deepcopy(tables);table=value[last];table['schema']=dict(reversed(list(table['schema'].items())));wrong.append(value)
  # The established actual CLI comparison checks column membership, while the
  # independent whole-result check additionally binds descriptor iteration order.
  need(not ordered_equal(wrong[-1],tables),'descriptor-order comparator is weak')
  omitted=deepcopy(tables);omitted.pop(last)
  need(not ordered_equal(omitted,tables),'whole catalog completeness comparator is weak')
  for index,value in enumerate(wrong[:-1]):
   path=area/('wrong-data-'+str(index)+'.json');path.write_bytes(encode(value));dest=area/('wrong-data-'+str(index))
   failed,record=cli(source,dest,expected=path,reports=report_path if reports else None)
   need(failed.returncode==1 and record['accepted'] is False and not (dest/'reports').exists(),'wrong dataset comparator accepted/leaked: '+str(index))
  if reports:
   transforms=[lambda t:t.split('\n',1)[1],lambda t:t.rstrip('\n'),lambda t:t.replace('"',''),lambda t:t.replace('\n1 ','\n99 ',1)]
   for index,transform in enumerate(transforms):
    wrong_reports=deepcopy(reports);name=list(wrong_reports)[-1];wrong_reports[name]=transform(wrong_reports[name])
    path=area/('wrong-report-'+str(index)+'.json');path.write_bytes(encode(wrong_reports));dest=area/('wrong-report-'+str(index))
    failed,record=cli(source,dest,expected=data_path,reports=path)
    need(failed.returncode==1 and not record['accepted'] and not (dest/'reports').exists(),'wrong report accepted/leaked')
  if variant=='all':qualify_permutations(area)
  late_failure(area,variant)
  need(source.read_bytes()==original,'staged original changed')
 with patch('tools.vendor_sources.urlopen',side_effect=AssertionError('offline vendor gate attempted network')):verify_sources()
 need(bound['source'].read_bytes()==original and bound['license'].read_bytes()==license_bytes,'external pins changed')
 print('VERIFIED vendor: '+config['id']+'; unchanged'+str(config['bytes'])+'bytes; independent whole hand/baseR; '+
       str(accounting['language_statements'])+'statements+1opaque/'+str(accounting['input_records'])+'rows/'+
       str(accounting['input_attempts'])+'attempts/'+str(len(trace))+'events; actualCLI+wrongcomparators+lateatomic; no live SAS or physical-layout claim')
 return 0
