#!/usr/bin/env python3
"""Whole unchanged external GROUPFORMAT example with pre-engine hand/base-R pins."""
from pathlib import Path
import hashlib
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.vendor_sources import verify_sources
from groupformat_hand import build
from format_gate_common import witness,frozen,execute,complete_cli_controls,ordered_equal

FROZEN={'result.json':'a7866d37fbcfc3de95e463db2bda94b7758975945a077ae873be230644e8d070',
        'accounting.json':'ae1623fa8024dc309134db6ea668de095c0d31b3fe9cb37e585d1bc69af94210',
        'trace.json':'4871701c574edb19337d9d4cb2c0a4e9d431684a1d509ea7af3839687e3be469'}


def main():
    with patch('tools.vendor_sources.urlopen',side_effect=AssertionError('offline vendor gate attempted network')):
        bound=verify_sources()['sas-code-examples-groupformat-v1']
    raw=bound['source'].read_bytes();license_bytes=bound['license'].read_bytes()
    assert len(raw)==3828 and hashlib.sha256(raw).hexdigest()=='574ae686cae9e5b81e65da1a4d2e3565d5b100f75fa6550087047b842381c1de'
    assert not bound['source'].resolve().is_relative_to(ROOT)
    text=raw.decode('ascii');values=build(text);frozen(values,FROZEN)
    assert all(ordered_equal(a,b) for a,b in zip(values,witness(text,'groupformat.R'),strict=True))
    from saschi.groupformat import run_program,REPORT_CONTRACT
    execute(text,*values,run_program);wrong=complete_cli_controls(text,values[0],values[1],REPORT_CONTRACT)
    assert bound['source'].read_bytes()==raw and bound['license'].read_bytes()==license_bytes
    print(f'VERIFIED vendor: unchanged GROUPFORMAT3828bytes,23statements+1opaque/45rows/46attempts/8explicit outputs/1complete report,full hand/R trace/runtime/emitted/CLI,{wrong} wrong controls; no live SAS')


if __name__=='__main__':main()
