#!/usr/bin/env python3
"""Complete independent record-eligibility-and-normalization original and catalog comparisons."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent))
from composition_gate_common import CompositionGate
from expression_gate_common import verify
GATE=CompositionGate(HERE,'record_eligibility','66b36e9b6459155344c16a49d4e4193ecbd749c4dbd37e9bdb6d89aa3efce576',15)
if __name__=='__main__':verify(GATE)
