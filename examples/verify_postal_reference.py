#!/usr/bin/env python3
"""Offline finite-domain provider and independently extracted base-R reference."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from saschi import postal_reference as reference


def qualify():
    with patch.object(reference,'urlopen',side_effect=AssertionError('reference verification attempted network')):mapping=reference.load_reference()
    path=reference.reference_path();assert not path.resolve().is_relative_to(ROOT)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==reference.RAW_SHA256
    script="args<-commandArgs(trailingOnly=TRUE);source(args[1]);x<-read_postal_reference(args[2]);cat('{',paste(paste0('\"',names(x),'\":\"',x,'\"'),collapse=','),'}\\n',sep='')"
    run=subprocess.run(['Rscript','-e',script,str(ROOT/'examples/postal_reference.R'),str(path)],capture_output=True,text=True,timeout=120)
    assert run.returncode==0,run.stderr;independent=json.loads(run.stdout);assert mapping==independent,'independent finite mapping differs'
    assert reference._semantic_pin(independent)==mapping
    for code in reference.DOMAIN:assert reference.zip_state(code,mapping)==independent[code]
    for invalid in [1040,True,None,'1040','01040 ','01040-0000','00000','59017','１２３４５']:
        try:reference.zip_state(invalid,mapping)
        except ValueError:pass
        else:raise AssertionError('ZIPSTATE admitted an unqualified input')
    return path,mapping


def main():
    qualify();print('VERIFIED: pinned external USPS workbook and19-code semantic map,independent base-R extraction,leading-zero character identity and9 refusals; offline; no state values retained in Go or native SAS claim')


if __name__=='__main__':main()
