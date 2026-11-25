#!/usr/bin/env python3
"""Self-test for scripts/check_sanitization.py : the rules must be seen to bite.

Every value this test looks for is assembled at runtime from fragments. That is
deliberate and it is load-bearing: this file lives in the tree the gate scans,
so a literal token here would be a finding in the gate's own repository. Do not
"simplify" the joins into whole strings.

A rule nobody has watched fire is faith, not a gate.
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "scripts" / "check_sanitization.py"


def run_gate(target: Path, profile: str = "buntas"):
    proc = subprocess.run(
        [sys.executable, str(GATE), profile, str(target)],
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def fake(fragment_a, fragment_b, repeat=36):
    return fragment_a + fragment_b + "a" * repeat


class GateRulesBite(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gate-selftest-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def write(self, rel, text):
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_clean_tree_passes(self):
        self.write("README.md", "Nothing identifying here, just prose.\n")
        code, out = run_gate(self.tmp)
        self.assertEqual(code, 0, out)

    def test_credential_shape_in_source_trips(self):
        self.write("notes.md", "token: " + fake("gh", "p_") + "\n")
        code, out = run_gate(self.tmp)
        self.assertEqual(code, 1, out)
        self.assertIn("finding", out)

    def test_private_key_header_trips(self):
        self.write("deploy.md", "-" * 5 + "BEGIN RSA PRIVATE KEY" + "-" * 5 + "\n")
        code, out = run_gate(self.tmp)
        self.assertEqual(code, 1, out)

    def test_workflow_directory_is_scanned(self):
        # .github was the one directory the gate never read. This proves it is
        # read now, using a path shape rather than a real host.
        self.write(".github/workflows/ci.yml", "run: cd " + "/home/" + "someone/repo\n")
        code, out = run_gate(self.tmp)
        self.assertEqual(code, 1, out)

    def test_extensionless_text_is_scanned(self):
        # A packaged licence or a copyright file arrives with no suffix.
        self.write("usr/share/doc/pkg/copyright", "written by: Jane Q Public\n")
        code, out = run_gate(self.tmp)
        self.assertEqual(code, 1, out)

    def test_binary_extensionless_file_is_skipped(self):
        path = self.tmp / "blob"
        path.write_bytes(b"\x00\x01\x02\x03" * 64)
        code, out = run_gate(self.tmp)
        self.assertEqual(code, 0, out)

    def test_staged_content_is_scanned_even_when_disk_is_clean(self):
        repo = self.tmp
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        for key, value in (("user.email", "selftest@example.invalid"),
                           ("user.name", "selftest"),
                           ("commit.gpgsign", "false")):
            subprocess.run(["git", "-C", str(repo), "config", key, value], check=True)
        path = repo / "staged.md"
        path.write_text("token: " + fake("gh", "p_") + "\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "staged.md"], check=True)
        # now make the working tree innocent while the index still holds it
        path.write_text("clean prose now\n", encoding="utf-8")
        code, out = run_gate(repo)
        self.assertEqual(code, 1, out)
        self.assertIn("staged", out)


if __name__ == "__main__":
    unittest.main()
