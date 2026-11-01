#!/usr/bin/env python3
"""DS-071 literal mapping/default-width and exact numeric fallback source gate."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.verify_formatted_input import run

if __name__ == '__main__':
    run('invalue')
