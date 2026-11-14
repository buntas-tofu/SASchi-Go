#!/usr/bin/env python3
"""Complete independent numeric-expressions original and catalog comparisons."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent))
from composition_gate_common import CompositionGate
from expression_gate_common import verify
GATE=CompositionGate(HERE,'expression_numerics','00950f6fa22393f8cb333bf9f45f7e7169dc589fc86461101314ca407fab42e6',11)
if __name__=='__main__':verify(GATE)
