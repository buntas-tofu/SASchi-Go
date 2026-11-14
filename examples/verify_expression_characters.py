#!/usr/bin/env python3
"""Complete independent character-expressions original and catalog comparisons."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent))
from composition_gate_common import CompositionGate
from expression_gate_common import verify
GATE=CompositionGate(HERE,'expression_characters','6bb5e61bae45df96d864759acc7234f737183468d21155eab50865147c72bb96',12)
if __name__=='__main__':verify(GATE)
