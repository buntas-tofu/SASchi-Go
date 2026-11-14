from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent))
from stateful_gate_common import StatefulGate,verify
GATE=StatefulGate(HERE,'batch_reconciliation','bb26733c768a7e11264b3f7126a8655a246a6649b500dfdb93ded9884edb257d',38)
if __name__=='__main__':verify(GATE)
