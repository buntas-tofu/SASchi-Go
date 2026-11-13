"""DS-102 fixed-width alignment, zero-length values and atomic execution."""
from copy import deepcopy
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from examples.verify_whitespace_alignment import GATE,REFUSALS
from sas_semantics import sas_left,sas_right,sas_compbl,sas_trimn
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .rules import route_function
from .runtime import run_plan
from .test_do_counted import execute,job_with_inputs

ROOT=Path(__file__).resolve().parent.parent
NAMES=('left','right','compbl','trimn')


def catalog(values,spec=None):
    return {'raw':{'schema':{'a':spec or {'type':'character','length':4}},'rows':[{'a':v} for v in values]}}


class WhitespaceAlignmentTests(unittest.TestCase):
    def test_independent_original_and_complete_log(self):
        GATE.qualify(REFUSALS)
        result,stdout=execute(GATE.source.read_text(),json.loads(GATE.inputs.read_text()))
        self.assertEqual(result,json.loads(GATE.expected.read_text()))
        self.assertEqual(stdout,''.join(line+'\n' for line in result['log']))

    def test_stored_padding_and_inherited_width(self):
        result,_=execute("data d;length a $5;a=' a ';l=left(a);r=right(a);c=compbl(a);t=trimn(a);run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':' a   ','l':'a    ','r':'    a','c':' a   ','t':' a   '}])
        self.assertTrue(all(spec=={'type':'character','length':5} for spec in result['datasets']['d']['schema'].values()))

    def test_existing_destination_keeps_width_and_assignment_policy(self):
        result,_=execute("data d;length x $2;x=left('  abc');y=right('ab  ');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'x':'ab','y':'  ab'}])
        self.assertEqual(result['datasets']['d']['schema'],{'x':{'type':'character','length':2},'y':{'type':'character','length':4}})

    def test_empty_helper_and_all_blank_storage_are_distinct(self):
        self.assertEqual([f('') for f in (sas_left,sas_right,sas_compbl,sas_trimn)],['']*4)
        self.assertEqual(sas_trimn('   '),'')
        self.assertEqual(sas_compbl('   '),' ')
        result,stdout=execute("data d;x=trimn('   ');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'x':'   '}])
        self.assertEqual(stdout,'')
        with self.assertRaisesRegex(ValueError,'blank character'):execute("data d;x=trimn('   ');put x;run;")

    def test_metadata_order_and_input_nonmutation(self):
        spec={'type':'character','length':4,'label':'Original','format':'$CHAR4.'}
        inputs=catalog([' a ','b'],spec);before=deepcopy(inputs)
        source='data d;set raw;l=left(a);r=right(a);run;'
        plan=compile_plan(source).to_dict();saved=deepcopy(plan)
        result=run_plan(plan,inputs)
        self.assertEqual(list(result['datasets']['d']['schema']),['a','l','r'])
        self.assertEqual(result['datasets']['d']['schema']['a'],spec)
        self.assertEqual(result['datasets']['d']['schema']['l'],{'type':'character','length':4})
        self.assertEqual((inputs,plan),(before,saved))
        self.assertEqual(run_plan(plan,inputs),result)

    def test_source_provenance_and_router(self):
        for name in NAMES:
            plan=compile_plan(f"data d;x={name}('a');run;")
            self.assertFalse(plan.blocked,plan.tickets)
            self.assertIn(('whitespace-alignment','DS-102',1),plan.matched)
            self.assertEqual(route_function(f'x={name}(a);')[1],'DS-102')

    def test_malformed_literals_are_checked_on_skipped_paths(self):
        for rhs in ("left('')","right('é')","compbl('a\tb')",'trimn(.)','left(1)',"right('a','b')"):
            with self.subTest(rhs=rhs):
                self.assertEqual(build_job('data d;if 0 then x='+rhs+';run;').code,2)

    def test_empty_input_still_checks_character_descriptors(self):
        source='data d;set raw;if 0 then x=left(a);run;'
        self.assertEqual(job_with_inputs(source,catalog([],spec='number')).code,1)
        result,_=execute(source,catalog([]))
        self.assertEqual(result['datasets']['d'],{'schema':{'a':{'type':'character','length':4},'x':{'type':'character','length':4}},'rows':[]})

    def test_dynamic_values_are_lazy_but_reached_late_error_is_atomic(self):
        for name in NAMES:
            inputs=catalog(['OK','é'])
            result,_=execute(f'data d;set raw;if 0 then x={name}(a);run;',inputs)
            self.assertEqual([r['x'] for r in result['datasets']['d']['rows']],['    ','    '])
            source=f'data d;set raw;x={name}(a);put x;output;run;'
            self.assertEqual(job_with_inputs(source,catalog(['OK'])).code,0)
            job=job_with_inputs(source,inputs)
            self.assertEqual(job.code,1);self.assertIsNone(job.result)
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):
                exec(translate(source).code,{'inputs':inputs})
            self.assertEqual(stream.getvalue(),'')

    def test_actual_cli_late_errors_publish_no_partial_data(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);data=folder/'inputs.json';data.write_text(json.dumps(catalog(['OK','é'])))
            for name in NAMES:
                source=folder/(name+'.sas');source.write_text(f'data d;set raw;x={name}(a);put x;output;run;')
                out=folder/('cli-'+name)
                run=subprocess.run([sys.executable,'-B','-m','saschi','run',str(source),'--inputs',str(data),'--output',str(out)],capture_output=True,text=True,cwd=ROOT,timeout=60)
                self.assertEqual(run.returncode,1,run.stdout+run.stderr)
                receipt=json.loads((out/'receipt.json').read_text())
                self.assertFalse(receipt['accepted']);self.assertEqual(receipt['tickets'],[])
                self.assertFalse((out/'result.json').exists());self.assertFalse((out/'observed.json').exists())

    def test_held_consumers_and_profiles(self):
        for source in ["data d;if left('a')='a' then x=1;run;","data d;set raw;where left(a)='a';run;",
                       "data d;x=left('a');put left('a');run;","data d;retain n 0;x=left('a');run;",
                       "data d;array q a;x=right('a');run;","data d;x=left(sqrt(1));run;"]:
            with self.subTest(source=source):self.assertIn(build_job(source).code,(1,2))
        self.assertEqual(build_job("data d;x=left('a');run;",target='cpp').code,2)

    def test_names_do_not_reserve_preexisting_arrays(self):
        for name in NAMES:
            result,_=execute(f'data d;array {name} a b;a=1;b=2;x={name}[2];run;')
            self.assertEqual(result['datasets']['d']['rows'],[{'a':1.,'b':2.,'x':2.}])

    def test_malformed_portable_shapes_refuse(self):
        original=compile_plan("data d;x=left('a');run;").to_dict()
        for args in (None,{},(),[],[{}],[{'kind':'character','value':'a','extra':1}],[{'kind':'number','value':True}]):
            plan=deepcopy(original);plan['steps'][0]['operations'][0]['args']['value']['args']=args
            with self.subTest(args=args),self.assertRaises(ValueError):run_plan(plan)
        plan=deepcopy(original);plan['version']=1
        with self.assertRaises(ValueError):run_plan(plan)
        plan=deepcopy(original);call=plan['steps'][0]['operations'][0]['args']['value'];call['args']=[call]
        with self.assertRaises(ValueError):run_plan(plan)

    def test_hash_seed_does_not_change_portable_or_emitted_bytes(self):
        code="import hashlib,json,sys;from saschi.plan import compile_plan;from saschi.emit_py import translate;s=sys.stdin.read();print(hashlib.sha256(json.dumps(compile_plan(s).to_dict(),sort_keys=True).encode()).hexdigest(),hashlib.sha256(translate(s).code.encode()).hexdigest())"
        results=[]
        for seed in ['1','2','99']:
            run=subprocess.run([sys.executable,'-B','-c',code],input=GATE.source.read_text(),capture_output=True,text=True,cwd=ROOT,env={**os.environ,'PYTHONHASHSEED':seed},check=True,timeout=60)
            results.append(run.stdout)
        self.assertEqual(len(set(results)),1)


if __name__=='__main__':unittest.main()
