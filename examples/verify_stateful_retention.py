from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent))
from stateful_gate_common import StatefulGate,verify
GATE=StatefulGate(HERE,'stateful_retention','723373b3fd174a8ed39d971d6e9e7c642caad274b727376a56f0f11e2db497be',22)
if __name__=='__main__':verify(GATE)
