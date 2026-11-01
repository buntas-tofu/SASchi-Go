#!/usr/bin/env python3
"""Prepare exact licensed source fixtures outside Go before offline verification."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.vendor_sources import cache_root, prepare_sources, verify_sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', help='External cache directory; default is SASCHI_VENDOR_CACHE or a temporary cache')
    parser.add_argument('--check', action='store_true', help='Verify local pins without network access')
    args = parser.parse_args()
    try:
        sources = (verify_sources if args.check else prepare_sources)(cache=args.cache)
    except (ValueError, OSError) as error:
        print('Vendor fixture preparation failed: ' + str(error), file=sys.stderr)
        return 1
    print(json.dumps({'status': 'Pinned external fixture cache verified; not an execution proof.',
                      'cache': str(cache_root(args.cache)), 'offline': args.check,
                      'programs': {name: {'source': str(item['source']), 'license': str(item['license'])}
                                   for name, item in sources.items()}}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
