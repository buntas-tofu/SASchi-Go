"""Complete character/missing and numeric/calendar compositions,including failures."""
import contextlib
from copy import deepcopy
from datetime import date
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from examples.verify_character_composition import GATE as CHARACTER
from examples.verify_numeric_calendar_composition import GATE as NUMERIC
from examples.wave_gate_common import assert_result
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .test_do_counted import execute,job_with_inputs


class FunctionWaveCompositionTests(unittest.TestCase):
    def test_both_originals_match_complete_hand_and_independent_r_results(self):
        for gate in (CHARACTER,NUMERIC):
            with self.subTest(program=gate.prefix):
                gate.qualify([])
                inputs=json.loads(gate.inputs.read_text());wanted=gate.program_witness()
                actual,stdout=execute(gate.source.read_text(),inputs)
                assert_result(actual,wanted)
                self.assertEqual(stdout,''.join(line+'\n' for line in wanted['log']))

    def test_empty_catalogs_keep_all_descriptors_and_no_records(self):
        for gate in (CHARACTER,NUMERIC):
            with self.subTest(program=gate.prefix):
                inputs=json.loads(gate.inputs.read_text());inputs['raw']['rows']=[]
                wanted=gate.witness(inputs);actual,stdout=execute(gate.source.read_text(),inputs)
                assert_result(actual,wanted)
                self.assertEqual(stdout,'');self.assertEqual(actual['log'],[])
                self.assertTrue(all(not table['rows'] for table in actual['datasets'].values()))

    def test_catalog_values_metadata_and_order_are_not_mutated(self):
        for gate in (CHARACTER,NUMERIC):
            inputs=json.loads(gate.inputs.read_text());before=json.dumps(inputs)
            result=run_plan(compile_plan(gate.source.read_text()).to_dict(),inputs)
            assert_result(result,gate.witness(inputs))
            self.assertEqual(json.dumps(inputs),before)

    def test_complete_source_provenance_names_every_used_family(self):
        for gate,rules in [(CHARACTER,{'DS-096','DS-097','DS-098','DS-099'}),(NUMERIC,{'DS-099','DS-100','DS-101'})]:
            plan=compile_plan(gate.source.read_text());self.assertFalse(plan.blocked,plan.tickets)
            self.assertTrue(rules<={rule for _,rule,_ in plan.matched})

    def test_unqualified_profile_and_nested_contexts_stay_refused(self):
        for gate,table,column in [(CHARACTER,'prepared','n'),(NUMERIC,'summary','amount')]:
            source=gate.source.read_text()
            for changed in (source.replace('data '+table+';','data '+table+';retain held 0;'),
                            source.replace('set raw;','set raw;where '+column+'>=0;'),
                            source.replace('data '+table+';','data '+table+';array scratch a b;')):
                self.assertTrue(compile_plan(changed).blocked)
            self.assertEqual(build_job(source,inputs=gate.inputs,target='cpp').code,2)
        self.assertTrue(compile_plan(CHARACTER.source.read_text().replace('upcase(text)','upcase(right(text))')).blocked)
        self.assertTrue(compile_plan(NUMERIC.source.read_text().replace('coalesce(amount,backup)','coalesce(abs(amount),backup)')).blocked)

    def test_composed_plan_and_emitted_bytes_are_stable_across_hash_seeds(self):
        paths=[str(gate.source.relative_to(gate.root)) for gate in (CHARACTER,NUMERIC)]
        code=("from pathlib import Path;from saschi.plan import compile_plan;from saschi.emit_py import translate;"
              "import hashlib,json;paths="+repr(paths)+";print(json.dumps([[hashlib.sha256(json.dumps(compile_plan(Path(p).read_text()).to_dict(),sort_keys=True).encode()).hexdigest(),"
              "hashlib.sha256(translate(Path(p).read_text()).code.encode()).hexdigest()] for p in paths]))")
        observed=[]
        for seed in (1,2,3):
            result=subprocess.run([sys.executable,'-c',code],cwd=CHARACTER.root,env={**os.environ,'PYTHONHASHSEED':str(seed)},capture_output=True,text=True,check=True,timeout=30)
            observed.append(result.stdout)
        self.assertEqual(len(set(observed)),1)

    def test_late_cross_family_failures_publish_no_runtime_emitted_or_cli_result(self):
        maximum=(date(3999,12,31)-date(1960,1,1)).days
        cases=[
            ('case',"x=upcase(text);put x;",{'text':{'type':'character','length':8}},[{'text':'GOOD'},{'text':'é'}]),
            ('word',"x=scan(text,n,'|');put x;",{'text':{'type':'character','length':8},'n':'number'},[{'text':'A|B','n':1},{'text':'C|D','n':0}]),
            ('rewrite',"x=tranwrd(text,'a','"+'x'*51+"');put x;",{'text':{'type':'character','length':4}},[{'text':'bbbb'},{'text':'aaaa'}]),
            ('summary',"x=coalesce(a,b);put 'row';",{'a':'number','b':'number'},[{'a':1,'b':2},{'a':1,'b':{'missing':'A'}}]),
            ('numeric',"x=abs(n);put 'row';",{'n':'number'},[{'n':-2},{'n':1e-320}]),
            ('calendar',"x=intnx('DAY',d,n);put 'row';",{'d':'number','n':'number'},[{'d':0,'n':1},{'d':maximum,'n':1}])]
        for name,body,schema,rows in cases:
            with self.subTest(family=name):
                source='data d;set raw;'+body+'output;run;'
                inputs={'raw':{'schema':schema,'rows':rows}};before=json.dumps(inputs)
                plan=compile_plan(source);self.assertFalse(plan.blocked,plan.tickets)
                first=deepcopy(inputs);first['raw']['rows']=first['raw']['rows'][:1]
                valid=run_plan(plan.to_dict(),first)
                self.assertEqual(len(valid['datasets']['d']['rows']),1);self.assertEqual(len(valid['log']),1)
                with self.assertRaises(ValueError):run_plan(plan.to_dict(),inputs)
                self.assertEqual(json.dumps(inputs),before)
                stream=io.StringIO();namespace={'inputs':inputs}
                with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(source).code,namespace)
                self.assertEqual(stream.getvalue(),'');self.assertNotIn('result',namespace)
                job=job_with_inputs(source,inputs);self.assertEqual(job.code,1);self.assertIsNone(job.result)
                with tempfile.TemporaryDirectory() as directory:
                    root=Path(directory);sas=root/'job.sas';sas.write_text(source);supplied=root/'inputs.json';supplied.write_text(json.dumps(inputs));output=root/'output'
                    result=subprocess.run([sys.executable,'-m','saschi','run',str(sas),'--inputs',str(supplied),'--output',str(output)],cwd=CHARACTER.root,capture_output=True,text=True,timeout=30)
                    self.assertEqual(result.returncode,1,result.stdout+result.stderr)
                    receipt=json.loads((output/'receipt.json').read_text());self.assertFalse(receipt['accepted']);self.assertTrue(receipt['error'])
                    self.assertEqual(receipt['tickets'],[])
                    self.assertFalse((output/'result.json').exists());self.assertFalse((output/'observed.json').exists())
                    self.assertFalse((output/'exports').exists());self.assertFalse((output/'reports').exists())

    def test_late_failure_in_each_complete_composition_is_atomic(self):
        for gate,column,value in [(CHARACTER,'backup','é'),(NUMERIC,'ratio',1e-320)]:
            inputs=json.loads(gate.inputs.read_text());inputs['raw']['rows'][-1][column]=value
            job=job_with_inputs(gate.source.read_text(),inputs)
            self.assertEqual(job.code,1);self.assertIsNone(job.result);self.assertFalse(job.receipt['accepted'])


if __name__=='__main__':unittest.main()
