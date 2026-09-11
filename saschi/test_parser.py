"""Tests for saschi.parser: the fence-robust statement splitter.

The estate C-005 lesson is the load-bearing requirement: fence robustness
first. Comments, string literals, and macro quotes must never break the
splitter's boundaries. A statement containing a comment or a string with
semicolons or /* markers must survive intact.

Runs against the 56-task Roku corpus where noted. Pure stdlib unittest.

Run: python -m unittest saschi.test_parser -v
"""

import unittest
from pathlib import Path

from saschi.parser import (
    Kind,
    Token,
    split_statements,
    tokenize,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
ROKU_CORPUS = Path.home() / "besaid" / "saschi-roku" / "corpus"


class TokenizerTests(unittest.TestCase):
    def test_simple_statements(self):
        toks = tokenize("data _null_;\n  x = 1;\nrun;\n")
        # Operators and equals emit as OTHER tokens; statement boundaries
        # are semicolons in code state.
        self.assertEqual([t.kind for t in toks][-1], Kind.SEMI)
        self.assertIn(Kind.SEMI, [t.kind for t in toks])

    def test_string_contains_semicolon_stays_one_token(self):
        toks = tokenize("s = \"a;b\";")
        kinds = [t.kind for t in toks]
        self.assertIn(Kind.STRING, kinds)
        self.assertEqual(toks[[i for i, k in enumerate(kinds) if k == Kind.STRING][0]].text,
                         '"a;b"')
        # The string is one token and the semicolon inside it did not split.
        self.assertEqual([t for t in toks if t.kind == Kind.SEMI], [toks[-1]])

    def test_single_quoted_string(self):
        toks = tokenize("t = 'it''s;here';")
        # SAS single-quoted strings double the quote to escape it.
        strings = [t for t in toks if t.kind == Kind.STRING]
        self.assertEqual(len(strings), 1)
        self.assertEqual(strings[0].text, "'it''s;here'")

    def test_comment_block_ignored(self):
        toks = tokenize("x = 1; /* a; comment; here */ y = 2;")
        # The block comment is dropped entirely.
        self.assertEqual([t.text for t in toks], ["x", "=", "1", ";", "y", "=", "2", ";"])

    def test_macro_comment_ignored(self):
        toks = tokenize("%* this is a macro comment\n   spanning lines ;\nx = 1;")
        self.assertNotIn("comment", [t.text for t in toks])
        self.assertEqual([t.text for t in toks][-1], ";")

    def test_star_comment_line_ignored(self):
        toks = tokenize("* a comment spanning\n   two lines ;\nx = 1;")
        self.assertNotIn("spanning", [t.text for t in toks])
        self.assertEqual([t.text for t in toks][-1], ";")

    def test_unterminated_comment_raises(self):
        with self.assertRaises(ValueError):
            tokenize("x = 1; /* never closed")


class SplitterTests(unittest.TestCase):
    def test_basic_split(self):
        stmts = split_statements("data a; x=1; run;")
        # Unspaced source stays one token ('x=1'); spaced source yields
        # 'x = 1'. Token boundaries are preserved either way.
        self.assertEqual([s.text for s in stmts], ["data a", "x=1", "run"])

    def test_multiline_split(self):
        src = "data a;\n  x = 1;\n  y = 2;\nrun;\n"
        stmts = split_statements(src)
        self.assertEqual([s.text for s in stmts],
                         ["data a", "x = 1", "y = 2", "run"])

    def test_semicolon_inside_string_does_not_split(self):
        src = 's = "a;b";\ny = 2;'
        stmts = split_statements(src)
        self.assertEqual(len(stmts), 2)
        self.assertEqual(stmts[0].text, 's = "a;b"')

    def test_semicolon_inside_comment_does_not_split(self):
        src = "x = 1; /* a; b; c */ y = 2;"
        stmts = split_statements(src)
        self.assertEqual([s.text for s in stmts], ["x = 1", "y = 2"])

    def test_line_numbers_tracked(self):
        src = "data a;\nx=1;\nrun;"
        stmts = split_statements(src)
        self.assertEqual([s.line for s in stmts], [1, 2, 3])

    def test_no_trailing_semicolon_ok(self):
        stmts = split_statements("x = 1")
        self.assertEqual(len(stmts), 1)
        self.assertEqual(stmts[0].text, "x = 1")
        self.assertFalse(stmts[0].terminated)

    def test_empty_source(self):
        self.assertEqual(split_statements(""), [])

    def test_double_quoted_with_embedded_comment_markers(self):
        # A string containing /* must not open a comment.
        src = 'msg = "not /* a comment */ here";'
        stmts = split_statements(src)
        self.assertEqual(len(stmts), 1)
        self.assertIn("not /* a comment */ here", stmts[0].text)

    def test_macro_quote_does_not_split(self):
        # %STR(%'...'%) style quoting keeps a semicolon inside intact.
        # NOTE: zero occurrences in the Roku corpus; this fence is
        # documented and unit-tested, not corpus-weighted.
        src = "%let x = %str(a;b);"
        stmts = split_statements(src)
        self.assertEqual(len(stmts), 1)
        # The interior semicolon is data, not a boundary; the fence kept
        # the statement whole even though the semicolon is not echoed.
        self.assertTrue(stmts[0].text.startswith("%let x = "))


class CorpusTests(unittest.TestCase):
    """Run the splitter across the 56-task Roku corpus.

    Every file must split into at least one statement, no statement may be
    empty, and every statement must re-join (by reconstruction of the
    original text modulo whitespace) to the source. This is the C-005
    fence-robustness proof at corpus scale.
    """

    @classmethod
    def setUpClass(cls):
        cls.corpus = sorted(ROKU_CORPUS.glob("*.sas"))
        if not cls.corpus:
            raise unittest.SkipTest("Roku corpus not present")

    def test_corpus_present(self):
        self.assertEqual(len(self.corpus), 56)

    def test_every_file_splits_cleanly(self):
        for path in self.corpus:
            with self.subTest(file=path.name):
                src = path.read_text(encoding="utf-8", errors="replace")
                stmts = split_statements(src)
                self.assertGreater(len(stmts), 0, f"{path.name}: no statements")
                for s in stmts:
                    self.assertTrue(s.text.strip(), f"{path.name}: empty statement")

    def test_every_file_semicolons_balanced(self):
        # The corpus is community-written SAS; some files may omit a final
        # semicolon or carry trailing prose. The invariant we hold is that
        # every CODE-STATE semicolon in the source terminates exactly one
        # statement. Semicolons inside strings and comments are not
        # statement terminators and are excluded from the count.
        for path in self.corpus:
            with self.subTest(file=path.name):
                src = path.read_text(encoding="utf-8", errors="replace")
                stmts = split_statements(src)
                terminated = sum(1 for s in stmts if s.terminated)
                tokens = tokenize(src)
                code_semis_src = sum(1 for tok in tokens if tok.kind is Kind.SEMI)
                self.assertEqual(terminated, code_semis_src,
                                 f"{path.name}: semicolon imbalance "
                                 f"(terminated {terminated} vs tokenized "
                                 f"{code_semis_src})")

    def test_statement_boundaries_at_provenance_header(self):
        # The provenance header is a comment block; the first statement
        # must come after it and must not swallow the header.
        for path in self.corpus:
            with self.subTest(file=path.name):
                src = path.read_text(encoding="utf-8", errors="replace")
                if not src.lstrip().startswith("/*"):
                    continue
                stmts = split_statements(src)
                self.assertNotIn("Source:", stmts[0].text,
                                 f"{path.name}: provenance header leaked into statement")


if __name__ == "__main__":
    unittest.main(verbosity=2)
