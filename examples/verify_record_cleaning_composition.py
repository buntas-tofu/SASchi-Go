#!/usr/bin/env python3
"""Independent complete record-cleaning composition program gate."""
from copy import deepcopy
from pathlib import Path
import contextlib,hashlib,io,json,random,sys
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(ROOT/'examples'));sys.path.insert(0,str(ROOT))
from composition_gate_common import CompositionGate
from wave_gate_common import assert_result
GATE=CompositionGate(HERE,'record_cleaning_composition','a6eaa7696dbdf906ea3cde6a8ddeaf78efcb46caf42c8911fba343e54017769c',16)
def catalogs():
    rng=random.Random(10916)
    for _ in range(30):
        inputs=json.loads(GATE.inputs.read_text())
        inputs['raw']['rows']=[{'label':''.join(rng.choice('  abAZ-19') for _ in range(rng.randrange(13))),
                              'code':''.join(rng.choice('  012AZ-_') for _ in range(rng.randrange(7))),
                              'tag':''.join(rng.choice(' aBZ0') for _ in range(rng.randrange(4)))} for _ in range(rng.randrange(13))]
        yield inputs
def main():
    assert hashlib.sha256((HERE/'function_wave2_oracles.R').read_bytes()).hexdigest()=='0962a3bb9efef5dcbf684e005d1e9b6089a10267087dba3b26e66bca5e7f4b29'
    GATE.qualify([])
    if '--qualify-only' in sys.argv:
        for inputs in catalogs():
            expected=GATE.witness(inputs)
            assert len(expected['datasets']['raw']['rows'])==len(inputs['raw']['rows'])
            assert len(expected['datasets']['cleaned']['rows'])==len(inputs['raw']['rows'])
        print('QUALIFIED: complete original hand/R record-cleaning and30generated catalogs before implementation');return
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
    print('VERIFIED:30generated complete record-cleaning R/runtime/emitted catalogs')
if __name__=='__main__':main()
