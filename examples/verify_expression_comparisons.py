#!/usr/bin/env python3
"""Complete independent comparisons-and-truth original and catalog comparisons."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent))
from composition_gate_common import CompositionGate
from expression_gate_common import verify
GATE=CompositionGate(HERE,'expression_comparisons','2489031fd0a1467db4659af58ef28c482b7ad30830675358ec791edc2ccedbe2',11)
if __name__=='__main__':verify(GATE)
