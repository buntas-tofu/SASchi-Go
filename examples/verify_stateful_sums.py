from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent))
from stateful_gate_common import StatefulGate,verify
GATE=StatefulGate(HERE,'stateful_sums','204974af3aa16206267864659ca8608e968f628333614e81fafd7daaac971a22',17)
if __name__=='__main__':verify(GATE)
