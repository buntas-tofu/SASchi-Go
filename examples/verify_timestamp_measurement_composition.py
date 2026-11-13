#!/usr/bin/env python3
"""Independent complete timestamp/measurement program and generated catalogs."""
from copy import deepcopy
from pathlib import Path
import contextlib,hashlib,io,json,random,sys
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(ROOT/'examples'));sys.path.insert(0,str(ROOT))
from composition_gate_common import CompositionGate
from wave_gate_common import assert_result
GATE=CompositionGate(HERE,'timestamp_measurement_composition','2e50e9e204211c26c96afab9a2c8e7622e70a6fa2c857829f6711b6cf3a6f086',27)
def catalogs():
    rng=random.Random(11027)
    for _ in range(30):
        inputs=json.loads(GATE.inputs.read_text());rows=[]
        for i in range(rng.randrange(13)):
            row={'id':f'r{i:02d}','day':rng.choice([None,rng.randrange(-75604,745095)]),
                 'hr':rng.choice([None,rng.randrange(24)]),'mn':rng.randrange(60),'sc':rng.randrange(60)}
            row.update({name:rng.choice([None,rng.randrange(-500,501)]) for name in ('a','b','c')})
            rows.append(row)
        inputs['raw']['rows']=rows
        yield inputs
def main():
    assert hashlib.sha256((HERE/'function_wave2_oracles.R').read_bytes()).hexdigest()=='0962a3bb9efef5dcbf684e005d1e9b6089a10267087dba3b26e66bca5e7f4b29'
    GATE.qualify([])
    if '--qualify-only' in sys.argv:
        for inputs in catalogs():
            expected=GATE.witness(inputs)
            assert len(expected['datasets']['raw']['rows'])==len(inputs['raw']['rows'])
            assert len(expected['datasets']['reconciled']['rows'])==len(inputs['raw']['rows'])
        print('QUALIFIED: original timestamp/measurement hand/R and30generated catalogs before implementation');return
    GATE.verify({},[],[])
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    from saschi.emit_py import translate
    source=GATE.source.read_text();plan=compile_plan(source);assert not plan.blocked,plan.tickets
    emitted=translate(source)
    for inputs in catalogs():
        saved=deepcopy(inputs);expected=GATE.witness(inputs);result=run_plan(plan.to_dict(),inputs)
        assert_result(result,expected);assert inputs==saved
        stream=io.StringIO();namespace={'inputs':inputs}
        with contextlib.redirect_stdout(stream):exec(emitted.code,namespace)
        assert_result(namespace['result'],expected);assert stream.getvalue()==''.join(line+'\n' for line in expected['log'])
    print('VERIFIED:30generated complete timestamp/measurement R/runtime/emitted catalogs')
if __name__=='__main__':main()
