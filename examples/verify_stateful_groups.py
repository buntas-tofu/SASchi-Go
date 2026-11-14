from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent))
from stateful_gate_common import StatefulGate,verify
GATE=StatefulGate(HERE,'stateful_groups','0ed9e2e72b5eeb420b3c89942bd544ac18be83abcb2a42da1edb44bac304892d',24)
if __name__=='__main__':verify(GATE)
