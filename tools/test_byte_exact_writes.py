#!/usr/bin/env python3
"""Guard: no text-mode write in the tree, because a byte-pinned receipt needs it.

Path.write_text and open(mode='w') translate "\\n" to "\\r\\n" on Windows. Any
code that writes a file and then hashes read_bytes() then describes a different
file from the one on disk, which is exactly what the fixture gates compare. The
rule is enforced here rather than trusted to review, because it is invisible on
Linux, where nothing translates and every test passes.

A new text-mode write is a defect even if today's tests are green on this host.
"""
import ast
import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
SCANNED = ("examples", "saschi", "tools")
SKIP_FILES = {"tools/test_byte_exact_writes.py"}


def python_files():
    for base in SCANNED:
        for path in sorted((REPO / base).rglob("*.py")):
            if path.relative_to(REPO).as_posix() not in SKIP_FILES:
                yield path


class ByteExactWrites(unittest.TestCase):
    def test_every_write_text_passes_newline(self):
        offenders = []
        for path in python_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "write_text":
                    if not any(k.arg == "newline" for k in node.keywords):
                        offenders.append(f"{path.relative_to(REPO)}:{node.lineno}")
        self.assertEqual(offenders, [], "text-mode write_text (add newline=''): " + ", ".join(offenders))

    def test_every_open_for_writing_passes_newline(self):
        offenders = []
        for path in python_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not (isinstance(func, ast.Attribute) and func.attr == "open"):
                    continue
                mode = None
                if node.args:
                    first = node.args[0]
                    if isinstance(first, ast.Constant):
                        mode = first.value
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        mode = kw.value.value
                if not isinstance(mode, str):
                    continue
                if any(flag in mode for flag in ("w", "a", "x")) and "b" not in mode:
                    if not any(k.arg == "newline" for k in node.keywords):
                        offenders.append(f"{path.relative_to(REPO)}:{node.lineno}")
        self.assertEqual(offenders, [], "text-mode open for writing (add newline=''): " + ", ".join(offenders))


if __name__ == "__main__":
    unittest.main()
