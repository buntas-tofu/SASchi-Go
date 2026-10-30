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
- `examples/verify_trim_strip.py`  character TRIM/STRIP assignment and shortened
  concatenation values, with fixed argument-derived destination widths.
- `examples/verify_substr_compositions.py`  stored-value/fixed-source combinations
  and padding-insensitive checked SUBSTR CATX items, with local temporary refusals.
- `examples/verify_substr.py`  checked ASCII SUBSTR bounds and source-derived
  DATA-step destination widths; the raw extraction fixture above is unchanged.
- `examples/verify_bitwise.py`  unsigned32 BAND/BOR/BXOR/BNOT/BLSHIFT/BRSHIFT,
  with strict finite integral inputs and error-state refusal.
- `examples/verify_lag_execution.py`  bounded numeric direct-assignment LAG/DIF
  occurrence queues; selected IF/ELSE and counted DO scheduling, no stateless calls.
- `examples/verify_mod.py`  MOD, dividend-signed remainder for bounded exact
  binary64 integers; fractional, missing, and zero-divisor inputs require review.
- `examples/verify_calendar.py`  MDY/WEEKDAY for valid dates in1753..3999,
  with integral numeric arguments and explicit missing/error-state refusals.
- `examples/verify_int.py`  bounded INT truncation outside a conservative
  near-integer refusal band. Full SAS INT fuzz behavior is not claimed.
- `examples/verify_division.py`  operator division with bounded numeric
  operands and exact binary64 quotients; rounded/error-state cases refuse.
"""
from __future__ import annotations

from dataclasses import dataclass
from sas_semantics import sas_divide, sas_int, sas_multiply, sas_numeric_array_add, sas_numeric_array_value, sas_numeric_order
from sas_semantics import sas_trim, sas_strip
from .trim_strip import call_width as trim_width
import math
import re

from sas_semantics import (is_sas_missing, sas_charnum, sas_count, sas_input_yymmdd8,
                           sas_length, sas_lengthc, sas_lengthn, sas_max,
                           sas_min, sas_mod, sas_numeric_length, sas_put_date9, sas_putn, sas_round,
                           sas_sum, sas_reverse, sas_catx, _sas_concat_text,
                           sas_substr_checked, sas_substr_bound, _sas_substr_text,
                           SAS_BITWISE_ARITY, sas_bitwise, sas_bitwise_integer, sas_lag_numeric,
                           SAS_CALENDAR_ARITY, SAS_CALENDAR_MIN_DAY, SAS_CALENDAR_MAX_DAY,
                           SAS_CALENDAR_MIN_YEAR, SAS_CALENDAR_MAX_YEAR, sas_calendar, sas_calendar_integer)

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
GATE_LAG_EXECUTION = "examples/verify_lag_execution.py"
GATE_CALENDAR = "examples/verify_calendar.py"
GATE_INT = "examples/verify_int.py"
GATE_TRIM_STRIP = "examples/verify_trim_strip.py"
BINARY64_FUNCTIONS = frozenset(('constant', 'sin', 'cos', 'tan', 'arsin', 'arcos', 'atan'))
GATE_BINARY64 = "examples/verify_binary64.py"

LAG_FUNCTIONS = {family + suffix: (family, depth)
                 for family in ("lag", "dif")
                 for suffix, depth in [("", 1)] + [(str(n), n) for n in range(1, 101)]}

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
        FunctionSpec("trim", "character", GATE_TRIM_STRIP, 1, 1),
        FunctionSpec("strip", "character", GATE_TRIM_STRIP, 1, 1),
        FunctionSpec("catx", "character", GATE_CONCAT, 2, 33),
        FunctionSpec("count", "number", GATE_COUNT, 2, 3),
        FunctionSpec("mod", "number", GATE_MOD, 2, 2),
        FunctionSpec("int", "number", GATE_INT, 1, 1),
        *(FunctionSpec(name, "number", GATE_BINARY64, 1, 1) for name in sorted(BINARY64_FUNCTIONS)),
        *(FunctionSpec(name, "number", GATE_CALENDAR, arity, arity)
          for name, arity in SAS_CALENDAR_ARITY.items()),
        *(FunctionSpec(name, "number", GATE_BITWISE, arity, arity)
          for name, arity in SAS_BITWISE_ARITY.items()),
        FunctionSpec("sum", "number", GATE_MISSARITH, 1, -1),
        FunctionSpec("round", "number", GATE_ROUNDING, 2, 2),
        FunctionSpec("put", "character", GATE_NUMFMT, 2, 2, (1,)),
        FunctionSpec("input", "number", GATE_FUNCS, 1, 2, (1,)),
        *(FunctionSpec(name, "number", GATE_LAG_EXECUTION, 1, 1) for name in LAG_FUNCTIONS),
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
    if name in LAG_FUNCTIONS:
        raise ValueError("LAG/DIF requires a scoped DATA-step occurrence queue")
    if name in SAS_BITWISE_ARITY:
        return sas_bitwise(name, *values)
    if name == "reverse":
        return sas_reverse(values[0])
    if name in ('trim', 'strip'):
        if len(values) != 1:
            raise ValueError('TRIM/STRIP requires exactly one argument')
        return (sas_trim if name == 'trim' else sas_strip)(values[0])
    if name == "catx":
        return sas_catx(*values)
    if name == "count":
        return sas_count(*values)
    if name == "mod":
        return sas_mod(*values)
    if name == 'int':
        return sas_int(*values)
    if name in SAS_CALENDAR_ARITY:
        return sas_calendar(name, *values)
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
    if name in ('trim', 'strip'):
        return trim_width(expr, schema)
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
    """Read-only preorder nodes and source lines, without Python recursion."""
    pending, active = [(value, line, False)], set()
    while pending:
        node, source_line, closing = pending.pop()
        if closing:
            active.remove(id(node))
            continue
        if not isinstance(node, (dict, list, tuple)):
            continue
        if id(node) in active:
            raise ValueError('expression and plan trees cannot contain cycles')
        active.add(id(node))
        pending.append((node, source_line, True))
        if isinstance(node, dict):
            source_line = node.get('line', source_line)
            yield node, source_line
            children = list(node.values())
        else:
            children = node
        pending.extend((child, source_line, False) for child in reversed(children))


def validate_multiplication_profile(value):
    """Bound new multiplication trees before recursive descriptor walkers."""
    nodes = [node for node, _ in expression_nodes(value)]
    if not any(node.get('kind') == 'arithmetic' and node.get('op') == '*' for node in nodes):
        return
    if sum(node.get('kind') in ('arithmetic', 'call') for node in nodes) > 128:
        raise ValueError('numeric composition exceeds the128-node step policy')
    structures = [(value, 0)]
    while structures:
        node, structural_depth = structures.pop()
        if not isinstance(node, (dict, list, tuple)):
            continue
        if structural_depth > 256:
            raise ValueError('multiplication plan structure exceeds the bounded validation profile')
        children = node.values() if isinstance(node, dict) else node
        structures.extend((child, structural_depth + 1) for child in children)
    expression_kinds = {'number', 'missing', 'tagged_missing', 'character', 'variable',
                        'automatic', 'format', 'arithmetic', 'call', 'concat',
                        'array_get', 'array_sum', 'array_current'}
    pending = [(value, 0)]
    while pending:
        node, depth = pending.pop()
        if isinstance(node, dict):
            kind = node.get('kind')
            is_expression = isinstance(kind, str) and kind in expression_kinds
            if depth and not is_expression:
                raise ValueError('multiplication composition has an unsupported expression kind')
            depth = depth + 1 if is_expression else 0
            if depth > 32:
                raise ValueError('multiplication expressions exceed the32-level profile')
            if kind in ('number', 'missing', 'tagged_missing', 'character', 'variable', 'automatic'):
                if set(node) != {'kind', 'value'}:
                    raise ValueError('multiplication composition has a malformed scalar operand')
                if kind == 'number' and (type(node['value']) not in (int, float)
                        or type(node['value']) is float and not math.isfinite(node['value'])):
                    raise ValueError('multiplication numeric literals require finite numbers')
                if kind == 'missing' and node['value'] is not None:
                    raise ValueError('multiplication ordinary missing requires None')
                if kind == 'character' and not isinstance(node['value'], str):
                    raise ValueError('multiplication character literals require text')
                if kind == 'tagged_missing':
                    if not isinstance(node['value'], dict) or set(node['value']) != {'missing'}:
                        raise ValueError('multiplication scalar tagged missing requires a valid encoding')
                    sas_numeric_order(node['value'])
                if kind == 'variable' and (not isinstance(node['value'], str)
                        or not re.fullmatch(r'[a-z_][a-z0-9_]{0,31}', node['value'])):
                    raise ValueError('multiplication operands require normalized ordinary variable names')
                if kind == 'automatic' and (not isinstance(node['value'], str)
                        or node['value'] != '_n_' and not re.fullmatch(r'(?:first|last)\.[a-z_][a-z0-9_]{0,31}', node['value'])):
                    raise ValueError('multiplication automatic operands require a supported reference')
            if kind == 'format' and (set(node) != {'kind', 'name', 'w', 'd'}
                    or not isinstance(node['name'], str) or node['name'] not in FORMATS
                    or type(node['w']) is not int or type(node['d']) is not int
                    or node['w'] < 0 or node['d'] < 0):
                raise ValueError('multiplication composition requires supported format metadata')
            if kind == 'call':
                spec = FUNCTIONS.get(node.get('name')) if isinstance(node.get('name'), str) else None
                args = node.get('args')
                if (set(node) != {'kind', 'name', 'args'} or spec is None or not isinstance(args, list)
                        or any(not isinstance(arg, dict) for arg in args)
                        or len(args) < spec.min_args or spec.max_args >= 0 and len(args) > spec.max_args):
                    raise ValueError('multiplication composition requires supported call shapes and arity')
            if kind == 'arithmetic' and (set(node) != {'kind', 'op', 'left', 'right'}
                    or node.get('op') not in ('+', '-', '/', '*')
                    or not all(isinstance(node[side], dict) for side in ('left', 'right'))):
                raise ValueError('multiplication composition requires supported arithmetic shapes')
            if kind == 'arithmetic':
                children = [node['left'], node['right']]
            elif kind in ('call', 'concat'):
                children = [node.get('args')]
            elif kind == 'array_get':
                children = [node.get('index')]
            else:
                children = [] if is_expression else node.values()
            pending.extend((child, depth) for child in children)
        elif isinstance(node, (list, tuple)):
            pending.extend((child, depth) for child in node)


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
    if kind in ('number', 'missing', 'tagged_missing', 'automatic', 'array_get', 'array_sum', 'array_current'):
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


def validate_sum_expression(expr, schema):
    """The new sum/UNTIL slice admits numeric trees without coercion or tags."""
    from sas_semantics import sas_sum_statement
    if not isinstance(expr, dict):
        raise ValueError('sum/UNTIL requires a numeric expression')
    for node, _ in expression_nodes(expr):
        kind = node.get('kind')
        if not _numeric_expression(node, schema) or kind == 'tagged_missing':
            raise ValueError('sum/UNTIL requires ordinary numeric expressions')
        if kind in ('number', 'missing'):
            if kind == 'missing' and node.get('value') is not None:
                raise ValueError('sum/UNTIL ordinary missing requires None')
            sas_sum_statement(None, node.get('value'))
        if kind == 'arithmetic' and node.get('op') not in ('+', '-', '/', '*'):
            raise ValueError('sum/UNTIL supports gated arithmetic only')
        if kind == 'call':
            spec = FUNCTIONS[node['name']]
            args = node.get('args')
            if (not isinstance(args, list) or len(args) < spec.min_args
                    or spec.max_args >= 0 and len(args) > spec.max_args):
                raise ValueError('sum/UNTIL requires exact supported call arity')


def _constant_numeric(expr):
    """Literal-only numeric trees; dynamic references remain lazy."""
    kind = expr.get('kind')
    if kind in ('number', 'missing', 'tagged_missing'):
        return True, expr.get('value')
    if kind == 'arithmetic':
        a, left = _constant_numeric(expr['left'])
        b, right = _constant_numeric(expr['right'])
        if not (a and b): return False, None
        if expr['op'] == '/': return True, sas_divide(left, right)
        if expr['op'] == '*': return True, sas_multiply(left, right)
        if left is None or right is None: return True, None
        return True, left + right if expr['op'] == '+' else left - right
    if kind == 'call':
        values = [_constant_numeric(arg) for arg in expr['args']]
        if all(known for known, _ in values):
            return True, apply(expr['name'], [value for _, value in values])
    return False, None


def _constant_product(expr):
    """Literal product-profile trees, including bounded exact + and -."""
    kind = expr.get('kind')
    if kind in ('number', 'missing'):
        return True, sas_numeric_array_value(expr.get('value'))
    if kind == 'arithmetic':
        a, left = _constant_product(expr['left'])
        b, right = _constant_product(expr['right'])
        if not (a and b):
            return False, None
        if expr['op'] == '*':
            return True, sas_multiply(left, right)
        if expr['op'] == '/':
            return True, sas_divide(left, right)
        return True, sas_numeric_array_add(left, right, expr['op'] == '-')
    if kind == 'call':
        values = [_constant_product(arg) for arg in expr['args']]
        if all(known for known, _ in values):
            return True, sas_numeric_array_value(apply(expr['name'], [value for _, value in values]))
    return False, None


def validate_numeric_composition(value, schema):
    """Bounded arithmetic/INT descriptors and constants on empty/skipped paths."""
    for node, _ in expression_nodes(value):
        if node.get('kind') == 'arithmetic':
            if node.get('op') not in ('+', '-', '/', '*'):
                raise ValueError('unsupported arithmetic plan operator')
            if any(child.get('kind') == 'arithmetic' and child.get('op') == '*'
                   for child, _ in expression_nodes(node)):
                validate_sum_expression(node, schema)
                _constant_product(node)
            if node['op'] not in ('/', '*'): continue
            for side in ('left', 'right'):
                validate_sum_expression(node[side], schema)
                known, constant = _constant_numeric(node[side])
                if known:
                    from sas_semantics import sas_bounded_numeric
                    (sas_bounded_numeric if node['op'] == '/' else sas_numeric_array_value)(constant)
                    if node['op'] == '/' and side == 'right' and constant == 0:
                        raise ValueError('division by zero requires error-state review')
            _constant_numeric(node)
        elif node.get('kind') == 'call' and node.get('name') == 'int':
            args = node.get('args')
            if not isinstance(args, list) or len(args) != 1:
                raise ValueError('INT requires one numeric expression')
            validate_sum_expression(args[0], schema)
            known, constant = _constant_numeric(args[0])
            if known: sas_int(constant)


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



def validate_calendar_calls(value, schema):
    """Check descriptors and literal bounds even for skipped/empty execution."""
    for node, _ in expression_nodes(value):
        name = node.get('name')
        if node.get('kind') != 'call' or name not in SAS_CALENDAR_ARITY:
            continue
        args = node.get('args')
        if (not isinstance(args, list) or len(args) != SAS_CALENDAR_ARITY[name] or
                any(not isinstance(arg, dict) for arg in args)):
            raise ValueError('calendar requires exact expression argument count')
        bounds = ([(1, 12), (1, 31), (SAS_CALENDAR_MIN_YEAR, SAS_CALENDAR_MAX_YEAR)] if name == 'mdy'
                  else [(SAS_CALENDAR_MIN_DAY, SAS_CALENDAR_MAX_DAY)])
        for arg, (lower, upper) in zip(args, bounds):
            if not _numeric_expression(arg, schema):
                raise ValueError('calendar requires numeric expressions without implicit coercion')
            if arg.get('kind') in ('number', 'missing', 'tagged_missing'):
                sas_calendar_integer(arg.get('value'), lower, upper)
        if all(arg.get('kind') == 'number' for arg in args):
            sas_calendar(name, *(arg['value'] for arg in args))


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


LAG_RESERVED_NAMES = {'_n_', '_error_', '_all_', '_numeric_', '_character_',
                      '_infile_', '_file_', '_ods_', '_page_', '_blankpage_'}


def validate_lag_calls(value, schema=None, *, direct=False):
    """Local stateful context and descriptor checks, including skipped source."""
    for node, _ in expression_nodes(value):
        if node.get('kind') != 'call' or node.get('name') not in LAG_FUNCTIONS:
            continue
        if not direct or node is not value:
            raise ValueError('LAG/DIF is gated only as a direct numeric assignment RHS; temporary/predicate contexts require review')
        args = node.get('args')
        if not isinstance(args, list) or len(args) != 1 or not isinstance(args[0], dict):
            raise ValueError('LAG/DIF requires exactly one expression argument')
        arg = args[0]
        kind, item = arg.get('kind'), arg.get('value')
        if kind == 'number':
            if item is None:
                raise ValueError('LAG/DIF numeric literal requires a finite number')
            sas_lag_numeric(item)
        elif kind == 'missing':
            if item is not None:
                raise ValueError('LAG/DIF ordinary missing literal requires None')
        elif kind == 'automatic' and item == '_n_':
            continue
        elif kind == 'variable':
            if (not isinstance(item, str) or not re.fullmatch(r'[a-z_][a-z0-9_]{0,31}', item) or
                    item in LAG_RESERVED_NAMES):
                raise ValueError('LAG/DIF reserved automatic argument requires review; only _N_ is gated')
            if schema is not None:
                spec = schema.get(item, 'number')
                if (spec if isinstance(spec, str) else spec.get('type')) != 'number':
                    raise ValueError('LAG/DIF requires a numeric variable descriptor')
        else:
            raise ValueError('LAG/DIF argument requires a finite numeric/ordinary-missing literal, numeric variable or _N_; coercion and expressions require review')
