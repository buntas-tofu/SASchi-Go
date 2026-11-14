"""Independent whole-program R witnesses and bounded catalog generation."""
from copy import deepcopy
import contextlib,csv,hashlib,io,json,random,tempfile
from pathlib import Path
from wave_gate_common import FamilyGate,assert_result,decode

class StatefulGate(FamilyGate):
    def witness(self,inputs):
        assert hashlib.sha256(self.source.read_bytes()).hexdigest()==self.source_sha
        base=json.loads(self.inputs.read_text());name=next(iter(base))
        assert list(inputs)==[name] and inputs[name]['schema']==base[name]['schema']
        wanted=json.loads(self.expected.read_text());actual=deepcopy(wanted)
        for table in actual['datasets'].values():table['rows']=[]
        actual['log']=[]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'input.csv'
            with path.open('w',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(inputs[name]['schema'])
                writer.writerows([row[n] for n in inputs[name]['schema']] for row in inputs[name]['rows'])
            records=self.rrun('program',self.source,path)
        assert records[0]=='STATEMENTS|'+str(self.statements)
        columns=[]
        for record in records[1:]:
            parts=record.split('|')
            if parts[0]=='COLUMNS':
                assert parts[2].split(',')==list(actual['datasets'][parts[1]]['schema'])
                columns.append(parts[1])
            elif parts[0]=='ROW':
                names=actual['datasets'][parts[1]]['schema'];assert len(parts[2:])==len(names)
                actual['datasets'][parts[1]]['rows'].append(dict(zip(names,map(decode,parts[2:]))))
            elif parts[0]=='LOG':actual['log'].append(bytes.fromhex(parts[1]).decode('ascii'))
            else:raise AssertionError(record)
        assert columns==list(actual['datasets'])
        return actual

    def program_witness(self):
        expected=json.loads(self.expected.read_text())
        assert_result(self.witness(json.loads(self.inputs.read_text())),expected)
        return expected


def catalogs(gate):
    base=json.loads(gate.inputs.read_text());name=next(iter(base));rows=base[name]['rows'];rng=random.Random(20261114)
    grouped=gate.prefix in ('stateful_groups','batch_reconciliation')
    for index in range(30):
        inputs=deepcopy(base)
        if index==0:chosen=[]
        elif index==1:chosen=deepcopy(rows[:1])
        elif index==2:
            chosen=deepcopy(rows[:1]);row=chosen[0]
            for key in ('amount','expected','value','lower','upper','enable'):
                if key in row:row[key]=None
            for key in ('code','raw_id'):
                if key in row:row[key]=' '
            if grouped:row['batch']=None
        elif index==3:chosen=deepcopy(rows)
        elif index==4:chosen=deepcopy(rows[-1:])*3
        else:
            chosen=[deepcopy(rng.choice(rows)) for _ in range(index%19)]
            for row in chosen:
                for key in ('amount','expected','value','lower','upper'):
                    if key in row:row[key]=rng.choice([None,-9,-3,0,2,7,13])
                if 'limit' in row:row['limit']=rng.choice([None,0,2,5])
                if 'enable' in row:row['enable']=rng.choice([None,0,1,-1])
                if grouped:row['batch']=rng.choice([None,-2,0,1,3])
        if grouped:chosen.sort(key=lambda row:(row['batch'] is not None,row['batch'] if row['batch'] is not None else 0))
        inputs[name]['rows']=chosen
        yield inputs


def verify(gate):
    gate.verify({},[],[])
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    from saschi.emit_py import translate
    import sas_semantics as sem
    source=gate.source.read_text();parsed=compile_plan(source);assert not parsed.blocked,parsed.tickets
    plan=parsed.to_dict();saved=deepcopy(plan);code=translate(source).code
    for inputs in catalogs(gate):
        before=deepcopy(inputs);wanted=gate.witness(inputs)
        assert_result(run_plan(plan,inputs),wanted)
        stream=io.StringIO();scope={'inputs':inputs}
        with contextlib.redirect_stdout(stream):exec(code,scope)
        assert_result(scope['result'],wanted)
        assert stream.getvalue()==''.join(s+'\n' for s in wanted['log'])
        assert inputs==before and plan==saved
    pins=json.loads((gate.directory/'stateful_kernel_pins.json').read_text())
    assert gate.r_cases([(n,a) for n,a,v in pins])==[v for n,a,v in pins]
    for name,args,wanted in pins:
        if name!='accumulate':assert sem.sas_expression_call(name,args)==wanted
        elif hasattr(sem,'sas_stateful_expression_accumulate'):assert sem.sas_stateful_expression_accumulate(*args)==wanted
    assert translate(source).code==code
    print('VERIFIED: '+gate.prefix+'; complete frozen hand/R original,30 complete R/runtime/emitted catalogs,10 contextual function pins and4 state pins,six actual CLI mismatch receipts; no native SAS')
