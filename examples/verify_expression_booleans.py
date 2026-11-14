#!/usr/bin/env python3
"""Complete independent boolean-conditions original and catalog comparisons."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent))
from composition_gate_common import CompositionGate
from expression_gate_common import verify
GATE=CompositionGate(HERE,'expression_booleans','07c9d98fc8375b8f33a937d93f282ff8d0de3c6716f1047c3ec20bfc1cdbfccd',11)
if __name__=='__main__':verify(GATE)
