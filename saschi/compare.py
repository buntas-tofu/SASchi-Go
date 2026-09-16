"""Typed comparisons: numeric tolerance never crosses a type boundary."""
import math
from fractions import Fraction


def equal(actual, expected, *, atol=0.0, nan_is_null=False, ordered_maps=False):
    if atol < 0 or not math.isfinite(atol):
        raise ValueError('comparison tolerance must be finite and nonnegative')
    if nan_is_null:
        actual = None if isinstance(actual, float) and math.isnan(actual) else actual
        expected = None if isinstance(expected, float) and math.isnan(expected) else expected
    if actual is None or expected is None:
        return actual is expected
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        if any(isinstance(v, float) and not math.isfinite(v) for v in (actual, expected)):
            return False
        # Do not round an integer to binary64 while comparing it to a float.
        return abs(Fraction(actual) - Fraction(expected)) <= Fraction(atol)
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        if (list(actual) != list(expected) if ordered_maps else actual.keys() != expected.keys()):
            return False
        return all(equal(actual[k], expected[k], atol=atol, nan_is_null=nan_is_null,
                         ordered_maps=ordered_maps) for k in actual)
    if isinstance(actual, (list, tuple)):
        return len(actual) == len(expected) and all(
            equal(a, b, atol=atol, nan_is_null=nan_is_null, ordered_maps=ordered_maps)
            for a, b in zip(actual, expected))
    return actual == expected


def table_equal(actual, expected):
    """Exact typed values, row order, column order, and all metadata."""
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        return False
    if not isinstance(actual.get('schema'), dict) or not isinstance(expected.get('schema'), dict):
        return False
    return list(actual['schema']) == list(expected['schema']) and equal(actual, expected)
