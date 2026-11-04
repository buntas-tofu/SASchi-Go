#!/usr/bin/env python3
"""Whole unchanged external function-backed date-format target."""
from pathlib import Path
import hashlib
import sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.vendor_sources import verify_sources
from week_callbacks_hand import build
from format_gate_common import witness,frozen,execute,complete_cli_controls,ordered_equal
PINS={'result.json':'2efa8e4b25157705f4d8d7c9bb87c95b63ae8f4e1cc0364fed6bd17e6e050207','accounting.json':'f205353dcf15cd1239a6b3f42d71fe997339aa00eb343a7a20e0caa9967ade2b','trace.json':'87fcd75846a49fbe97ca57300a5515e096f22048d6001e16024ea497abe89497'}


def main():
    with patch('tools.vendor_sources.urlopen',side_effect=AssertionError('offline gate attempted network')):bound=verify_sources()['sas-code-examples-week-callbacks-v1']
    raw=bound['source'].read_bytes();license_bytes=bound['license'].read_bytes();assert len(raw)==3127 and hashlib.sha256(raw).hexdigest()=='129d54f964ed66fb2dbf591d1b38b12f39d60e9e718e273d1c7a33a367617111'
    assert not bound['source'].resolve().is_relative_to(ROOT);text=raw.decode('ascii');values=build(text);frozen(values,PINS)
    assert all(ordered_equal(a,b) for a,b in zip(values,witness(text,'week_callbacks.R'),strict=True))
    from saschi.week_callbacks import run_program,REPORT_CONTRACT
    execute(text,*values,run_program);wrong=complete_cli_controls(text,values[0],values[1],REPORT_CONTRACT)
    assert bound['source'].read_bytes()==raw and bound['license'].read_bytes()==license_bytes
    print(f'VERIFIED vendor: unchanged3127byte week callback source,30statements+1opaque,10rows/11attempts,20callbackcalls,1whole ORDER/spanned report,hand/R/fulltrace/runtime/emitted/CLI,{wrong} wrong controls; no live SAS')


if __name__=='__main__':main()
