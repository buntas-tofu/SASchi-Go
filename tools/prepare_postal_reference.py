#!/usr/bin/env python3
"""Explicitly prepare the bounded pinned external USPS reference before gates."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from saschi.postal_reference import prepare,load_reference,reference_path,metadata


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--cache');parser.add_argument('--check',action='store_true');args=parser.parse_args()
    try:
        if args.check:load_reference(args.cache);path=reference_path(args.cache)
        else:path=prepare(args.cache)
    except (ValueError,OSError) as error:print('Postal reference preparation failed: '+str(error),file=sys.stderr);return 1
    print(json.dumps({'status':'Pinned external reference prepared; not execution or native SAS evidence.','reference':str(path),'offline':args.check,**metadata()},indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
