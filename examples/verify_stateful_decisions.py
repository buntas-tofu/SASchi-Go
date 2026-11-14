from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent))
from stateful_gate_common import StatefulGate,verify
GATE=StatefulGate(HERE,'stateful_decisions','8274f31f7aa79d5e0beece12cd671f9902c01c5aa79118aaa50af88ee0370482',28)
if __name__=='__main__':verify(GATE)
