"""Conservative SAS statement scanner with opaque strings and macro quotes.

Macro text and inline data remain intact for diagnostics. The scanner does not
expand macros or interpret inline records. Unsupported syntax stays visible to
consumers, and an unclosed lexical fence raises ParseError with its start line.
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
    DATA = "inline-data"


@dataclass(frozen=True)
class Token:
    kind: Kind
    text: str
    line: int


@dataclass(frozen=True)
class Statement:
    text: str
    line: int
    terminated: bool = True


class ParseError(ValueError):
    def __init__(self, message: str, line: int):
        self.line = line
        super().__init__(f"line {line}: {message}")


MACRO_QUOTE = re.compile(r"%(?:NRSTR|STR|QUOTE|NRQUOTE|BQUOTE|NRBQUOTE|SUPERQ)\s*\(", re.I)
INLINE = re.compile(r"^(?:DATALINES|CARDS|LINES)(4)?$", re.I)


def tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    i, line, statement_start = 0, 1, 0
    n = len(source)
    while i < n:
        ch = source[i]
        if ch.isspace():
            line += ch == "\n"
            i += 1
            continue
        start, start_line = i, line
        if source.startswith("/*", i):
            depth, i = 1, i + 2
            while i < n and depth:
                if source.startswith("/*", i):
                    depth, i = depth + 1, i + 2
                elif source.startswith("*/", i):
                    depth, i = depth - 1, i + 2
                else:
                    line += source[i] == "\n"
                    i += 1
            if depth:
                raise ParseError("unterminated block comment", start_line)
            continue
        if source.startswith("%*", i) or (ch == "*" and len(tokens) == statement_start):
            end = source.find(";", i)
            if end < 0:
                raise ParseError("unterminated statement comment", start_line)
            line += source[i:end + 1].count("\n")
            i = end + 1
            continue
        match = MACRO_QUOTE.match(source, i)
        if match:
            depth, i = 1, match.end()
            while i < n and depth:
                # Percent marks quoted unmatched parentheses/quotes in %STR.
                if source[i] == "%" and i + 1 < n and source[i + 1] in "()'\"":
                    i += 2
                    continue
                depth += (source[i] == "(") - (source[i] == ")")
                line += source[i] == "\n"
                i += 1
            if depth:
                raise ParseError("unterminated macro quote", start_line)
            tokens.append(Token(Kind.OTHER, source[start:i], start_line))
            continue
        if ch in "\"'":
            quote, i = ch, i + 1
            while i < n:
                if source[i] == quote:
                    if i + 1 < n and source[i + 1] == quote:
                        i += 2
                        continue
                    i += 1
                    break
                line += source[i] == "\n"
                i += 1
            else:
                raise ParseError("unterminated string", start_line)
            tokens.append(Token(Kind.STRING, source[start:i], start_line))
            continue
        if ch == ";":
            text = " ".join(t.text for t in tokens[statement_start:]).strip()
            tokens.append(Token(Kind.SEMI, ";", line))
            statement_start = len(tokens)
            i += 1
            inline = INLINE.fullmatch(text)
            if inline:
                terminator = ";;;;" if inline.group(1) else ";"
                end = re.search(r"(?m)^[ \t]*" + terminator + r"[ \t]*\r?$", source[i:])
                if not end:
                    raise ParseError("unterminated inline data", start_line)
                raw = source[i:i + end.start()]
                tokens.append(Token(Kind.DATA, raw, line))
                line += source[i:i + end.end()].count("\n")
                tokens.append(Token(Kind.SEMI, ";", line))
                i += end.end()
                statement_start = len(tokens)
            continue
        while i < n and not source[i].isspace() and source[i] not in ';"\'':
            if source.startswith("/*", i) or (i > start and MACRO_QUOTE.match(source, i)):
                break
            i += 1
        text = source[start:i]
        tokens.append(Token(Kind.WORD if text[0].isalpha() or text[0] == "_" else Kind.OTHER,
                            text, start_line))
    return tokens


def split_statements(source: str) -> list[Statement]:
    statements: list[Statement] = []
    buf: list[Token] = []
    for token in tokenize(source):
        if token.kind is Kind.SEMI:
            if buf:
                # Prefix inline records so a record resembling code cannot emit.
                text = ("<inline-data> " + buf[0].text if buf[0].kind is Kind.DATA else
                        " ".join(t.text for t in buf))
                statements.append(Statement(text, buf[0].line))
            buf = []
        else:
            buf.append(token)
    if buf:
        statements.append(Statement(" ".join(t.text for t in buf), buf[0].line, False))
    return statements
