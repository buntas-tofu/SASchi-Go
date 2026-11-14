#!/usr/bin/env python3
"""Complete independent subsetting-if original and catalog comparisons."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent))
from composition_gate_common import CompositionGate
from expression_gate_common import verify
GATE=CompositionGate(HERE,'expression_subset','8ce5975fa6c2146d68c094324fa6f684e5ae22b24407ab218bd6942b8eff110a',8)
if __name__=='__main__':verify(GATE)
