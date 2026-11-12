#!/usr/bin/env python3
"""Independent complete numeric-summary/calendar composition evidence."""
from copy import deepcopy
from datetime import date
from pathlib import Path
import random
import sys
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT))
from composition_gate_common import CompositionGate
from wave_gate_common import assert_result
GATE=CompositionGate(HERE,'numeric_calendar_composition','61b549ff1bcddb14931898b8fb23bfd5ca0a1a741ab35f9d45be67bea907a033',21)

def main():
    GATE.qualify([])
    if '--qualify-only' in sys.argv:
        print('QUALIFIED: complete numeric/calendar composition hand/base-R result before remaining group and composition integration');return
    GATE.verify({},[],[])
    from saschi.runtime import run_plan
    from saschi.plan import compile_plan
    from saschi.emit_py import translate
    import contextlib,io,json
    plan=compile_plan(GATE.source.read_text()).to_dict();translation=translate(GATE.source.read_text());rng=random.Random(10311);epoch=date(1960,1,1)
    for _ in range(30):
        inputs=json.loads(GATE.inputs.read_text());inputs['raw']['rows']=[{'amount':rng.choice([None,rng.randrange(-100,101)]),'backup':rng.choice([None,rng.randrange(-100,101)]),'ratio':rng.choice([-1.25,2.5,1+2**-40,-1-2**-40]),'d':(date(rng.randrange(2000,2031),rng.randrange(1,13),rng.randrange(1,29))-epoch).days,'ending':(date(rng.randrange(2000,2031),rng.randrange(1,13),rng.randrange(1,29))-epoch).days,'move':rng.randrange(-12,13)} for _ in range(rng.randrange(1,13))]
        saved=deepcopy(inputs);expected=GATE.witness(inputs);result=run_plan(plan,inputs);assert_result(result,expected);assert inputs==saved
        stream=io.StringIO();namespace={'inputs':inputs}
        with contextlib.redirect_stdout(stream):exec(translation.code,namespace)
        assert_result(namespace['result'],expected);assert stream.getvalue()==''.join(x+'\n' for x in expected['log'])
    print('VERIFIED: thirty generated complete numeric/calendar R/runtime/emitted catalogs; no new native SAS or external-program claim')

if __name__=='__main__':main()
