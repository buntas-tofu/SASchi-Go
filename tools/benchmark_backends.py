#!/usr/bin/env python3
"""Measure cold scalar execution, compilation separately, with output parity.

Status: local pilot measurement, not a production throughput claim. Uses five
fresh processes per target and includes interpreter startup and output capture.
"""
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from saschi.emit_py import translate as emit_py
from saschi.emit_cpp import translate as emit_cpp
from saschi.provenance import environment, digest


def main():
    rng = random.Random(198307)
    source = 'data _null_;\n' + '\n'.join(
        f'x=round({rng.uniform(-1e6,1e6)!r},0.1); put x=;' for _ in range(128)) + '\nrun;'
    compiler = os.environ.get('CXX') or shutil.which('g++')
    if not compiler:
        raise RuntimeError('C++17 compiler is required')
    report = {'status': 'local cold-process pilot; no production throughput claim',
              'cases': 128, 'repetitions': 5, 'environment': environment(),
              'timing_scope': 'fresh process, runtime startup, execution, output capture; compilation separate',
              'flags': ['-std=c++17','-O2','-ffp-contract=off']}
    with tempfile.TemporaryDirectory() as td:
        wd=Path(td); py=wd/'job.py'; cpp=wd/'job.cpp'; exe=wd/'job'
        py.write_text(emit_py(source).code); cpp.write_text(emit_cpp(source).code)
        report['generated_sha256']={'python':digest(py),'cpp':digest(cpp)}
        start=time.perf_counter()
        subprocess.run([compiler,*report['flags'],str(cpp),'-o',str(exe)],check=True,capture_output=True,timeout=60)
        report['compile_seconds']=time.perf_counter()-start
        expected=None
        for target,cmd in [('python',[sys.executable,str(py)]),('cpp',[str(exe)])]:
            samples=[]; rss=[]
            for _ in range(5):
                command = ['/usr/bin/time','-f','%M',*cmd] if Path('/usr/bin/time').exists() else cmd
                start=time.perf_counter()
                result=subprocess.run(command,check=True,capture_output=True,text=True,timeout=30,
                                      env={**os.environ,'PYTHONPATH':str(ROOT)})
                samples.append(time.perf_counter()-start)
                if command != cmd:
                    rss.append(int(result.stderr.strip()))
                if expected is None:
                    expected=result.stdout
                if result.stdout != expected:
                    raise RuntimeError('backend output divergence')
            report[target]={'seconds':samples,'median_seconds':statistics.median(samples),
                            'peak_rss_kib':max(rss) if rss else None}
    report['outputs_equal']=True
    path=ROOT/'telemetry'/'benchmark-backends.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    print(f'receipt -> {path}')


if __name__=='__main__':
    main()
