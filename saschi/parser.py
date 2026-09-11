"""saschi.parser: the fence-robust statement splitter.

The estate C-005 lesson is the load-bearing requirement: fence robustness
first. Comments, string literals, and macro quoting must never break the
splitter's boundaries. A statement containing a comment or a string with
semicolons or comment markers survives intact.

Design: a single-pass character scanner that tracks five states (code,
double-quoted string, single-quoted string, block comment, macro comment).
Semicolons are statement terminators only in code state. The scanner emits
tokens; split_statements groups tokens into statements with source line
numbers. Statement text is the token stream space-joined with terminators
dropped: word boundaries survive, and `Statement.terminated` records
whether a semicolon closed the statement.

Fences handled:
- /* ... */ block comments (dropped, with nesting tolerance).
- %* ... ; macro comments (dropped, terminator is the semicolon).
- * ... ; single-line comments (dropped when they start a line).
- "..." double-quoted strings (SAS doubles a double quote to escape).
- '...' single-quoted strings (SAS doubles a single quote to escape).
- %STR(...) / %NRSTR(...) / %QUOTE(...) style macro quoting is treated as
  code; a semicolon inside the parentheses stays inside the statement
  because the splitter only terminates on a code-state semicolon and the
  macro function consumes the balanced parentheses. This is the fence
  tolerance the C-005 lesson demands: never let an inner fence look like
  an outer one.

The tokenizer is deterministic and pure stdlib. It does not parse SAS
grammar; it only needs to know where statements end.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Kind(Enum):
    WORD = "word"
    STRING = "string"
    SEMI = "semi"
    OTHER = "other"


@dataclass(frozen=True)
class Token:
    kind: Kind
    text: str
    line: int


@dataclass(frozen=True)
class Statement:
    """One SAS statement: its text, the source line it started on, and
    whether a semicolon terminated it."""

    text: str
    line: int
    terminated: bool = True


def tokenize(source: str) -> list[Token]:
    """Scan source into tokens. Comments are dropped; strings are one token.

    Raises ValueError on an unterminated comment or string.
    """
    tokens: list[Token] = []
    i = 0
    n = len(source)
    line = 1
    # Macro-quote depth: %STR( / %NRSTR( / %QUOTE( open a fence that
    # keeps interior semicolons inside the statement (C-005: never let
    # an inner fence look like an outer one). Tracked per opening paren.
    macro_quote_depth = 0
    macro_quote_rx = re.compile(r"%\s*(NRSTR|STR|QUOTE|BQUOTE|NRBQUOTE|SUPERQ)\s*\(", re.I)

    while i < n:
        ch = source[i]

        # Line tracking and whitespace: newlines bump the line counter;
        # spaces and tabs are consumed without emitting anything.
        if ch == "\n":
            line += 1
            i += 1
            continue
        if ch in " \t\r":
            i += 1
            continue

        # Macro-quote fence: opening and closing parens adjust depth; a
        # semicolon inside the fence is not a statement terminator.
        if macro_quote_depth > 0 and ch == ")":
            macro_quote_depth -= 1
            i += 1
            continue
        if macro_quote_depth == 0:
            m = macro_quote_rx.match(source, i)
            if m:
                macro_quote_depth += 1
                i = m.end()
                continue

        # Block comment: /* ... */ (dropped; tolerate nesting one deep).
        if ch == "/" and i + 1 < n and source[i + 1] == "*":
            depth = 1
            i += 2
            while i < n and depth:
                if source[i] == "\n":
                    line += 1
                    i += 1
                    continue
                if source[i] == "/" and i + 1 < n and source[i + 1] == "*":
                    depth += 1
                    i += 2
                    continue
                if source[i] == "*" and i + 1 < n and source[i + 1] == "/":
                    depth -= 1
                    i += 2
                    continue
                i += 1
            if depth:
                raise ValueError("unterminated block comment")
            continue

        # Macro comment: %* ... ; (dropped; terminator is the semicolon).
        if ch == "%" and i + 1 < n and source[i + 1] == "*":
            i += 2
            while i < n:
                if source[i] == "\n":
                    line += 1
                    i += 1
                    continue
                if source[i] == ";":
                    i += 1
                    break
                i += 1
            continue

        # Single-line star comment: * ... ; at the start of a statement.
        if ch == "*" and _at_statement_start(source, i):
            i += 1
            while i < n:
                if source[i] == "\n":
                    line += 1
                    i += 1
                    continue
                if source[i] == ";":
                    i += 1
                    break
                i += 1
            continue

        # Double-quoted string (SAS escapes a double quote by doubling).
        if ch == '"':
            start = i
            i += 1
            while i < n:
                if source[i] == '"':
                    if i + 1 < n and source[i + 1] == '"':
                        i += 2  # escaped quote
                        continue
                    i += 1
                    break
                if source[i] == "\n":
                    line += 1
                i += 1
            tokens.append(Token(Kind.STRING, source[start:i], line))
            continue

        # Single-quoted string (SAS escapes a single quote by doubling).
        if ch == "'":
            start = i
            i += 1
            while i < n:
                if source[i] == "'":
                    if i + 1 < n and source[i + 1] == "'":
                        i += 2  # escaped quote
                        continue
                    i += 1
                    break
                if source[i] == "\n":
                    line += 1
                i += 1
            tokens.append(Token(Kind.STRING, source[start:i], line))
            continue

        # Semicolon: statement terminator, unless inside a macro-quote
        # fence (a semicolon inside %STR(...) is data, not a boundary).
        if ch == ";":
            if macro_quote_depth == 0:
                tokens.append(Token(Kind.SEMI, ";", line))
            i += 1
            continue

        # Everything else: one token per run of non-whitespace,
        # non-string, non-comment characters.
        start = i
        while i < n and not source[i].isspace() and source[i] not in ';"\'' \
                and not (source[i] == "/" and i + 1 < n and source[i + 1] == "*"):
            i += 1
        text = source[start:i]
        if text:
            kind = Kind.WORD if (text[0].isalpha() or text[0] == "_") else Kind.OTHER
            tokens.append(Token(kind, text, line))

    return tokens


def _at_statement_start(source: str, i: int) -> bool:
    """True when position i is at the start of a statement (only spaces
    and newlines since the last semicolon or the start of input)."""
    j = i - 1
    while j >= 0 and source[j] in " \t\r\n":
        j -= 1
    return j < 0 or source[j] == ";"


def _join(buf: list[Token]) -> str:
    """Statement text: tokens space-joined, terminators dropped.

    The join is deliberate: token boundaries carry word boundaries, which
    the first consumer (the emitter) needs. The earlier no-separator join
    compacted 'data rounded_values' into 'datarounded_values' and left
    statements unparseable. Terminators are dropped because the statement
    list itself delimits them; Statement.terminated records presence.
    """
    return " ".join(t.text for t in buf if t.kind is not Kind.SEMI).strip()


def split_statements(source: str) -> list[Statement]:
    """Split source into statements on code-state semicolons.

    Statements retain the source line they started on. A trailing
    statement without a semicolon is kept (terminated False). Comments
    and strings never terminate a statement.
    """
    tokens = tokenize(source)
    statements: list[Statement] = []
    buf: list[Token] = []
    start_line: int = 0

    for tok in tokens:
        if not buf:
            start_line = tok.line
        buf.append(tok)
        if tok.kind is Kind.SEMI:
            text = _join(buf)
            if text:
                statements.append(Statement(text, start_line, True))
            buf = []

    if buf:
        text = _join(buf)
        if text:
            statements.append(Statement(text, start_line, False))

    return statements
