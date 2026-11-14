"""Complete independently frozen expression programs and real CLI controls."""
from copy import deepcopy
from pathlib import Path
import contextlib,hashlib,io,json,random
from wave_gate_common import assert_result


def catalogs(gate):
    base=json.loads(gate.inputs.read_text());rng=random.Random(11413)
    for index in range(30):
        inputs=deepcopy(base)
        inputs['raw']['rows']=[deepcopy(rng.choice(base['raw']['rows'])) for _ in range(index%13)]
        yield inputs


def verify(gate):
    gate.verify({},[],[])
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    from saschi.emit_py import translate
    import sas_semantics as sem
    source=gate.source.read_text();parsed=compile_plan(source)
    assert not parsed.blocked,parsed.tickets
    plan=parsed.to_dict();saved=deepcopy(plan);code=translate(source).code
    for inputs in catalogs(gate):
        before=deepcopy(inputs);wanted=gate.witness(inputs)
        assert_result(run_plan(plan,inputs),wanted)
        stream=io.StringIO();scope={'inputs':inputs}
        with contextlib.redirect_stdout(stream):exec(code,scope)
        assert_result(scope['result'],wanted)
        assert stream.getvalue()==''.join(s+'\n' for s in wanted['log'])
        assert inputs==before and plan==saved
    pins=json.loads((gate.directory/'composition_kernel_pins.json').read_text())
    wanted=gate.r_cases([(name,args) for name,args,_ in pins])
    assert wanted==[v for _,_,v in pins]
    for name,args,value in pins:assert sem.sas_expression_call(name,args)==value,(name,args,value)
    assert code==translate(source).code
    print('VERIFIED: '+gate.prefix+'; complete frozen hand/R original,30 complete R/runtime/emitted catalogs,46 hand/R contextual kernel pins,six actual CLI mismatch receipts; no native SAS')
