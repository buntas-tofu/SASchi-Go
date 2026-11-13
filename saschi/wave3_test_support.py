"""Shared adversarial checks for independently frozen wave-3 family witnesses."""
from copy import deepcopy
import hashlib,json,random,subprocess,sys,tempfile
from pathlib import Path
from examples.composition_gate_common import CompositionGate
from examples.wave_gate_common import assert_result
from saschi.emit_py import translate
from saschi.plan import compile_plan
from saschi.runtime import run_plan
from saschi.job import build_job
from saschi.test_do_counted import execute

ROOT=Path(__file__).resolve().parent.parent

def literal(value):
    return "'"+value.replace("'","''")+"'" if type(value) is str else '.' if value is None else '.'+value['missing'] if type(value) is dict else repr(value)

class FamilyContract:
    """Mixin, each concrete suite names its own oracle and domain cases."""
    def test_complete_original_with_independent_hand_and_R(self):
        self.gate.qualify(self.refusals)
        inputs=json.loads(self.gate.inputs.read_text());before=deepcopy(inputs)
        result,stdout=execute(self.gate.source.read_text(),inputs)
        assert_result(result,json.loads(self.gate.expected.read_text()))
        self.assertEqual(stdout,''.join(record+'\n' for record in result['log']))
        self.assertEqual(inputs,before)

    def test_thirty_complete_R_catalogs_empty_order_metadata_and_nonmutation(self):
        g=self.gate;oracle=CompositionGate(g.directory,g.prefix,g.source_sha,g.statements)
        base=json.loads(g.inputs.read_text());table=next(iter(base.values()));rng=random.Random(31113)
        plan=compile_plan(g.source.read_text()).to_dict();saved=deepcopy(plan)
        code=translate(g.source.read_text()).code
        import contextlib,io
        for index in range(30):
            inputs=deepcopy(base)
            next(iter(inputs.values()))['rows']=[deepcopy(rng.choice(table['rows'])) for _ in range(index%13)]
            before=deepcopy(inputs);wanted=oracle.witness(inputs)
            assert_result(run_plan(plan,inputs),wanted)
            stream=io.StringIO();namespace={'inputs':inputs}
            with contextlib.redirect_stdout(stream):exec(code,namespace)
            assert_result(namespace['result'],wanted)
            self.assertEqual(stream.getvalue(),''.join(s+'\n' for s in wanted['log']))
            self.assertEqual((inputs,plan),(before,saved))

    def test_frozen_hand_pins_exact_and_all_refusals(self):
        from saschi.functions import apply
        for name,args,wanted in self.gate.pins:
            self.assertEqual(apply(name,args),wanted,(name,args))
        for name,args in self.refusals:
            with self.subTest(name=name,args=str(args)[:80]),self.assertRaises(ValueError):apply(name,args)

    def test_source_provenance_and_deterministic_emission(self):
        from saschi.rules import route_function
        for name in self.names:
            sample=next((a for n,a,_ in self.gate.pins if n==name and all(v!='' for v in a)),None)
            source='data d;x='+name+'('+','.join(map(literal,sample))+');run;'
            plan=compile_plan(source)
            self.assertFalse(plan.blocked,plan.tickets)
            self.assertIn((self.family,self.rule,1),plan.matched)
            self.assertEqual(route_function(source),(self.family,self.rule))
            self.assertEqual(translate(source).code,translate(source).code)
            self.assertEqual(build_job(source,target='cpp').code,2)
            self.assertEqual(build_job(source.replace('data d;','data _null_;',1),target='cpp').code,2)

    def test_function_names_remain_valid_array_names(self):
        for name in self.names:
            source=f'data d;array {name} a b;a=1;b=2;x={name}[2];run;'
            result,_=execute(source)
            self.assertEqual(result['datasets']['d']['rows'],[{'a':1.,'b':2.,'x':2.}])

    def test_malformed_portable_calls(self):
        name,args,_=next(p for p in self.gate.pins if all(v!='' for v in p[1]))
        source='data d;x='+name+'('+','.join(map(literal,args))+');run;'
        original=compile_plan(source).to_dict()
        for arguments in (None,{},(),[],[{}],[{'kind':'number','value':True}],[{'kind':'character','value':'a','extra':1}]):
            plan=deepcopy(original);plan['steps'][0]['operations'][0]['args']['value']['args']=arguments
            with self.subTest(arguments=arguments),self.assertRaises(ValueError):run_plan(plan)
        plan=deepcopy(original);plan['version']=1
        with self.assertRaises(ValueError):run_plan(plan)

    def atomic_cli(self,source,inputs,error_fragment):
        import contextlib,io
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);src=folder/'job.sas';inp=folder/'inputs.json';out=folder/'actual-cli'
            src.write_text(source);inp.write_text(json.dumps(inputs))
            first=deepcopy(inputs)
            for table in first.values():table['rows']=table['rows'][:1]
            first_input=folder/'prefix-inputs.json';first_output=folder/'prefix-cli';first_input.write_text(json.dumps(first))
            prefix=subprocess.run([sys.executable,'-B','-m','saschi','run',str(src),'--inputs',str(first_input),'--output',str(first_output)],capture_output=True,text=True,cwd=ROOT,timeout=60)
            self.assertEqual(prefix.returncode,0,prefix.stdout+prefix.stderr)
            first_receipt=json.loads((first_output/'receipt.json').read_text())
            self.assertTrue(first_receipt['accepted']);self.assertTrue((first_output/'result.json').is_file())
            prefix_result=json.loads((first_output/'result.json').read_text());last=next(reversed(prefix_result['datasets']))
            self.assertEqual(len(prefix_result['datasets'][last]['rows']),1)
            command=[sys.executable,'-B','-m','saschi','run',str(src),'--inputs',str(inp),'--output',str(out)]
            run=subprocess.run(command,capture_output=True,text=True,cwd=ROOT,timeout=60)
            self.assertEqual(run.returncode,1,run.stdout+run.stderr)
            receipt=json.loads((out/'receipt.json').read_text())
            self.assertFalse(receipt['accepted']);self.assertEqual(receipt['tickets'],[])
            self.assertIn(error_fragment,receipt['error'])
            self.assertFalse((out/'result.json').exists());self.assertFalse((out/'observed.json').exists())
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(source).code,{'inputs':inputs})
        self.assertEqual(stream.getvalue(),'')
