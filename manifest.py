#!/usr/bin/env python3
"""manifest.py : pin a SAS corpus with content hashes and provenance.

Every corpus the campaign touches gets manifested before a line of it is
processed, so any downstream result is reproducible from a clean checkout and
no file can be swapped underneath a claim. Mirrors the project corpus-manifest
pattern (hash + provenance on every row).

Emits one row per .sas file: file, source_class, sha256, bytes, lines.

Usage:
  python manifest.py <dir-of-sas-files> [--out manifest.csv]
"""

import argparse
import csv
import hashlib
from collections import Counter
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus_dir", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="pin every .sas under the tree, labeled by relative path")
    args = ap.parse_args()

    paths = sorted(args.corpus_dir.rglob("*.sas") if args.recursive else args.corpus_dir.glob("*.sas"))
    rows = []
    skipped = []
    for p in paths:
        if not p.is_file():
            skipped.append(str(p))
            continue
        try:
            raw = p.read_bytes()
        except OSError as e:
            skipped.append(f"{p}: {e}")
            continue
        rel = p.relative_to(args.corpus_dir)
        if args.recursive:
            src = rel.parts[0] if len(rel.parts) > 1 else "root"
            fname = str(rel)
        else:
            fname = p.name
            src = fname.split("__", 1)[0] if "__" in fname else "unknown"
        rows.append({
            "file": fname,
            "source_class": src,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "lines": raw.count(b"\n") + 1,
        })
    if skipped:
        print(f"skipped {len(skipped)} unreadable (broken symlinks or read errors)")

    out = args.out or (args.corpus_dir.parent / "manifest.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "source_class", "sha256", "bytes", "lines"])
        w.writeheader()
        w.writerows(rows)

    by_src = Counter(r["source_class"] for r in rows)
    print(f"{len(rows)} files pinned | {sum(r['bytes'] for r in rows)} bytes | "
          f"{sum(r['lines'] for r in rows)} lines")
    print(f"by source: {dict(by_src)}")
    print(f"manifest -> {out}")


if __name__ == "__main__":
    main()
