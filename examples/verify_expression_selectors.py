#!/usr/bin/env python3
"""Complete independent selector-expressions original and catalog comparisons."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent))
from composition_gate_common import CompositionGate
from expression_gate_common import verify
GATE=CompositionGate(HERE,'expression_selectors','f56d5ae4a7d0b823e11b0134a632a9195fd33120132d8ac08db48103e53a42ed',9)
if __name__=='__main__':verify(GATE)
