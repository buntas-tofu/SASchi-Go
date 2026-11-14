#!/usr/bin/env python3
"""Complete independent where-composition original and catalog comparisons."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent))
from composition_gate_common import CompositionGate
from expression_gate_common import verify
GATE=CompositionGate(HERE,'expression_where','03b1a7c02ae079581443b0e29dd272469a51117e778bdd48120d03ce157a9c45',7)
if __name__=='__main__':verify(GATE)
