"""Scalar SAS functions wired into the executable slice, one gate at a time.

Nothing is wired here that a fixture gate does not already prove. Every entry
names the gate file that pins its behavior, the parser refuses any function or
format token that is not in this registry, and a construct with no gate stays a
human-review ticket instead of becoming silently generated code.

Gate provenance, function by function:

- `examples/verify_funcs.py`  MAX, MIN (ignore missing), the LENGTH family
  (trailing blanks excluded, floored at 1), SUBSTR (1-based), character to
  numeric coercion (blank or invalid reads as missing).
- `examples/verify_missarith.py`  SUM (ignores missing, where the `+` operator
  propagates it).
- `examples/verify_numfmt.py`  PUT with a numeric w.d format, PUT DATE9, and the
  YYMMDD8 informat read by INPUT.
- `examples/verify_rounding.py`  ROUND, ties away from zero.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from sas_semantics import (is_sas_missing, sas_charnum, sas_input_yymmdd8,
                           sas_length, sas_lengthc, sas_lengthn, sas_max,
                           sas_min, sas_put_date9, sas_putn, sas_round,
                           sas_substr, sas_sum)

GATE_FUNCS = "examples/verify_funcs.py"
GATE_MISSARITH = "examples/verify_missarith.py"
GATE_NUMFMT = "examples/verify_numfmt.py"
GATE_ROUNDING = "examples/verify_rounding.py"

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
    if name in ("max", "min"):
        return (sas_max if name == "max" else sas_min)(*_numeric(name, values))
    if name in ("length", "lengthn", "lengthc"):
        function = {"length": sas_length, "lengthn": sas_lengthn, "lengthc": sas_lengthc}[name]
        return function(_text(name, values[0]))
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


def character_width(expr) -> int | None:
    """Declared width of a character-returning call, or None when not derivable.

    SAS fixes the width of a character expression at compile time. SUBSTR takes
    its width from the length argument, so a non-literal length is refused by the
    parser rather than guessed here.
    """
    name = expr.get("name")
    if name == "substr":
        length = expr["args"][2]
        return int(length["value"]) if length.get("kind") == "number" else None
    if name == "put":
        fmt = expr["args"][1]
        if not isinstance(fmt, dict) or fmt.get("kind") != "format":
            return None
        return DATE9_WIDTH if fmt["name"] == "date" else int(fmt["w"])
    return None


def assign_spec(expr):
    """Column descriptor for an assignment target, or None for plain numeric."""
    if expr.get("kind") == "call":
        spec = FUNCTIONS[expr["name"]]
        if spec.returns == "character":
            width = character_width(expr)
            if width is None:
                raise ValueError(f"{spec.name}: character width is not derivable")
            return {"type": "character", "length": width}
    return None