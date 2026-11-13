"""Complete original-program consumers across the second function wave."""
from copy import deepcopy
import contextlib,io,json,os
from pathlib import Path
import subprocess,sys,tempfile,unittest
from examples.verify_record_cleaning_composition import GATE,catalogs
from .emit_py import translate
from .plan import compile_plan
from .runtime import run_plan
from .test_do_counted import execute,job_with_inputs
ROOT=Path(__file__).resolve().parent.parent

class RecordCleaningCompositionTests(unittest.TestCase):
    def test_frozen_complete_original_tables_metadata_and_log(self):
        GATE.qualify([])
        result,stdout=execute(GATE.source.read_text(),json.loads(GATE.inputs.read_text()))
        self.assertEqual(result,json.loads(GATE.expected.read_text()))
        self.assertEqual(stdout,''.join(x+'\n' for x in result['log']))
        self.assertEqual(len(result['datasets']['cleaned']['schema']),11)

    def test_generated_complete_catalogs_runtime_and_emitted(self):
        source=GATE.source.read_text();plan=compile_plan(source);emitted=translate(source)
        for inputs in catalogs():
            expected=GATE.witness(inputs);saved=deepcopy(inputs);serialized=plan.to_dict();before=deepcopy(serialized)
            result=run_plan(serialized,inputs);self.assertEqual(result,expected)
            stream=io.StringIO();namespace={'inputs':inputs}
            with contextlib.redirect_stdout(stream):exec(emitted.code,namespace)
            self.assertEqual(namespace['result'],expected);self.assertEqual(stream.getvalue(),''.join(x+'\n' for x in expected['log']))
            self.assertEqual((serialized,inputs),(before,saved))

    def test_empty_input_preserves_all_declared_columns(self):
        inputs=json.loads(GATE.inputs.read_text());inputs['raw']['rows']=[]
        result,stdout=execute(GATE.source.read_text(),inputs)
        self.assertEqual(result,GATE.witness(inputs));self.assertEqual(stdout,'')
        self.assertEqual(len(result['datasets']['cleaned']['schema']),11)

    def test_blank_fields_retain_identifier_and_independent_decisions(self):
        inputs=json.loads(GATE.inputs.read_text());inputs['raw']['rows']=[{'label':'','code':'','tag':''}]
        result,_=execute(GATE.source.read_text(),inputs);self.assertEqual(result,GATE.witness(inputs))
        row=result['datasets']['cleaned']['rows'][0]
        self.assertEqual((row['key'],row['words'],row['pos'],row['accepted'],row['blank_label']),('-'.ljust(200),0,0,1,1))

    def test_late_bad_record_publishes_no_partial_output(self):
        inputs=json.loads(GATE.inputs.read_text());inputs['raw']['rows']=inputs['raw']['rows'][:1]+[{'label':'é','code':'1','tag':'a'}]
        source=GATE.source.read_text();job=job_with_inputs(source,inputs)
        self.assertEqual(job.code,1);self.assertIsNone(job.result)
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(source).code,{'inputs':inputs})
        self.assertEqual(stream.getvalue(),'')
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);data=folder/'inputs.json';data.write_text(json.dumps(inputs));out=folder/'cli'
            run=subprocess.run([sys.executable,'-B','-m','saschi','run',str(GATE.source),'--inputs',str(data),'--output',str(out)],capture_output=True,text=True,cwd=ROOT,timeout=60)
            self.assertEqual(run.returncode,1,run.stdout+run.stderr)
            receipt=json.loads((out/'receipt.json').read_text());self.assertFalse(receipt['accepted']);self.assertEqual(receipt['tickets'],[])
            self.assertFalse((out/'result.json').exists());self.assertFalse((out/'observed.json').exists())

    def test_complete_emission_hash_seed_determinism(self):
        script='from saschi.emit_py import translate;import sys;sys.stdout.write(translate(sys.stdin.read()).code)';codes=[]
        for seed in ('2','101'):
            run=subprocess.run([sys.executable,'-B','-c',script],input=GATE.source.read_text(),capture_output=True,text=True,cwd=ROOT,env={**os.environ,'PYTHONHASHSEED':seed},timeout=60)
            self.assertEqual(run.returncode,0,run.stderr);codes.append(run.stdout)
        self.assertEqual(codes[0],codes[1])

from examples.verify_timestamp_measurement_composition import GATE as TIMESTAMP_GATE,catalogs as timestamp_catalogs

class TimestampMeasurementCompositionTests(unittest.TestCase):
    def test_frozen_complete_original_and_log(self):
        gate=TIMESTAMP_GATE;gate.qualify([])
        result,stdout=execute(gate.source.read_text(),json.loads(gate.inputs.read_text()))
        self.assertEqual(result,json.loads(gate.expected.read_text()))
        self.assertEqual(stdout,''.join(x+'\n' for x in result['log']))
        self.assertEqual(len(result['datasets']['reconciled']['schema']),28)

    def test_generated_complete_catalogs_runtime_and_emitted(self):
        gate=TIMESTAMP_GATE;source=gate.source.read_text();plan=compile_plan(source);emitted=translate(source)
        for inputs in timestamp_catalogs():
            expected=gate.witness(inputs);saved=deepcopy(inputs);serialized=plan.to_dict();before=deepcopy(serialized)
            result=run_plan(serialized,inputs);self.assertEqual(result,expected)
            stream=io.StringIO();namespace={'inputs':inputs}
            with contextlib.redirect_stdout(stream):exec(emitted.code,namespace)
            self.assertEqual(namespace['result'],expected);self.assertEqual(stream.getvalue(),''.join(x+'\n' for x in expected['log']))
            self.assertEqual((serialized,inputs),(before,saved))

    def test_empty_input_preserves_full_schema(self):
        gate=TIMESTAMP_GATE;inputs=json.loads(gate.inputs.read_text());inputs['raw']['rows']=[]
        result,stdout=execute(gate.source.read_text(),inputs)
        self.assertEqual(result,gate.witness(inputs));self.assertEqual(stdout,'')
        self.assertEqual(len(result['datasets']['reconciled']['schema']),28)

    def test_all_missing_and_singleton_statistics(self):
        gate=TIMESTAMP_GATE;inputs=json.loads(gate.inputs.read_text());row=deepcopy(inputs['raw']['rows'][0]);row.update(a=None,b=None,c=None)
        second=deepcopy(row);second.update(a=5)
        inputs['raw']['rows']=[row,second];result,_=execute(gate.source.read_text(),inputs)
        self.assertEqual(result,gate.witness(inputs));a,b=result['datasets']['reconciled']['rows']
        self.assertTrue(all(a[key] is None for key in ('mid','spread','variance','deviation','average','magnitude')))
        self.assertEqual((b['mid'],b['spread'],b['variance'],b['deviation'],b['average'],b['magnitude']),(5,0,None,None,5,5))

    def test_late_component_and_reading_faults_are_atomic(self):
        gate=TIMESTAMP_GATE;source=gate.source.read_text()
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            for name,value in [('sc',65),('a',.5)]:
                inputs=json.loads(gate.inputs.read_text());row=deepcopy(inputs['raw']['rows'][0]);bad=deepcopy(row);bad[name]=value;inputs['raw']['rows']=[row,bad]
                job=job_with_inputs(source,inputs);self.assertEqual(job.code,1);self.assertIsNone(job.result)
                stream=io.StringIO()
                with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(source).code,{'inputs':inputs})
                self.assertEqual(stream.getvalue(),'')
                data=folder/(name+'.json');data.write_text(json.dumps(inputs));out=folder/('cli-'+name)
                run=subprocess.run([sys.executable,'-B','-m','saschi','run',str(gate.source),'--inputs',str(data),'--output',str(out)],capture_output=True,text=True,cwd=ROOT,timeout=60)
                self.assertEqual(run.returncode,1,run.stdout+run.stderr)
                receipt=json.loads((out/'receipt.json').read_text());self.assertFalse(receipt['accepted']);self.assertEqual(receipt['tickets'],[])
                self.assertFalse((out/'result.json').exists());self.assertFalse((out/'observed.json').exists())

    def test_complete_program_is_independent_of_process_timezone(self):
        gate=TIMESTAMP_GATE;source=gate.source.read_text();inputs=json.loads(gate.inputs.read_text())
        script='from saschi.plan import compile_plan;from saschi.runtime import run_plan;import json,sys;request=json.load(sys.stdin);print(json.dumps(run_plan(compile_plan(request["source"]).to_dict(),request["inputs"])))'
        wanted=gate.witness(inputs)
        for zone in ('UTC','Pacific/Honolulu','Asia/Tokyo'):
            run=subprocess.run([sys.executable,'-B','-c',script],input=json.dumps({'source':source,'inputs':inputs}),capture_output=True,text=True,cwd=ROOT,env={**os.environ,'TZ':zone},timeout=60)
            self.assertEqual(run.returncode,0,run.stderr);self.assertEqual(json.loads(run.stdout),wanted)

if __name__=='__main__':unittest.main()
