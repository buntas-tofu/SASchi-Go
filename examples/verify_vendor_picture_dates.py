#!/usr/bin/env python3
"""Whole unchanged external date-picture example with pre-engine hand/R pins."""
from pathlib import Path
import hashlib
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.vendor_sources import verify_sources
from picture_dates_hand import build
from format_gate_common import witness,frozen,execute,complete_cli_controls,ordered_equal

FROZEN={'result.json':'cddeaca1a4dc8d93cc7980e7360e713e38a8507e34e8b496194a65ee97698d2c',
        'accounting.json':'5a623d32eb50d673db8c0369dc8efebe8ff9c59835314c59dd93451225bc29d2',
        'trace.json':'b8df3d6d84dfbab870e39027065b851eb26c43c7f7f090c1d875559126a5a282'}


def main():
    with patch('tools.vendor_sources.urlopen',side_effect=AssertionError('offline gate attempted network')):
        bound=verify_sources()['sas-code-examples-date-picture-v1']
    raw=bound['source'].read_bytes();license_bytes=bound['license'].read_bytes()
    assert len(raw)==3775 and hashlib.sha256(raw).hexdigest()=='e066c564052bb6e9467f2c3f56794e9eba8011de0fc5b027c3c6dd92948cfdfa'
    assert not bound['source'].resolve().is_relative_to(ROOT)
    text=raw.decode('ascii');values=build(text);frozen(values,FROZEN)
    independent=witness(text,'picture_dates.R')
    assert all(ordered_equal(a,b) for a,b in zip(values,independent,strict=True))
    from saschi.picture_dates import run_program,REPORT_CONTRACT
    execute(text,*values,run_program);wrong=complete_cli_controls(text,values[0],values[1],REPORT_CONTRACT)
    assert bound['source'].read_bytes()==raw and bound['license'].read_bytes()==license_bytes
    print(f'VERIFIED vendor: unchanged date-picture3775bytes,21statements+1opaque/20rows/21attempts/2reports,full hand/R trace/runtime/emitted/CLI,{wrong} wrong controls; no live SAS')


if __name__=='__main__':main()
