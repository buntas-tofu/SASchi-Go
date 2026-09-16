"""Compile and execute the C++ pilot against pins and the Python plan runtime."""
import os
import random
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from .emit_cpp import translate
from .plan import compile_plan
from .runtime import run_plan


class CppTests(unittest.TestCase):
    def test_compiled_backend(self):
        compiler = os.environ.get('CXX') or shutil.which('g++')
        self.assertTrue(compiler, 'C++17 compiler required for the backend gate')
        rng = random.Random(198307)
        values = [(0.25,0.1), (9.995,0.01), (-2.5,1), (0.125,0.01)]
        values += [(rng.uniform(-1e6,1e6),rng.choice([0.01,0.1,1.,10.])) for _ in range(40)]
        source = 'data _null_; X=01; class=X; sas_round=2; put x= class= sas_round=; run;\n'
        for x,u in values:
            source += f'data _null_; x=round({x!r},{u!r}); put x=; run;\n'
        source += 'data _null_; put x=; x=round(1,0); put x=; run;'
        translation = translate(source)
        self.assertFalse(translation.blocked)
        expected = run_plan(compile_plan(source).to_dict())['log']
        self.assertEqual(expected[1:5], ['x=0.30000000000000004','x=10','x=-3','x=0.13'])
        with tempfile.TemporaryDirectory() as td:
            cpp, exe = Path(td)/'program.cpp', Path(td)/'program'
            cpp.write_text(translation.code)
            result = subprocess.run([compiler, '-std=c++17', '-O2', '-ffp-contract=off', str(cpp), '-o', str(exe)], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.splitlines(), expected)

    def test_dataset_and_unsupported_constructs_block(self):
        for source in ('data d; x=1; run;', 'data _null_; set a; run;', '%let x=1;'):
            result = translate(source)
            self.assertTrue(result.blocked)
            self.assertIn('#error', result.code)
