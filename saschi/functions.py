"""Scalar SAS functions wired into the executable slice, one gate at a time.

Nothing is wired here that a fixture gate does not already prove. Every entry
names the gate file that pins its behavior, the parser refuses any function or
format token that is not in this registry, and a construct with no gate stays a
human-review ticket instead of becoming silently generated code.

Gate provenance, function by function:

- `examples/verify_funcs.py`  MAX, MIN (ignore missing), the LENGTH family
  (trailing blanks excluded, floored at 1), SUBSTR (1-based), character to
  numeric coercion (blank or invalid reads as missing). Typed numeric LENGTH
  arguments use the documented right-justified BEST12 conversion and return 12.
- `examples/verify_missarith.py`  SUM (ignores missing, where the `+` operator
  propagates it).
- `examples/verify_numfmt.py`  PUT with a numeric w.d format, PUT DATE9, and the
  YYMMDD8 informat read by INPUT.
- `examples/verify_rounding.py`  ROUND, ties away from zero.
- `examples/verify_count.py`  COUNT, bounded ASCII substring matching with I/T
  modifiers, preserved blanks, and refusal of undefined overlapping matches.
- `examples/verify_length_reverse.py`  REVERSE, fixed-width printable ASCII
  character reversal with descriptor-derived return length.
- `examples/verify_concat_catx.py`  bounded character CATX and operator concatenation.
- `examples/verify_mod.py`  MOD, dividend-signed remainder for bounded exact
  binary64 integers; fractional, missing, and zero-divisor inputs require review.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from sas_semantics import (is_sas_missing, sas_charnum, sas_count, sas_input_yymmdd8,
                           sas_length, sas_lengthc, sas_lengthn, sas_max,
                           sas_min, sas_mod, sas_numeric_length, sas_put_date9, sas_putn, sas_round,
                           sas_substr, sas_sum, sas_reverse, sas_catx, _sas_concat_text)

GATE_FUNCS = "examples/verify_funcs.py"
GATE_MISSARITH = "examples/verify_missarith.py"
GATE_NUMFMT = "examples/verify_numfmt.py"
GATE_ROUNDING = "examples/verify_rounding.py"
GATE_COUNT = "examples/verify_count.py"
GATE_MOD = "examples/verify_mod.py"
GATE_LENGTH_REVERSE = "examples/verify_length_reverse.py"
GATE_CONCAT = "examples/verify_concat_catx.py"

DATE9_WIDTH = 9


@dataclass(frozen=True)
class FunctionSpec:
    """One wired function: its return type and the gate that proves it.

    `format_args` names the argument positions that accept a format token
    (`PUT(value, 8.2)`, `INPUT(value, yymmdd8.)`). Everywhere else a dotted token
    is a number, not a format.
    """

    name: str
    returns: str
    gate: str
    min_args: int
    max_args: int  # -1 means variadic
    format_args: tuple = ()


FUNCTIONS: dict[str, FunctionSpec] = {
    spec.name: spec for spec in (
        FunctionSpec("max", "number", GATE_FUNCS, 1, -1),
        FunctionSpec("min", "number", GATE_FUNCS, 1, -1),
        FunctionSpec("length", "number", GATE_FUNCS, 1, 1),
        FunctionSpec("lengthn", "number", GATE_FUNCS, 1, 1),
        FunctionSpec("lengthc", "number", GATE_FUNCS, 1, 1),
        FunctionSpec("substr", "character", GATE_FUNCS, 3, 3),
        FunctionSpec("reverse", "character", GATE_LENGTH_REVERSE, 1, 1),
        FunctionSpec("catx", "character", GATE_CONCAT, 2, 33),
        FunctionSpec("count", "number", GATE_COUNT, 2, 3),
        FunctionSpec("mod", "number", GATE_MOD, 2, 2),
        FunctionSpec("sum", "number", GATE_MISSARITH, 1, -1),
        FunctionSpec("round", "number", GATE_ROUNDING, 2, 2),
        FunctionSpec("put", "character", GATE_NUMFMT, 2, 2, (1,)),
        FunctionSpec("input", "number", GATE_FUNCS, 1, 2, (1,)),
    )
}

FORMATS: dict[str, str] = {"": "numeric w.d", "date": "DATE9", "yymmdd": "YYMMDD8"}


def format_token(name: str, width: int, decimals: int) -> dict:
    """A format argument as the plan carries it: name, width, decimals."""
    return {"kind": "format", "name": name, "w": width, "d": decimals}


def _reject(name: str, message: str):
    raise ValueError(f"{name}: {message}")


def _numeric(name: str, values):
    for value in values:
        if isinstance(value, str):
            _reject(name, "a character argument is outside this slice")
        if isinstance(value, dict):
            _reject(name, "tagged missing is outside this slice")
    return values


def _text(name: str, value):
    if isinstance(value, dict):
        _reject(name, "tagged missing is outside this slice")
    if value is None or isinstance(value, str):
        return value
    _reject(name, "a numeric argument is outside this slice")


def _width_decimals(fmt) -> tuple[int, int]:
    if isinstance(fmt, dict) and fmt.get("kind") == "format":
        if fmt["name"] == "":
            return int(fmt["w"]), int(fmt["d"])
        if fmt["name"] == "date":
            return DATE9_WIDTH, 0
    _reject("PUT", "format has no gate in this slice")


def apply(name: str, values: list):
    """Evaluate one wired function over already-evaluated argument values."""
    if name == "reverse":
        return sas_reverse(values[0])
    if name == "catx":
        return sas_catx(*values)
    if name == "count":
        return sas_count(*values)
    if name == "mod":
        return sas_mod(*values)
    if name in ("max", "min"):
        return (sas_max if name == "max" else sas_min)(*_numeric(name, values))
    if name in ("length", "lengthn", "lengthc"):
        function = {"length": sas_length, "lengthn": sas_lengthn, "lengthc": sas_lengthc}[name]
        return function(values[0]) if isinstance(values[0], str) else sas_numeric_length(values[0])
    if name == "substr":
        text, position, length = _text(name, values[0]), values[1], values[2]
        if is_sas_missing(position) or is_sas_missing(length):
            return ""
        return sas_substr(text, int(position), int(length))
    if name == "sum":
        return sas_sum(*_numeric(name, values))
    if name == "round":
        value, unit = values
        if any(isinstance(v, dict) or is_sas_missing(v) for v in values):
            return None
        _numeric(name, values)
        if unit <= 0:
            return None
        try:
            result = sas_round(value, unit)
        except (OverflowError, ValueError):
            return None
        return result if math.isfinite(result) else None
    if name == "put":
        value, fmt = values
        if isinstance(fmt, dict) and fmt.get("kind") == "format" and fmt["name"] == "date":
            if is_sas_missing(value):
                return ".".rjust(DATE9_WIDTH)
            if isinstance(value, str):
                _reject(name, "DATE9 requires a numeric SAS day number")
            return sas_put_date9(value)
        width, decimals = _width_decimals(fmt)
        if isinstance(value, str):
            _reject(name, "a character value is outside this slice")
        return sas_putn(value, width, decimals)
    if name == "input":
        text = _text(name, values[0])
        if len(values) == 1:
            return sas_charnum(text)
        fmt = values[1]
        if isinstance(fmt, dict) and fmt.get("kind") == "format" and fmt["name"] == "yymmdd":
            return None if text is None else sas_input_yymmdd8(text)
        _reject(name, "informat has no gate in this slice")
    raise ValueError(f"unwired function: {name}")


def character_width(expr, schema=None) -> int | None:
    """Declared width of a character-returning call, or None when not derivable.

    Widths come from static descriptors rather than current row values. The
    legacy SUBSTR branch retains its extraction-length rule pending separate
    repair; new string-feature programs containing SUBSTR are quarantined.
    """
    kind = expr.get('kind')
    if kind == 'character':
        value = expr['value']
        _sas_concat_text(value)
        return len(value)
    if kind == 'variable':
        spec = (schema or {}).get(expr['value'])
        return spec['length'] if isinstance(spec, dict) and spec.get('type') == 'character' else None
    if kind == 'concat':
        parts = expr.get('args')
        if not isinstance(parts, list) or not 2 <= len(parts) <= 32:
            raise ValueError('character concatenation requires 2..32 operands')
        widths = [character_width(part, schema) for part in parts]
        if any(width is None for width in widths):
            raise ValueError('character concatenation requires statically known character operands')
        width = sum(widths)
        if width > 32767:
            raise ValueError('character concatenation exceeds 32767 bytes')
        return width
    name = expr.get("name")
    if name == 'reverse':
        argument = expr['args'][0]
        if argument.get('kind') == 'character':
            sas_reverse(argument['value'])
        width = character_width(argument, schema)
        if width is None or not 1 <= width <= 32767:
            raise ValueError('REVERSE requires a known character argument width, 1..32767')
        return width
    if name == 'catx':
        if not 2 <= len(expr['args']) <= 33 or any(arg['kind'] not in ('character', 'variable') for arg in expr['args']):
            raise ValueError('CATX direct assignment requires literal or variable character arguments')
        if any(character_width(arg, schema) is None for arg in expr['args']):
            raise ValueError('CATX requires statically known character arguments')
        return 200
    if name == "substr":
        length = expr["args"][2]
        return int(length["value"]) if length.get("kind") == "number" else None
    if name == "put":
        fmt = expr["args"][1]
        if not isinstance(fmt, dict) or fmt.get("kind") != "format":
            return None
        return DATE9_WIDTH if fmt["name"] == "date" else int(fmt["w"])
    return None


def assign_spec(expr, schema=None):
    """Column descriptor for an assignment target, or None for plain numeric."""
    if expr.get('kind') == 'concat':
        return {'type': 'character', 'length': character_width(expr, schema)}
    if expr.get("kind") == "call":
        spec = FUNCTIONS[expr["name"]]
        if spec.returns == "character":
            width = character_width(expr, schema)
            if width is None:
                raise ValueError(f"{spec.name}: character width is not derivable")
            return {"type": "character", "length": width}
    return None


def validate_reverse_calls(value, schema):
    """Validate REVERSE descriptors even when no DATA row executes a call."""
    if isinstance(value, dict):
        if value.get('kind') == 'call' and value.get('name') == 'reverse':
            character_width(value, schema)
        for child in value.values():
            validate_reverse_calls(child, schema)
    elif isinstance(value, list):
        for child in value:
            validate_reverse_calls(child, schema)


def validate_string_expressions(value, schema, *, direct_catx=False):
    """Check new character operand descriptors even when no row executes."""
    if isinstance(value, dict):
        if value.get('kind') == 'call' and value.get('name') == 'catx' and not direct_catx:
            raise ValueError('CATX temporary contexts require review; direct assignment RHS only')
        if value.get('kind') == 'concat' or (value.get('kind') == 'call' and value.get('name') == 'catx'):
            character_width(value, schema)
        for child in value.values():
            validate_string_expressions(child, schema)
    elif isinstance(value, list):
        for child in value:
            validate_string_expressions(child, schema)


def expression_nodes(value, line=None):
    """Read-only expression dictionaries with their enclosing source line."""
    if isinstance(value, dict):
        line = value.get('line', line)
        yield value, line
        for child in value.values():
            yield from expression_nodes(child, line)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from expression_nodes(child, line)


def function_call_lines(value, name, line=None):
    """Find actual calls in AST dictionaries, ignoring function-shaped text."""
    return [source_line for node, source_line in expression_nodes(value, line)
            if node.get('kind') == 'call' and node.get('name') == name]
