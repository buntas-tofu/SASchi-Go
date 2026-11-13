#!/usr/bin/env python3
"""Complete independent quoted-record composition witness."""
from copy import deepcopy
from pathlib import Path
import contextlib,hashlib,io,json,random,sys
HERE=Path(__file__).resolve().parent;ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(ROOT/'examples'));sys.path.insert(0,str(ROOT))
from composition_gate_common import CompositionGate
from wave_gate_common import assert_result
GATE=CompositionGate(HERE,'quoted_record_classification','d7558a1dcea9b491626a051e3e859fdd06c205e01a4119a50cc6ec57976f894d',26)
def catalogs():
 base=json.loads(GATE.inputs.read_text());rng=random.Random(11613)
 for index in range(30):
  inputs=deepcopy(base);inputs['raw']['rows']=[deepcopy(rng.choice(base['raw']['rows'])) for _ in range(index%13)];yield inputs
def main():
 assert hashlib.sha256((HERE/'function_wave3_oracles.R').read_bytes()).hexdigest()=='f8c21d3f849540404ec830561b8cb0854c39c568efb7dd7955ad3904205e03f3'
 GATE.qualify([])
 if '--qualify-only' in sys.argv:
  for inputs in catalogs():
   expected=GATE.witness(inputs);assert len(expected['datasets']['records']['rows'])==len(inputs['raw']['rows'])
  print('QUALIFIED: complete original hand/R and 30 catalogs before composition implementation');return
 GATE.verify({},[],[])
 from saschi.plan import compile_plan
 from saschi.runtime import run_plan
 from saschi.emit_py import translate
 source=GATE.source.read_text();plan=compile_plan(source);assert not plan.blocked,plan.tickets
 code=translate(source).code
 for inputs in catalogs():
  before=deepcopy(inputs);wanted=GATE.witness(inputs);assert_result(run_plan(plan.to_dict(),inputs),wanted)
  stream=io.StringIO();namespace={'inputs':inputs}
  with contextlib.redirect_stdout(stream):exec(code,namespace)
  assert_result(namespace['result'],wanted);assert stream.getvalue()==''.join(s+'\n' for s in wanted['log']);assert inputs==before
 print('VERIFIED: complete original and 30 independent R/runtime/emitted catalogs; six actual CLI wrong-comparison receipts')
if __name__=='__main__':main()
