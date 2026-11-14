from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent))
from stateful_gate_common import StatefulGate,verify
GATE=StatefulGate(HERE,'record_quality_audit','2d3676995bd427ad0b79a21de18aef7ea2b36575580d69c15d9402bcf12a4057',24)
if __name__=='__main__':verify(GATE)
