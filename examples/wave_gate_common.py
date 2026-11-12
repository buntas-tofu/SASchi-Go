"""Independent-R transport and complete original-program verification helpers."""
import contextlib
from copy import deepcopy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REFUSED=object()


def assert_result(actual,expected):
    from saschi.compare import equal,table_equal
    assert equal(actual,expected),(actual,expected)
    assert list(actual['datasets'])==list(expected['datasets'])
    for name in expected['datasets']:
        assert table_equal(actual['datasets'][name],expected['datasets'][name]),name


def encode(value):
    if type(value) is str:return 'c:'+value.encode('utf-8').hex()
    if value is None:return 'm:'
    if type(value) is bool:return 'b:1'
    if type(value) is dict:return 't:'+value['missing']
    return 'n:'+str(value)


def decode(value):
    if value=='REFUSE':return REFUSED
    if value.startswith('c:'):return bytes.fromhex(value[2:]).decode('ascii')
    if value=='m:':return None
    if value.startswith('n:'):return float(value[2:])
    raise AssertionError('oracle transport')


class FamilyGate:
    def __init__(self,directory,prefix,source_sha,statements):
        self.directory=Path(directory);self.prefix=prefix
        self.root=next(p for p in self.directory.parents if (p/'sas_semantics.py').is_file())
        self.source=self.directory/(prefix+'_capture.sas')
        self.inputs=self.directory/(prefix+'_inputs.json')
        self.expected=self.directory/(prefix+'_expected.json')
        self.pins=json.loads((self.directory/(prefix+'_pins.json')).read_text())
        self.source_sha=source_sha;self.statements=statements

    def rrun(self,mode,*paths):
        command=[os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript',str(self.directory/(self.prefix+'.R')),mode,*map(str,paths)]
        return subprocess.run(command,capture_output=True,text=True,check=True,timeout=60).stdout.splitlines()

    def r_cases(self,cases):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'cases.csv'
            with path.open('w',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(['name','args'])
                writer.writerows((name,'|'.join(map(encode,args))) for name,args in cases)
            records=self.rrun('cases',path)
        assert len(records)==len(cases)
        return list(map(decode,records))

    def program_witness(self):
        assert hashlib.sha256(self.source.read_bytes()).hexdigest()==self.source_sha
        expected=json.loads(self.expected.read_text());actual=deepcopy(expected)
        for table in actual['datasets'].values():table['rows']=[]
        actual['log']=[]
        inputs=json.loads(self.inputs.read_text());table=next(iter(inputs.values()))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'input.csv'
            with path.open('w',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(table['schema'])
                writer.writerows([row[name] for name in table['schema']] for row in table['rows'])
            records=self.rrun('program',self.source,path)
        assert records[0]=='STATEMENTS|'+str(self.statements)
        for record in records[1:]:
            parts=record.split('|')
            if parts[0]=='ROW':
                schema=actual['datasets'][parts[1]]['schema']
                assert len(parts[2:])==len(schema)
                actual['datasets'][parts[1]]['rows'].append(dict(zip(schema,map(decode,parts[2:]))))
            elif parts[0]=='LOG':actual['log'].append(bytes.fromhex(parts[1]).decode('ascii'))
            else:raise AssertionError(record)
        assert actual==expected,(actual,expected)
        return expected

    def qualify(self,refusals):
        assert self.r_cases([(name,args) for name,args,_ in self.pins])==[value for _,_,value in self.pins]
        assert all(value is REFUSED for value in self.r_cases(refusals))
        self.program_witness()

    def verify(self,functions,cases,refusals,widths=None):
        from saschi.compare import equal
        from saschi.plan import compile_plan
        from saschi.runtime import run_plan
        from saschi.emit_py import translate
        from saschi.job import build_job
        self.qualify(refusals)
        all_cases=[(name,args) for name,args,_ in self.pins]+cases
        expected=self.r_cases(all_cases+refusals)
        for (name,args),wanted in zip(all_cases+refusals,expected):
            if wanted is REFUSED:
                try:functions[name](*args)
                except ValueError:pass
                else:raise AssertionError(('missing refusal',name,args))
                continue
            actual=functions[name](*args)
            assert equal(actual,wanted),(name,args,actual,wanted)
            literals=["'"+value.replace("'","''")+"'" if type(value) is str else '.' if value is None else '.'+value['missing'] if type(value) is dict else repr(value) for value in args]
            source='data d;x='+name+'('+','.join(literals)+');run;'
            plan=compile_plan(source);assert not plan.blocked,plan.tickets
            table=run_plan(plan.to_dict())['datasets']['d']
            if type(wanted) is str:
                width=widths[name](args);wanted=wanted[:width].ljust(width)
                assert table['schema']['x']=={'type':'character','length':width}
            assert equal(table['rows'],[{'x':wanted}]),(source,table,wanted)
        wanted=self.program_witness();source=self.source.read_text();inputs=json.loads(self.inputs.read_text())
        plan=compile_plan(source);assert not plan.blocked,plan.tickets
        assert_result(run_plan(plan.to_dict(),inputs),wanted)
        stream=io.StringIO();namespace={'inputs':inputs}
        with contextlib.redirect_stdout(stream):exec(translate(source).code,namespace)
        assert_result(namespace['result'],wanted)
        assert stream.getvalue()==''.join(x+'\n' for x in wanted['log'])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);expect=root/'expected.json';expect.write_text(json.dumps(wanted['datasets']))
            log=root/'log.json';log.write_text(json.dumps(wanted['log']))
            job=build_job(source,inputs=self.inputs,expect=expect,expect_log=log)
            assert job.code==0 and job.receipt['accepted']
            assert build_job(source,inputs=self.inputs,target='cpp').code==2
            command=[sys.executable,'-m','saschi','run',str(self.source),'--inputs',str(self.inputs),'--expect',str(expect),'--expect-log',str(log),'--output',str(root/'cli')]
            good=subprocess.run(command,capture_output=True,text=True,cwd=self.root,timeout=60)
            assert good.returncode==0,good.stderr+good.stdout
            assert_result(json.loads((root/'cli/result.json').read_text()),wanted)
            good_receipt=json.loads((root/'cli/receipt.json').read_text())
            assert good_receipt['accepted'] and good_receipt['comparison']=='passed' and good_receipt['log_comparison']=='passed'
            table_name=next(reversed(wanted['datasets']));original=wanted['datasets'][table_name]
            for mutation in ('value','type','order','metadata','column-order'):
                bad=deepcopy(wanted['datasets']);table=bad[table_name];column=next(iter(table['schema']))
                if mutation=='value':
                    value=table['rows'][0][column];table['rows'][0][column]=value+'!' if type(value) is str else 987654321
                elif mutation=='type':table['rows'][0][column]=False
                elif mutation=='order':
                    table['rows'].reverse()
                    if table['rows']==original['rows']:table['rows'].append(deepcopy(table['rows'][0]))
                elif mutation=='column-order':table['schema']=dict(reversed(list(table['schema'].items())))
                else:
                    spec=table['schema'][column]
                    table['schema'][column]={**({'type':spec} if type(spec) is str else spec),'label':'wrong metadata'}
                expect.write_text(json.dumps(bad))
                output=root/('wrong-'+mutation)
                wrong=subprocess.run(command[:-1]+[str(output)],capture_output=True,text=True,cwd=self.root,timeout=60)
                assert wrong.returncode==1,(mutation,wrong.stdout,wrong.stderr)
                receipt=json.loads((output/'receipt.json').read_text())
                assert not receipt['accepted'] and receipt['comparison']=='failed' and receipt['error'].startswith('expected dataset differs:'),receipt
                assert receipt['log_comparison']=='passed' and (output/'observed.json').is_file() and not (output/'result.json').exists()
            expect.write_text(json.dumps(wanted['datasets']));log.write_text(json.dumps(wanted['log']+['wrong record']))
            output=root/'wrong-log'
            wrong=subprocess.run(command[:-1]+[str(output)],capture_output=True,text=True,cwd=self.root,timeout=60)
            assert wrong.returncode==1,(wrong.stdout,wrong.stderr)
            receipt=json.loads((output/'receipt.json').read_text())
            assert not receipt['accepted'] and receipt['log_comparison']=='failed' and receipt['error']=='expected ordered log record bytes differ',receipt
            assert (output/'observed.json').is_file() and not (output/'result.json').exists()
        print('VERIFIED: '+self.prefix+'; '+str(len(self.pins))+'hand pins,'+str(len(cases))+'generated source/runtime/R cases,'+str(len(refusals))+'shared refusals,complete original/emitted/CLI,six receipt-verified wrong CLI controls; no live SAS')
