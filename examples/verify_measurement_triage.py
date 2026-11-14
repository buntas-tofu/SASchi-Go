#!/usr/bin/env python3
"""Complete independent measurement-exception-triage original and catalog comparisons."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent))
from composition_gate_common import CompositionGate
from expression_gate_common import verify
GATE=CompositionGate(HERE,'measurement_triage','c9da025ce63491b2bc577f9ce658a63ca9a38468c44dead4194270ec32df4988',16)
if __name__=='__main__':verify(GATE)
