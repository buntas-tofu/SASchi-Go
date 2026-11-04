#!/usr/bin/env python3
"""Unchanged external postal-function target under the bounded USPS policy."""
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.vendor_sources import verify_sources
from postal_function_hand import build
from format_gate_common import witness,frozen,execute,complete_cli_controls,external_temporary,ordered_equal
from verify_postal_reference import qualify
PINS={'result.json':'033445f821aa24fccb0add8ed18d869fa638991b49e3503d93f3eec66aabd672','accounting.json':'d4bd3212072a5e697d17bf1456a4dda60bc563c9c59d34c78bbfefde64b62fdd','trace.json':'1fc0906dc2f3185fbe7c5876e3d2849df00cf6e58ff76728ff3c2466527c1bfc'}


def main():
    raw_reference,mapping=qualify();os.environ['SASCHI_POSTAL_REFERENCE']=str(raw_reference)
    with patch('tools.vendor_sources.urlopen',side_effect=AssertionError('offline vendor gate attempted network')):bound=verify_sources()['sas-code-examples-postal-function-v1']
    raw=bound['source'].read_bytes();license_bytes=bound['license'].read_bytes();assert len(raw)==3902 and hashlib.sha256(raw).hexdigest()=='39e8f17657e9aaa31f3940cbff076384a893da6f95b4ed42b49c8a116d06d417'
    assert not bound['source'].resolve().is_relative_to(ROOT)
    with external_temporary('saschi-postal-vendor-') as temp:
        reference=Path(temp)/'reference.json';reference.write_text(json.dumps(mapping,sort_keys=True,separators=(',',':'))+'\n');text=raw.decode('ascii');values=build(text,reference);frozen(values,PINS)
        assert all(ordered_equal(a,b) for a,b in zip(values,witness(text,'postal_function.R'),strict=True))
        from saschi.postal_function import run_program,REPORT_CONTRACT
        execute(text,*values,run_program);wrong=complete_cli_controls(text,values[0],values[1],REPORT_CONTRACT)
    assert bound['source'].read_bytes()==raw and bound['license'].read_bytes()==license_bytes
    print(f'VERIFIED vendor: unchanged3902byte postal target,31statements+1opaque/25rows26attempts/25callbackcells/2BYruns/1whole report,hand/R/trace/runtime/emitted/CLI,{wrong} wrong controls; bounded USPS policy,not native SAS postal-data match')


if __name__=='__main__':main()
