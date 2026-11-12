#!/usr/bin/env python3
"""Independent complete character/missing composition evidence."""
from copy import deepcopy
from pathlib import Path
import random
import sys
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT))
from composition_gate_common import CompositionGate
from wave_gate_common import assert_result
GATE=CompositionGate(HERE,'character_composition','df951bfe6d7673df9f84119ecb94c90bcde0561b3d9c6fe262a5f69f6650ca3a',18)

def main():
    GATE.qualify([])
    if '--qualify-only' in sys.argv:
        print('QUALIFIED: complete character composition hand/base-R result before remaining group and composition integration');return
    GATE.verify({},[],[])
    from saschi.runtime import run_plan
    from saschi.plan import compile_plan
    from saschi.emit_py import translate
    import contextlib,io,json
    plan=compile_plan(GATE.source.read_text()).to_dict();translation=translate(GATE.source.read_text());rng=random.Random(10211)
    for _ in range(30):
        inputs=json.loads(GATE.inputs.read_text());inputs['raw']['rows']=[{'text':''.join(rng.choice(' aAbB|cX') for _ in range(rng.randrange(0,9))),'backup':rng.choice(['',' ','B',' Q ']),'n':rng.choice([None,0,5])} for _ in range(rng.randrange(1,13))]
        saved=deepcopy(inputs);expected=GATE.witness(inputs);result=run_plan(plan,inputs);assert_result(result,expected);assert inputs==saved
        stream=io.StringIO();namespace={'inputs':inputs}
        with contextlib.redirect_stdout(stream):exec(translation.code,namespace)
        assert_result(namespace['result'],expected);assert stream.getvalue()==''.join(x+'\n' for x in expected['log'])
    print('VERIFIED: thirty generated complete character/missing R/runtime/emitted catalogs; no new native SAS or external-program claim')

if __name__=='__main__':main()
