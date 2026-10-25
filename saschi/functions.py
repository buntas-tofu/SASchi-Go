"""Scalar SAS functions wired into the executable slice, one gate at a time.

Nothing is wired here that a fixture gate does not already prove. Every entry
names the gate file that pins its behavior, the parser refuses any function or
format token that is not in this registry, and a construct with no gate stays a
human-review ticket instead of becoming silently generated code.

Gate provenance, function by function:

- `examples/verify_funcs.py`  MAX, MIN (ignore missing), the LENGTH family
  (trailing blanks excluded, floored at 1), raw SUBSTR extraction, character to
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
- `examples/verify_substr_compositions.py`  stored-value/fixed-source combinations
  and padding-insensitive checked SUBSTR CATX items, with local temporary refusals.
- `examples/verify_substr.py`  checked ASCII SUBSTR bounds and source-derived
  DATA-step destination widths; the raw extraction fixture above is unchanged.
- `examples/verify_bitwise.py`  unsigned32 BAND/BOR/BXOR/BNOT/BLSHIFT/BRSHIFT,
  with strict finite integral inputs and error-state refusal.
- `examples/verify_mod.py`  MOD, dividend-signed remainder for bounded exact
  binary64 integers; fractional, missing, and zero-divisor inputs require review.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from sas_semantics import (is_sas_missing, sas_charnum, sas_count, sas_input_yymmdd8,
                           sas_length, sas_lengthc, sas_lengthn, sas_max,
                           sas_min, sas_mod, sas_numeric_length, sas_put_date9, sas_putn, sas_round,
                           sas_sum, sas_reverse, sas_catx, _sas_concat_text,
                           sas_substr_checked, sas_substr_bound, _sas_substr_text,
                           SAS_BITWISE_ARITY, sas_bitwise, sas_bitwise_integer)

GATE_FUNCS = "examples/verify_funcs.py"
GATE_MISSARITH = "examples/verify_missarith.py"
GATE_NUMFMT = "examples/verify_numfmt.py"
GATE_ROUNDING = "examples/verify_rounding.py"
GATE_COUNT = "examples/verify_count.py"
GATE_MOD = "examples/verify_mod.py"
GATE_LENGTH_REVERSE = "examples/verify_length_reverse.py"
GATE_CONCAT = "examples/verify_concat_catx.py"
GATE_SUBSTR = "examples/verify_substr.py"
GATE_BITWISE = "examples/verify_bitwise.py"

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
        FunctionSpec("substr", "character", GATE_SUBSTR, 3, 3),
        FunctionSpec("reverse", "character", GATE_LENGTH_REVERSE, 1, 1),
        FunctionSpec("catx", "character", GATE_CONCAT, 2, 33),
        FunctionSpec("count", "number", GATE_COUNT, 2, 3),
        FunctionSpec("mod", "number", GATE_MOD, 2, 2),
        *(FunctionSpec(name, "number", GATE_BITWISE, arity, arity)
          for name, arity in SAS_BITWISE_ARITY.items()),
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
    if name in SAS_BITWISE_ARITY:
        return sas_bitwise(name, *values)
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
        return sas_substr_checked(*values)
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


def catx_arguments_allowed(expr):
    """CATX trims SUBSTR item padding; delimiter padding remains significant."""
    args = expr.get('args')
    if not isinstance(args, list) or not 2 <= len(args) <= 33 or any(not isinstance(arg, dict) for arg in args):
        return False
    return (args[0].get('kind') in ('character', 'variable') and
            all(arg.get('kind') in ('character', 'variable') or
                arg.get('kind') == 'call' and arg.get('name') == 'substr' for arg in args[1:]))


def character_width(expr, schema=None) -> int | None:
    """Declared width of a character-returning call, or None when not derivable.

    Widths come from static descriptors rather than current row values. The
    SUBSTR branch derives new destination width from its first argument.
    SUBSTR temporary widths remain unclaimed; local consumer checks apply.
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
        if not catx_arguments_allowed(expr):
            raise ValueError('CATX requires literal/variable delimiter and literal/variable or checked SUBSTR items')
        if any(character_width(arg, schema) is None for arg in expr['args']):
            raise ValueError('CATX requires statically known character arguments')
        return 200
    if name == "substr":
        args = _substr_arguments(expr)
        source = args[0]
        if source['kind'] == 'character':
            return len(_sas_substr_text(source['value']))
        if source['kind'] == 'variable':
            spec = (schema or {}).get(source['value'])
            if isinstance(spec, dict) and spec.get('type') == 'character':
                return spec['length']
        if source.get('kind') == 'concat' or source.get('kind') == 'call' and source.get('name') == 'reverse':
            width = character_width(source, schema)
            if width is not None:
                return width
        raise ValueError('SUBSTR source requires a known fixed-width character literal, variable, REVERSE or concatenation expression')
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



def _substr_arguments(expr):
    args = expr.get('args')
    if not isinstance(args, list) or len(args) != 3 or any(not isinstance(arg, dict) for arg in args):
        raise ValueError('SUBSTR requires three expression arguments')
    return args


def _numeric_expression(expr, schema):
    kind = expr.get('kind')
    if kind in ('number', 'missing', 'tagged_missing', 'automatic'):
        return True
    if kind == 'variable':
        spec = schema.get(expr['value'], 'number')
        return (spec if isinstance(spec, str) else spec.get('type')) == 'number'
    if kind == 'call':
        spec = FUNCTIONS.get(expr.get('name'))
        return spec is not None and spec.returns == 'number'
    if kind == 'arithmetic':
        return _numeric_expression(expr['left'], schema) and _numeric_expression(expr['right'], schema)
    return False


def validate_substr_calls(value, schema):
    """Check descriptors/literal bounds even for empty or skipped DATA input."""
    for node, _ in expression_nodes(value):
        if node.get('kind') != 'call' or node.get('name') != 'substr':
            continue
        args = _substr_arguments(node)
        width = character_width(node, schema)
        literals = []
        for arg in args[1:]:
            if not _numeric_expression(arg, schema):
                raise ValueError('SUBSTR bounds require numeric expressions')
            if arg.get('kind') in ('number', 'missing', 'tagged_missing'):
                literals.append(sas_substr_bound(arg.get('value')))
            else:
                literals.append(None)
        position, length = literals
        if (position is not None and position > width or length is not None and length > width or
                position is not None and length is not None and position + length - 1 > width):
            raise ValueError('SUBSTR literal bounds exceed the source width; error-flag review required')


def substr_context_errors(value, context='other'):
    """Admit only consumers proven insensitive to an unclaimed temporary width."""
    if isinstance(value, dict):
        if value.get('kind') == 'call':
            name, args = value.get('name'), value.get('args', [])
            if not isinstance(args, list):
                if name == 'substr':
                    yield 'SUBSTR requires three expression arguments'
                return
            if name == 'substr' and context not in ('assignment', 'padding-insensitive'):
                yield 'SUBSTR temporary consumer requires width review; store the result in a variable first'
            for index, arg in enumerate(args):
                safe = name in ('length', 'lengthn') or name == 'catx' and index > 0
                if name == 'count' and index == 0 and len(args) >= 2:
                    needle = args[1]
                    safe = (needle.get('kind') == 'character' and bool(needle.get('value')) and
                            ' ' not in needle['value'])
                yield from substr_context_errors(arg, 'padding-insensitive' if safe else 'other')
        elif 'op' in value and 'left' in value:
            comparisons = ('=', 'eq', '^=', '~=', '<>', 'ne', '<', 'lt', '>', 'gt', '<=', 'le', '>=', 'ge')
            child_context = 'padding-insensitive' if value['op'] in comparisons else 'other'
            for key in ('left', 'right'):
                if key in value:
                    yield from substr_context_errors(value[key], child_context)
        else:
            for child in value.values():
                yield from substr_context_errors(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from substr_context_errors(child, context)



def validate_bitwise_calls(value, schema):
    """Check numeric descriptors and literal limits even if no row executes."""
    for node, _ in expression_nodes(value):
        name = node.get('name')
        if node.get('kind') != 'call' or name not in SAS_BITWISE_ARITY:
            continue
        args = node.get('args')
        if (not isinstance(args, list) or len(args) != SAS_BITWISE_ARITY[name] or
                any(not isinstance(arg, dict) for arg in args)):
            raise ValueError('bitwise requires exact expression argument count')
        for index, arg in enumerate(args):
            if not _numeric_expression(arg, schema):
                raise ValueError('bitwise requires numeric expressions without implicit coercion')
            if arg.get('kind') in ('number', 'missing', 'tagged_missing'):
                sas_bitwise_integer(arg.get('value'), shift=index == 1 and name in ('blshift', 'brshift'))
