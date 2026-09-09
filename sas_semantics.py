"""sas_semantics.py : reference implementations of SAS quirks, the verifier's law.

Both translation targets (Python and R) and every fixture verifier import their
truth from here, never from the host language's defaults. First resident: ROUND.

SAS ROUND(x, unit) rounds half AWAY FROM ZERO, with documented fuzzing to absorb
floating-point representation error. Python round() and numpy.round round half
to even (banker's rounding). The two agree everywhere except exact half-unit
boundaries, which in disclosure rounding is precisely where the rule lives.
"""

import ast
import datetime
import decimal
import math
import re
import struct

FUZZ = 1e-9  # SAS documents fuzzing inside ROUND; this absorbs float error


def sas_round(x: float, unit: float = 1.0) -> float:
    if unit <= 0:
        raise ValueError("unit must be positive")
    q = abs(x) / unit
    r = math.floor(q + 0.5 + FUZZ)
    return math.copysign(r * unit, x)


def round_count(x: float) -> float:
    """The small-count rounding ladder used in disclosure control.

    Below 15 reports 10, which by the rule's own comment does not mean 10, it
    means 'fewer than 15'. Above one million, four significant digits.
    """
    if x < 15:
        return 10
    if x < 100:
        return sas_round(x, 10)
    if x < 1000:
        return sas_round(x, 50)
    if x < 10000:
        return sas_round(x, 100)
    if x < 100000:
        return sas_round(x, 500)
    if x < 1000000:
        return sas_round(x, 1000)
    return sas_round(x, 10 ** (math.floor(math.log10(x)) - 3))


# ---------------------------------------------------------------------------
# Dates. SAS stores a date as an integer count of days from 1960-01-01. INTCK
# counts interval BOUNDARIES crossed, not elapsed time. INTCK('YEAR', d1, d2)
# is year(d2) - year(d1): crossing one Jan-1 boundary counts as 1 even if one
# day elapsed. A translation that reaches for elapsed time (difftime,
# relativedelta) returns 0 and disagrees with SAS at exactly the boundary a
# fiscal-year or age rule turns on. WEEK and SEMIYEAR are deliberately not
# characterized yet (WEEK's Sunday alignment is its own landmine).
# ---------------------------------------------------------------------------

SAS_EPOCH = datetime.date(1960, 1, 1)


def sas_date(n: int) -> datetime.date:
    """A SAS date integer (days since 1960-01-01) as a calendar date."""
    return SAS_EPOCH + datetime.timedelta(days=int(n))


def date_to_sas(d: datetime.date) -> int:
    return (d - SAS_EPOCH).days


def sas_intck(interval: str, start: datetime.date, end: datetime.date) -> int:
    """SAS INTCK, discrete method: interval boundaries crossed from start to end.

    Boundaries, not elapsed intervals. Negative when end precedes start, as SAS.
    Supports DAY, MONTH, QTR, YEAR. Others raise until characterized.
    """
    iv = interval.strip().upper()
    if iv == "DAY":
        return (end - start).days
    if iv == "MONTH":
        return (end.year - start.year) * 12 + (end.month - start.month)
    if iv == "QTR":
        return (end.year * 4 + (end.month - 1) // 3) - (start.year * 4 + (start.month - 1) // 3)
    if iv == "YEAR":
        return end.year - start.year
    raise ValueError(f"sas_intck: interval {interval!r} not yet characterized")


# ---------------------------------------------------------------------------
# Missing values. SAS orders missing as SMALLER than any number: missing sorts
# first ascending and is the smallest in comparisons. A translation that maps
# missing to NaN gets non-comparable ordering (NaN sorts last or is dropped),
# silently reordering BY-group output and mis-ranking the smallest real value.
# ---------------------------------------------------------------------------


def is_sas_missing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


# ---------------------------------------------------------------------------
# Aggregate functions ignore missing. SAS MAX()/MIN() (and SUM/MEAN) drop the
# missing arguments and aggregate what remains; if ALL are missing the result
# is missing. numpy max/min propagate NaN and Python's built-in max is
# unreliable with NaN, so a naive translation silently returns NaN where SAS
# returns a real value.
# ---------------------------------------------------------------------------


def sas_max(*vals):
    nums = [v for v in vals if not is_sas_missing(v)]
    return max(nums) if nums else None


def sas_min(*vals):
    nums = [v for v in vals if not is_sas_missing(v)]
    return min(nums) if nums else None


# ---------------------------------------------------------------------------
# Character length. SAS LENGTH() returns the length EXCLUDING trailing blanks,
# floored at 1 (a blank value returns 1, never 0). LENGTHN() is the same but
# returns 0 for blank. LENGTHC() returns the full length INCLUDING trailing
# blanks. Python len() and R nchar() are LENGTHC; a naive translation of
# LENGTH() over-counts by the trailing blanks and never floors to 1.
# ---------------------------------------------------------------------------


def sas_length(x):
    if x is None:
        return 1
    s = str(x).rstrip(" ")
    return len(s) if s else 1


def sas_lengthn(x):
    if x is None:
        return 0
    return len(str(x).rstrip(" "))


def sas_lengthc(x):
    if x is None:
        return 0
    return len(str(x))


# ---------------------------------------------------------------------------
# SUBSTR is 1-based. SAS SUBSTR(s, pos, len) starts at position pos where 1 is
# the first character, and returns len characters (or to the end if len is
# omitted). Python string slicing is 0-based, so a naive s[pos:pos+len] shifts
# every extracted field by one. R's substr is 1-based like SAS. When the request
# runs past the end, SAS returns the characters that exist.
# ---------------------------------------------------------------------------


def sas_substr(s, pos, length=None):
    if s is None:
        s = ""
    s = str(s)
    start = max(pos - 1, 0)
    return s[start:] if length is None else s[start:start + length]


# ---------------------------------------------------------------------------
# Macro arithmetic. %EVAL does INTEGER arithmetic: division keeps only the
# integer portion, truncating toward zero, so %eval(7/2) is 3 and %eval(-7/2)
# is -3. A naive translation to floating division returns 3.5 and silently
# changes every loop bound, index, and count computed in a macro. %SYSEVALF is
# the floating-point counterpart. Note R's %/% floors toward negative infinity,
# so the R translation must truncate (trunc(a/b)), not floor.
# ---------------------------------------------------------------------------


def _sas_int_div(a, b):
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def _eval_expr(node, integer):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("%EVAL: unsupported operand")
        if integer and not isinstance(node.value, int):
            raise ValueError("%EVAL requires integer operands (use %SYSEVALF)")
        return node.value if integer else float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_expr(node.operand, integer)
    if isinstance(node, ast.BinOp):
        a = _eval_expr(node.left, integer)
        b = _eval_expr(node.right, integer)
        if isinstance(node.op, ast.Add):
            return a + b
        if isinstance(node.op, ast.Sub):
            return a - b
        if isinstance(node.op, ast.Mult):
            return a * b
        if isinstance(node.op, ast.Div):
            return _sas_int_div(a, b) if integer else a / b
    raise ValueError("%EVAL: unsupported expression")


def sas_eval(expr):
    """SAS %EVAL: integer arithmetic, division truncates toward zero."""
    return _eval_expr(ast.parse(str(expr).strip(), mode="eval").body, integer=True)


def sas_sysevalf(expr):
    """SAS %SYSEVALF: floating-point evaluation."""
    return _eval_expr(ast.parse(str(expr).strip(), mode="eval").body, integer=False)


# ---------------------------------------------------------------------------
# Type coercion. SAS silently converts between character and numeric. The
# high-frequency landmine is CHARACTER TO NUMERIC: when a character value is
# used where a number is expected (arithmetic, a comparison against a number, an
# assignment to a numeric variable), SAS strips leading and trailing blanks and
# reads the value with the standard numeric informat. A value that is blank or
# does not parse as a standard number becomes MISSING; SAS sets _ERROR_ and logs
# a note, but execution continues. A naive translation reaches for float(x),
# which RAISES on exactly the blank and non-numeric rows SAS turns to missing,
# so the translation crashes where SAS quietly drops the row and keeps counting.
# It composes with the missing-is-smallest rule: a coerced-to-missing value
# sorts first and fails an ` > n` test, dropping out of a filtered group the way
# SAS drops it. The standard informat does NOT read commas, dollar signs, or hex,
# so "1,000", "$5", and "0x10" are missing, not 1000, 5, and 16. (R's native
# as.numeric would read "0x10" as 16; the reference rejects it, so the two
# translations agree on the SAS rule rather than on either host's default.)
# Numeric-to-character, the BEST12. right-justified rule, is the sibling and is
# deliberately not gated yet: its exact field width wants a SAS console pin
# before it enters the deterministic core.
# ---------------------------------------------------------------------------

# The standard SAS numeric informat: optional sign, then digits with an optional
# decimal point or a bare leading decimal, then optional E-notation. Nothing
# else -- no commas, currency, or hex.
_SAS_NUM_RE = re.compile(r"^[+-]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][+-]?[0-9]+)?$")


def sas_charnum(s):
    """SAS standard character-to-numeric conversion: blanks stripped, a blank or
    invalid value becomes missing (None), never an exception."""
    if s is None:
        return None
    t = str(s).strip()
    if not t or not _SAS_NUM_RE.match(t):
        return None
    return float(t)


# ---------------------------------------------------------------------------
# BY-group processing. The SAS DATA step is SEQUENTIAL and STATEFUL: it reads a
# BY-sorted stream one row at a time, exposing FIRST.var and LAST.var flags and
# carrying RETAINed variables across rows. pandas groupby is SET-BASED and
# stateless: it pools every row of a key and returns an aggregate, with no
# row-by-row first/last flag and no cross-row state. Those flags are the
# primitive real SAS code runs on: reset a running total at FIRST.id, accumulate
# down the group, output at LAST.id. FIRST.var/LAST.var follow the BY PREFIX: for
# BY a b, FIRST.b is set whenever the pair (a, b) differs from the previous row,
# which includes every row where a itself changes. The headline landmine is
# RETAIN across groups: a translation that forgets the FIRST.-reset accumulates a
# running total ACROSS group boundaries (a naive global cumsum) instead of
# resetting per group, and the two diverge from the second group on. The sum
# statement also treats a missing addend as zero, tying back to missing handling,
# where a plain Python + on None or NaN would raise or propagate. NOTSORTED, the
# multi-BY descending interactions, and the double-DOW loop are deliberately not
# characterized yet. `rows` must already be sorted by by_vars, as SAS requires.
# ---------------------------------------------------------------------------


def sas_by_groups(rows, by_vars):
    """Yield (index, first, last) for each row of a BY-sorted sequence, where
    first[v] and last[v] are the SAS FIRST.v / LAST.v flags. A flag on by-var v
    follows the prefix (by_vars up to and including v): FIRST.v is set when that
    prefix differs from the previous row, LAST.v when it differs from the next."""
    n = len(rows)

    def prefix(i, j):
        return tuple(rows[i][v] for v in by_vars[:j + 1])

    for i in range(n):
        first, last = {}, {}
        for j, v in enumerate(by_vars):
            p = prefix(i, j)
            first[v] = (i == 0) or prefix(i - 1, j) != p
            last[v] = (i == n - 1) or prefix(i + 1, j) != p
        yield i, first, last


def _sum_num(x):
    """The SAS sum statement treats a missing addend as zero."""
    return 0.0 if is_sas_missing(x) else x


def sas_retain_total(rows, by_vars, sum_var):
    """The canonical retain pattern: retain total; if first.<last by> then
    total=0; total + sum_var; output at last.<last by>. Returns one row per group
    with the running total, reset at each group start, which is the semantics a
    naive global accumulation (cumsum without the reset) gets wrong."""
    last_by = by_vars[-1]
    out, total = [], 0.0
    for i, first, last in sas_by_groups(rows, by_vars):
        if first[last_by]:
            total = 0.0
        total += _sum_num(rows[i][sum_var])
        if last[last_by]:
            out.append({**{v: rows[i][v] for v in by_vars}, "total": total})
    return out


# ---------------------------------------------------------------------------
# PROC SORT ordering. 499 programs, 27 percent of the public corpus, carry
# sort-dependent constructs (sort-risk probe, 2026-07-15), and three rules
# diverge from both pandas and R defaults. (1) MISSING SORTS FIRST: numeric
# missing orders below every number, negatives included; pandas puts NaN last
# (na_position default) and R puts NA last (na.last default), both the exact
# inverse. Under DESCENDING the whole order reverses, so missing lands LAST,
# which naive na_position juggling also gets wrong. (2) EQUALS IS THE DEFAULT:
# PROC SORT preserves the input order of ties (SAS 9.4 Procedures Guide, PROC
# SORT statement, EQUALS|NOEQUALS). Independent drafts disagreed on this exact
# pin (one asserted NOEQUALS), which is why it is taken from the documented
# spec and proven by fixture, not by vote. pandas sort_values defaults to an
# unstable quicksort. (3) BYTE COLLATION: default SORTSEQ compares bytes,
# case-sensitive, "B" < "a"; R consults the locale unless the sort runs with
# method="radix" (C-locale, stable), which is the R twin's whole trick.
# Character comparison pads the shorter operand with blanks, so trailing
# blanks NEVER order two values: the key strips them and 'a' vs 'a ' is a tie
# resolved by stability (and a duplicate to NODUPKEY, which keeps the FIRST
# occurrence in sorted order). Numeric-as-character sorts lexically by byte
# ('10' < '2'), the classic trap, inherited faithfully by treating char as
# char. Special missings (._ below . below .A through .Z, all below every
# number) are documented but NOT implemented: pandas and R collapse them to
# NaN on read, a recorded lossy edge, to be characterized if the corpus ever
# exercises it. SORTSEQ=LINGUISTIC is likewise out of scope, recorded.
# ---------------------------------------------------------------------------


def sas_sort_key(value):
    """Ordering key for one value of one sort variable. Numeric missing
    (None/NaN) keys below every number; character keys strip trailing blanks
    (SAS comparison pads the shorter operand, so trailing blanks are padding,
    never order; the all-blank value keys to '' and sorts first in byte
    order). A sort variable holds one type, as in SAS; keys from mixed types
    do not compare."""
    if isinstance(value, str):
        return value.rstrip(" ")
    if is_sas_missing(value):
        return (0, 0.0)
    return (1, float(value))


def sas_proc_sort(records, by, nodupkey=False):
    """PROC SORT reference over a list of dict records. `by` is a list of
    variable names or (variable, "ascending"|"descending") pairs. EQUALS
    semantics, the SAS default: ties keep input order, guaranteed by one
    STABLE sort pass per BY variable applied last-key first (each pass of
    Python's sorted is stable, including under reverse=True, so DESCENDING
    reverses order classes without disturbing ties). NODUPKEY keeps the first
    occurrence of each BY-key tuple in sorted order."""
    norm = [(v, "ascending") if isinstance(v, str) else tuple(v) for v in by]
    out = list(records)
    for var, direction in reversed(norm):
        out = sorted(out, key=lambda rec, _v=var: sas_sort_key(rec[_v]),
                     reverse=(direction == "descending"))
    if not nodupkey:
        return out
    seen, kept = set(), []
    for rec in out:
        key = tuple(repr(sas_sort_key(rec[v])) for v, _ in norm)
        if key not in seen:
            seen.add(key)
            kept.append(rec)
    return kept


# ---------------------------------------------------------------------------
# Numeric precision and storage (quirk 10). SAS stores every DATA-step numeric
# as an 8-byte IEEE 754 double, so its arithmetic is bit-identical to Python
# and R doubles; half the quirk is the MYTH that SAS does decimal math (the
# 0.1 + 0.2 pin misses 0.3 by the same margin in all three languages). Three
# real divergences. (1) INTEGER EXACTNESS ends at 2**53: Python ints are
# arbitrary precision, so 2**53 + 1 survives a Python int but collapses to
# 2**53 through any SAS numeric (IEEE round-to-even at storage); translations
# that keep IDs in int silently diverge from the SAS dataset. (2) LENGTH
# TRUNCATION: LENGTH 3 through 7 stores a numeric by TRUNCATING low-order
# mantissa bytes at dataset write (SAS Language Reference: Concepts, numeric
# precision; the documented largest-exact-integer table pins the rule). No
# pandas or R equivalent, and NO draft dossier surfaced it, which is itself a
# finding: the deadliest precision landmine is the one nobody drafted for.
# (3) FUZZ(x) returns the nearest integer when x lies within 1e-12 of it,
# else x unchanged; plain IF comparisons do NOT fuzz (exact binary equality),
# settling the dossier's low-confidence note from the spec. ROUND ties are
# quirk 1, already gated half-away (one dossier re-asserted bankers and is
# refuted by that gate). Special missings stay documented-not-implemented;
# the drafts also split on their order (._ sorts below ., per the spec).
# ---------------------------------------------------------------------------

# Largest integer stored exactly at each SAS numeric LENGTH (documented table).
SAS_MAX_EXACT_INT = {3: 8192, 4: 2097152, 5: 536870912, 6: 137438953472,
                     7: 35184372088832, 8: 9007199254740992}


def sas_num(value):
    """A value as SAS stores it: through an IEEE double. Collapses Python's
    arbitrary-precision ints exactly the way a DATA step would (round to even
    at the 2**53 cliff)."""
    return float(value)


def sas_num_trunc(value, length):
    """SAS LENGTH-statement storage: keep sign, exponent, and the high
    mantissa bytes; TRUNCATE the rest (big-endian layout, low-order mantissa
    last). length 8 is full precision; 3 is the SAS minimum."""
    if length not in SAS_MAX_EXACT_INT:
        raise ValueError("SAS numeric LENGTH is 3 through 8")
    raw = struct.pack(">d", float(value))
    return struct.unpack(">d", raw[:length] + b"\x00" * (8 - length))[0]


def sas_fuzz(x):
    """FUZZ(x): the nearest integer when within 1e-12 of it, else x."""
    n = math.floor(x + 0.5)
    return float(n) if abs(x - n) < 1e-12 else x


# ---------------------------------------------------------------------------
# PUT rendering (quirk 11). The formatted value is display only; the stored
# value never changes. Pinned rules: (1) w.d ROUNDS HALF AWAY FROM ZERO on
# the STORED DOUBLE (the SAS rounding family; sprintf and R formatC round
# half to even, so 2.5 under 3.0 prints 3 in SAS and 2 naively), and when the
# rounded value cannot fit, SAS DROPS DECIMALS to fit before it fills the
# field with asterisks. (2) MISSING PRINTS AS A PERIOD, right-justified (the
# MISSING= system option default '.'): both draft dossiers asserted blanks and
# the spec says otherwise, so it is pinned. (3) DATE9. is locale-fixed
# English over the 1960-01-01 epoch, and YYMMDD8. INPUT reads to epoch days
# with the CHAR->NUM temperament (unparsable reads as missing, never an
# exception). The 2.675 myth-buster pin: the stored double sits below the
# apparent tie and prints 2.67 in every engine, because every engine rounds
# the stored value, not the decimal literal. BESTw. is deferred, documented.
# One dossier fixture claimed INPUT('20240101', yymmdd8.) = 19760; the
# arithmetic says 23376 and the gate pins the arithmetic.
# ---------------------------------------------------------------------------

_MON = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
        "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


def _round_half_away_decimal(value, d):
    """Round the exact stored double half away from zero at d decimals,
    via Decimal(value), which expands the double's exact binary value
    (decimal.ROUND_HALF_UP is ties-away-from-zero)."""
    q = decimal.Decimal(1).scaleb(-d)
    return decimal.Decimal(value).quantize(q, rounding=decimal.ROUND_HALF_UP)


def sas_putn(value, w, d=0):
    """PUT(value, w.d): right-justified in width w with d decimals, ties half
    away from zero on the stored double, decimals dropped to fit, asterisk
    fill when even the integer part cannot fit. Missing prints as '.'."""
    if is_sas_missing(value):
        return ".".rjust(w)
    for dd in range(d, -1, -1):
        s = f"{_round_half_away_decimal(float(value), dd):.{dd}f}"
        if len(s) <= w:
            return s.rjust(w)
    return "*" * w


def sas_put_date9(days):
    """PUT(date, DATE9.): DDMONYYYY, English months, epoch 1960-01-01 = 0."""
    dt = SAS_EPOCH + datetime.timedelta(days=int(days))
    return f"{dt.day:02d}{_MON[dt.month - 1]}{dt.year:04d}"


def sas_input_yymmdd8(s):
    """INPUT(string, yymmdd8.): days since the SAS epoch as a float;
    blank-tolerant; unparsable reads as missing (None), never an exception."""
    try:
        dt = datetime.datetime.strptime(s.strip(), "%Y%m%d").date()
    except (ValueError, AttributeError):
        return None
    return float((dt - SAS_EPOCH).days)


# ---------------------------------------------------------------------------
# Statistical functions (quirk 12, first half: probability, quantile, and
# moment functions). The family the Littles surfaced from the drafts' own
# landmine notes and the exec gate confirmed by catching hallucinated survey
# APIs. Two rules. (1) PROB*/quantile functions map cleanly onto scipy.stats
# and base R distributions ONCE the parameterization is pinned: PROBCHI and
# CINV are chi-square CDF and quantile, PROBT and TINV are Student t (TINV
# takes the LEFT-tail probability: TINV(0.975, df) is the two-sided 5 percent
# critical value), PROBF and FINV are F, PROBNORM and PROBIT are standard
# normal. The pins are published table classics (3.841458821 chi-square on
# 1 df at 0.95; 2.228138852 t on 10 df at 0.975), which is oracle layer 1:
# outputs the world already printed. Domain violations follow the SAS runtime
# temperament: missing with _ERROR_, never an exception, so the references
# return None out of domain. Noncentral forms are deferred, documented.
# (2) MOMENTS: SAS skewness and kurtosis are the corrected G1 and G2
# estimators (kurtosis is EXCESS, with the 3(n-1)^2/((n-2)(n-3)) term), which
# scipy matches only with bias=False and base R does not provide at all;
# skewness needs n >= 3, kurtosis n >= 4, and a zero-variance series returns
# missing. VARDEF= controls the variance divisor (DF the default, N;
# WEIGHT/WDF deferred to the weight-semantics quirk). Analysis variables drop
# missing values first, the aggregate-missing temperament.
# ---------------------------------------------------------------------------


def sas_probnorm(x):
    """PROBNORM(x): standard normal CDF (stdlib erf; no scipy needed)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _st():
    import scipy.stats
    return scipy.stats


def sas_probit(p):
    """PROBIT(p): standard normal quantile; p in (0,1) else missing."""
    return float(_st().norm.ppf(p)) if 0.0 < p < 1.0 else None


def sas_probchi(x, df):
    """PROBCHI(x, df): chi-square CDF; x >= 0, df > 0 else missing."""
    return float(_st().chi2.cdf(x, df)) if x >= 0 and df > 0 else None


def sas_cinv(p, df):
    """CINV(p, df): chi-square quantile; p in [0,1) and df > 0 else missing."""
    return float(_st().chi2.ppf(p, df)) if 0.0 <= p < 1.0 and df > 0 else None


def sas_probt(x, df):
    """PROBT(x, df): Student t CDF (left tail); df > 0 else missing."""
    return float(_st().t.cdf(x, df)) if df > 0 else None


def sas_tinv(p, df):
    """TINV(p, df): Student t LEFT-tail quantile; p in (0,1), df > 0."""
    return float(_st().t.ppf(p, df)) if 0.0 < p < 1.0 and df > 0 else None


def sas_probf(x, ndf, ddf):
    """PROBF(x, ndf, ddf): F CDF; x >= 0 and positive dfs else missing."""
    if x >= 0 and ndf > 0 and ddf > 0:
        return float(_st().f.cdf(x, ndf, ddf))
    return None


def sas_finv(p, ndf, ddf):
    """FINV(p, ndf, ddf): F quantile; p in [0,1), positive dfs."""
    if 0.0 <= p < 1.0 and ndf > 0 and ddf > 0:
        return float(_st().f.ppf(p, ndf, ddf))
    return None


def _analysis_values(vals):
    return [float(v) for v in vals if not is_sas_missing(v)]


def sas_mean(vals):
    xs = _analysis_values(vals)
    return sum(xs) / len(xs) if xs else None


def sas_std(vals, vardef="DF"):
    """Standard deviation under VARDEF= (DF default, N). Missing when the
    divisor is not positive."""
    xs = _analysis_values(vals)
    n = len(xs)
    div = {"DF": n - 1, "N": n}[vardef.upper()]
    if div <= 0:
        return None
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / div)


def sas_skewness(vals):
    """SAS skewness: G1 = n/((n-1)(n-2)) * sum(z^3) with the VARDEF=DF std;
    missing for n < 3 or zero variance."""
    xs = _analysis_values(vals)
    n = len(xs)
    if n < 3:
        return None
    s = sas_std(xs)
    if not s:
        return None
    m = sum(xs) / n
    return (n / ((n - 1) * (n - 2))) * sum(((x - m) / s) ** 3 for x in xs)


def sas_kurtosis(vals):
    """SAS kurtosis: excess G2 = n(n+1)/((n-1)(n-2)(n-3)) * sum(z^4)
    - 3(n-1)^2/((n-2)(n-3)); missing for n < 4 or zero variance."""
    xs = _analysis_values(vals)
    n = len(xs)
    if n < 4:
        return None
    s = sas_std(xs)
    if not s:
        return None
    m = sum(xs) / n
    t4 = sum(((x - m) / s) ** 4 for x in xs)
    return (n * (n + 1) / ((n - 1) * (n - 2) * (n - 3))) * t4 \
        - 3.0 * (n - 1) ** 2 / ((n - 2) * (n - 3))


# ---------------------------------------------------------------------------
# WEIGHT semantics (quirk 12, second half). PROC MEANS with a WEIGHT variable,
# pinned against two conflicting dossiers. (1) THE EXCLUSION RULE: a MISSING
# weight excludes the observation; zero and negative weights are INCLUDED by
# default, and the documented EXCLNPWGT option exists precisely to exclude
# nonpositive weights, which proves the default includes them (one dossier
# asserted excluded-as-missing; the option's existence refutes it). A zero
# weight therefore contributes nothing to the sums but still counts toward n,
# which silently changes the VARDEF=DF divisor: the subtlest consequence and
# a pinned fixture. (2) THE DIVISOR SET: VARDEF=DF divides the weighted CSS
# by n-1 (observation count, not weight sum), N by n, WDF by sum(w)-1, and
# WEIGHT by sum(w). One dossier offered sum(w) - sum(w^2)/sum(w) for
# VARDEF=WEIGHT: that is the effective-df of reliability weights, a real
# statistics concept hallucinated into SAS, refuted by the documented set.
# (3) PATHOLOGY IS HONEST: negative weights can drive the weighted CSS
# negative, and the reference returns missing for the std rather than
# inventing a number. (4) PROC FREQ's WEIGHT sums possibly non-integer
# weights into cell counts, missing weights excluded, and levels whose total
# weight is zero drop from the table by default (the ZEROS option exists to
# keep them). Weighted skewness and kurtosis are deferred, documented: the
# SAS weighted higher-moment formulas need their own spec pass.
# ---------------------------------------------------------------------------


def _weighted_rows(pairs, excl_npwgt=False):
    """(x, w) pairs as PROC MEANS uses them: missing weight excludes the row,
    missing x excludes the row (analysis variable), EXCLNPWGT drops w <= 0."""
    rows = [(float(x), float(w)) for x, w in pairs
            if not is_sas_missing(x) and not is_sas_missing(w)]
    if excl_npwgt:
        rows = [(x, w) for x, w in rows if w > 0]
    return rows


def sas_weighted_mean(pairs, excl_npwgt=False):
    rows = _weighted_rows(pairs, excl_npwgt)
    sw = sum(w for _x, w in rows)
    if not rows or sw == 0:
        return None
    return sum(w * x for x, w in rows) / sw


def sas_weighted_std(pairs, vardef="DF", excl_npwgt=False):
    """Weighted standard deviation under the documented VARDEF divisor set:
    DF n-1, N n, WDF sum(w)-1, WEIGHT sum(w). Missing when the divisor is not
    positive or the weighted CSS goes negative (negative weights)."""
    rows = _weighted_rows(pairs, excl_npwgt)
    n = len(rows)
    sw = sum(w for _x, w in rows)
    if not rows or sw == 0:
        return None
    mean = sum(w * x for x, w in rows) / sw
    css = sum(w * (x - mean) ** 2 for x, w in rows)
    div = {"DF": n - 1, "N": n, "WDF": sw - 1, "WEIGHT": sw}[vardef.upper()]
    if div <= 0 or css < 0:
        return None
    return math.sqrt(css / div)


def sas_freq_weighted(pairs, keep_zeros=False):
    """PROC FREQ with WEIGHT: cell counts are weight sums (non-integer
    allowed), missing weights excluded, zero-total levels dropped unless
    ZEROS. Returns {level: weighted count} with insertion order by first
    appearance, as the FREQ table orders unformatted values."""
    counts = {}
    for level, w in pairs:
        if is_sas_missing(w):
            continue
        counts[level] = counts.get(level, 0.0) + float(w)
    if not keep_zeros:
        counts = {k: v for k, v in counts.items() if v != 0}
    return counts


# ---------------------------------------------------------------------------
# Missing-value arithmetic (quirk 14). Four rules, each a divergence from
# BOTH host languages. (1) PROPAGATION: any arithmetic operator with a
# missing operand yields missing, with a log note, never an exception;
# Python's None raises TypeError and NaN propagates silently, R's NA
# propagates but infects comparisons differently (below). (2) DIVISION BY
# ZERO yields missing with a note, never an exception: Python raises, numpy
# and R produce Inf, all three invent a value SAS refuses to. (3) THE PAIRED
# LANDMINE: the + operator propagates missing while the SUM() function
# ignores it (all-missing sums to missing), and translations constantly swap
# one for the other; the pair is pinned side by side. (4) COMPARISONS TREAT
# MISSING AS SMALLER THAN EVERY NUMBER: "if x < 0" CATCHES missing x in SAS,
# silently does not in Python (NaN comparisons are all false), and yields NA
# in R (filters drop the row); missing EQ missing is TRUE in SAS where
# NaN != NaN everywhere else. In logical context missing and zero are false,
# everything else true. Special missings' inter-ordering stays
# documented-not-implemented, as in the sort quirk.
# ---------------------------------------------------------------------------


def sas_arith(a, op, b):
    """Arithmetic with the SAS temperament: a missing operand or a zero
    divisor yields missing (with a log note in real SAS), never an
    exception. Division is floating (the DATA step's /), not %EVAL's."""
    if is_sas_missing(a) or is_sas_missing(b):
        return None
    a, b = float(a), float(b)
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        return None if b == 0 else a / b
    if op == "**":
        return a ** b
    raise ValueError(f"sas_arith: operator {op!r} not characterized")


def sas_sum(*vals):
    """SUM(of ...): ignores missing arguments; all-missing is missing.
    The pair to sas_arith('+'): the operator propagates, the function
    ignores, and swapping them is the classic translation bug."""
    nums = [float(v) for v in vals if not is_sas_missing(v)]
    return sum(nums) if nums else None


def sas_num_lt(a, b):
    """The SAS comparison order: missing is smaller than every number, and
    missing EQ missing is true (so missing < missing is false). Returns a
    real bool, never a third state."""
    am, bm = is_sas_missing(a), is_sas_missing(b)
    if am:
        return not bm
    if bm:
        return False
    return float(a) < float(b)


def sas_truth(x):
    """Logical context: missing and zero are false, everything else true."""
    return not (is_sas_missing(x) or float(x) == 0)


# ---------------------------------------------------------------------------
# MERGE BY (quirk 15): the data step's second stateful pillar, 501 corpus
# receipts in the sort-risk probe. SAS match-merge is NOT a relational join:
# within each BY group it walks row-by-row, and the group emits
# max(n_left, n_right) rows, with the shorter side's variables RETAINED
# (carried forward) once it exhausts: a 2x3 group yields 3 rows where every
# SQL-family join yields 6 (pandas merge, dplyr joins, the trap). Shared
# variables follow PDV read order: the right (later-listed) dataset's read
# overwrites the left's every iteration it still has rows, and the moment it
# exhausts mid-group the value FLIPS back to the left's fresh reads, because
# the left keeps reading and nothing overwrites it: the exhaustion flip,
# pinned. Unmatched groups emit the present side with the absent side's
# variables missing. IN= flags are group-level and retained: 1 for every row
# of a group the dataset participates in, even after its rows exhaust.
# Missing BY values MATCH each other (missing EQ missing, quirk 14), unlike
# every SQL join's NULL semantics. Inputs must be BY-sorted, as SAS requires;
# unsorted input is a SAS runtime error and out of scope here.
# ---------------------------------------------------------------------------


def sas_merge_by(left, right, by):
    """Match-merge two BY-sorted lists of dict records. Returns (rows,
    in_left, in_right) where the in-lists carry the group-level IN= flag per
    output row. Column semantics: left-only and right-only variables carry
    forward within the group; shared non-BY variables follow the PDV order
    (right overwrites while reading, flips to left on right's exhaustion)."""
    def key_of(rec):
        return tuple(sas_sort_key(rec[v]) for v in by)

    def groups(rows):
        out = {}
        for rec in rows:
            out.setdefault(key_of(rec), []).append(rec)
        return out

    gl, gr = groups(left), groups(right)
    lcols = list(left[0].keys()) if left else []
    rcols = list(right[0].keys()) if right else []
    shared = [c for c in lcols if c in rcols and c not in by]
    lonly = [c for c in lcols if c not in rcols and c not in by]
    ronly = [c for c in rcols if c not in lcols and c not in by]

    rows, in_l, in_r = [], [], []
    for key in sorted(set(gl) | set(gr), key=lambda k: k):
        ls, rs = gl.get(key, []), gr.get(key, [])
        nl, nr = len(ls), len(rs)
        n = max(nl, nr)
        for i in range(n):
            rec = {}
            for v in by:
                rec[v] = (ls or rs)[0][v]
            for v in lonly:
                rec[v] = ls[min(i, nl - 1)][v] if nl else None
            for v in ronly:
                rec[v] = rs[min(i, nr - 1)][v] if nr else None
            for v in shared:
                if nr and i < nr:
                    rec[v] = rs[i][v]
                elif nl:
                    rec[v] = ls[min(i, nl - 1)][v]
                else:
                    rec[v] = rs[nr - 1][v]
            rows.append(rec)
            in_l.append(1 if nl else 0)
            in_r.append(1 if nr else 0)
    return rows, in_l, in_r


# ---------------------------------------------------------------------------
# PROC TRANSPOSE (quirk 16). The reshape is BY-group-wise and single-pass:
# one output row per VAR variable per BY group. Without ID, data columns are
# COL1..COLn sized by the LARGEST group (ragged groups fill missing); with
# ID, columns are the ID variable's values mangled to valid names (invalid
# characters to underscores, a leading digit gets an underscore PREFIX), and
# the output carries the UNION of ID values across all groups in order of
# first appearance. VAR defaults to the numeric variables not otherwise
# claimed; character variables transpose only when named explicitly. _NAME_
# always carries the source variable's name. DUPLICATE ID VALUES IN A GROUP
# ARE AN ERROR by default: SAS refuses to guess, and only the LET option
# turns that into last-wins with a warning: while pandas pivot_table silently
# AGGREGATES duplicates (mean by default), the philosophical divergence
# pinned in the gate. PREFIX= prepends to ID values (or replaces COL).
# _LABEL_ machinery and OUT= dataset options are deferred, documented.
# ---------------------------------------------------------------------------


def _sas_valid_name(value, prefix=None):
    """Mangle a value into a SAS variable name. Column names come from the
    FORMATTED ID value, so whole numerics render bare (BEST-style, 2020.0
    names _2020, never _2020_0); then invalid characters become underscores
    and a leading digit gains a leading underscore. PREFIX prepends before
    the mangling rules apply."""
    if isinstance(value, float) and value == int(value):
        s = str(int(value))
    elif isinstance(value, float):
        s = f"{value:g}"
    else:
        s = str(value).strip()
    if prefix:
        s = prefix + s
    s = re.sub(r"[^A-Za-z0-9_]", "_", s)
    if not s or s[0].isdigit():
        s = "_" + s
    return s[:32]


def sas_transpose(rows, by=None, var=None, id_var=None, prefix=None,
                  let=False):
    """PROC TRANSPOSE reference over dict records. Returns (out_rows,
    columns). rows must be BY-sorted. VAR defaults to numeric variables not
    used as BY or ID. Duplicate ID within a group raises unless let=True
    (the LET option), where the last occurrence wins."""
    by = by or []

    def is_num(v):
        return v is None or isinstance(v, (int, float))

    all_cols = list(rows[0].keys()) if rows else []
    if var is None:
        var = [c for c in all_cols
               if c not in by and c != id_var
               and all(is_num(r[c]) for r in rows)]

    groups, order = {}, []
    for rec in rows:
        key = tuple(rec[v] for v in by)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(rec)

    if id_var is not None:
        id_cols = []
        for key in order:
            seen = set()
            for rec in groups[key]:
                name = _sas_valid_name(rec[id_var], prefix)
                if name in seen and not let:
                    raise ValueError(
                        f"duplicate ID value {rec[id_var]!r} in BY group "
                        f"{key!r}: SAS errors without LET")
                seen.add(name)
                if name not in id_cols:
                    id_cols.append(name)
        data_cols = id_cols
    else:
        width = max((len(g) for g in groups.values()), default=0)
        base = prefix if prefix else "COL"
        data_cols = [f"{base}{i + 1}" for i in range(width)]

    out = []
    for key in order:
        grp = groups[key]
        for v in var:
            rec = {b: k for b, k in zip(by, key)}
            rec["_NAME_"] = v
            for c in data_cols:
                rec[c] = None
            if id_var is not None:
                for src in grp:
                    rec[_sas_valid_name(src[id_var], prefix)] = src[v]
            else:
                for i, src in enumerate(grp):
                    rec[data_cols[i]] = src[v]
            out.append(rec)
    return out, by + ["_NAME_"] + data_cols


# ---------------------------------------------------------------------------
# INTNX and the WEEK interval (quirk 17), closing the deferrals the INTCK
# section declared. INTNX(interval, date, n, alignment) advances by interval
# INDEX arithmetic and then ALIGNS, and the alignment default is BEGINNING:
# intnx('month', 15JAN2020, 1) is 01FEB2020, not 15FEB2020, which is the
# landmine, because every naive host idiom (relativedelta, lubridate %m+%)
# does same-day arithmetic. 'SAME' does same-relative-position with END
# CLIPPING (31JAN plus one month is 29FEB2020 or 28FEB2021; 29FEB2020 plus
# one year is 28FEB2021). 'END' is the interval's last day; 'MIDDLE' is the
# floor midpoint of the interval's day span (documented as the middle day;
# the floor derivation is labeled and proven cross-language). WEEK intervals
# begin on SUNDAY: 01JAN1960 was a Friday, so the epoch's week begins
# 27DEC1959 (day -5), and INTCK('WEEK', a, b) counts Sunday boundaries
# crossed, closing the WEEK deferral. Shifted and multiplied intervals
# (WEEK.2, YEAR.7) stay deferred, documented. Both drafts whiffed this
# dossier during the saturation window; the family is pinned from the
# documented spec alone, like quirk 14.
# ---------------------------------------------------------------------------

_ALIGN = {"B": "B", "BEGINNING": "B", "M": "M", "MIDDLE": "M",
          "E": "E", "END": "E", "S": "S", "SAME": "S"}


def _month_index(d):
    return d.year * 12 + d.month - 1


def _month_bounds(idx):
    y, m = divmod(idx, 12)
    first = datetime.date(y, m + 1, 1)
    nxt = datetime.date(y + (m + 1) // 12, (m + 1) % 12 + 1, 1)
    return first, nxt - datetime.timedelta(days=1)


def sas_intnx(interval, days, increment, alignment="B"):
    """INTNX over SAS epoch-day integers. DAY, WEEK (Sunday-first), MONTH,
    QTR, YEAR, with B/M/E/S alignment (BEGINNING is the SAS default)."""
    iv = interval.strip().upper()
    al = _ALIGN[alignment.strip().upper()]
    d = SAS_EPOCH + datetime.timedelta(days=int(days))

    if iv == "DAY":
        return int(days) + int(increment)

    if iv == "WEEK":
        week_start = int(days) - ((int(days) + 5) % 7)
        week_start += 7 * int(increment)
        if al == "B":
            out = week_start
        elif al == "E":
            out = week_start + 6
        elif al == "M":
            out = week_start + 3
        else:
            out = week_start + ((int(days) + 5) % 7)
        return out

    if iv in ("MONTH", "QTR", "YEAR"):
        step = {"MONTH": 1, "QTR": 3, "YEAR": 12}[iv]
        idx = (_month_index(d) // step + int(increment)) * step
        first, _last = _month_bounds(idx)
        _f2, last = _month_bounds(idx + step - 1)
        if al == "B":
            out = first
        elif al == "E":
            out = last
        elif al == "M":
            out = first + datetime.timedelta(
                days=(last - first).days // 2)
        else:
            if iv == "YEAR":
                try:
                    out = datetime.date(first.year, d.month, d.day)
                except ValueError:
                    out = datetime.date(first.year, d.month, 28)
            else:
                anchor_first, _al = _month_bounds(
                    (_month_index(d) // step) * step)
                offset = (d - anchor_first).days
                span = (last - first).days
                out = first + datetime.timedelta(days=min(offset, span))
        return date_to_sas(out)

    raise ValueError(f"sas_intnx: interval {interval!r} not yet characterized")


def sas_intck_week(days1, days2):
    """INTCK('WEEK', a, b): Sunday boundaries crossed (weeks begin Sunday;
    the epoch 01JAN1960 was a Friday, so its week began 27DEC1959)."""
    def widx(n):
        return (int(n) + 5) // 7
    return widx(days2) - widx(days1)


# ---------------------------------------------------------------------------
# PROC FORMAT user formats (quirk 18): VALUE definitions as lookup maps, and
# the classification behavior that makes them dangerous in translation:
# PROC FREQ and PROC MEANS CLASS group by the FORMATTED value, so a format
# silently changes analysis grain. Range endpoints are INCLUSIVE by default;
# '<' makes an endpoint exclusive on either side (1-<5, 1<-5). LOW and HIGH
# are open ends, and LOW EXCLUDES MISSING for numeric formats: missing
# matches only an explicit '.' entry or OTHER. The fallthrough is the pin
# the drafts miss: an unmatched value with no OTHER renders AS ITSELF (the
# BEST-style rendering), never blank. Overlapping ranges are a build-time
# ERROR (SAS refuses without MULTILABEL, which is out of scope, documented).
# Multiple values may share one label. Character ranges compare in byte
# order with the quirk-9 trailing-blank key.
# ---------------------------------------------------------------------------

LOW = ("__LOW__",)
HIGH = ("__HIGH__",)


def sas_format_def(entries):
    """Build a user format. entries: list of (spec, label). spec is a value,
    a list of values, ('.',) for explicit missing, ('OTHER',), or a range
    tuple (lo, hi, lo_inclusive, hi_inclusive) where lo/hi may be LOW/HIGH.
    Overlapping range/value coverage raises, as PROC FORMAT does."""
    fmt = {"values": {}, "ranges": [], "other": None, "missing": None}

    def key(v):
        return v.rstrip(" ") if isinstance(v, str) else float(v)

    for spec, label in entries:
        if spec == ("OTHER",):
            fmt["other"] = label
        elif spec == (".",):
            fmt["missing"] = label
        elif isinstance(spec, tuple) and len(spec) == 4:
            fmt["ranges"].append((spec, label))
        else:
            vals = spec if isinstance(spec, list) else [spec]
            for v in vals:
                if key(v) in fmt["values"]:
                    raise ValueError(f"overlapping format value {v!r}")
                fmt["values"][key(v)] = label

    def lo_key(r):
        (lo, _hi, _li, _hi2), _lab = r
        return (0,) if lo is LOW else (1, key(lo))

    fmt["ranges"].sort(key=lo_key)
    for (a, _la), (b, _lb) in zip(fmt["ranges"], fmt["ranges"][1:]):
        _lo1, hi1, _i1, hi1_inc = a
        lo2, _hi2, lo2_inc, _i2 = b
        if hi1 is HIGH:
            raise ValueError("overlapping format ranges")
        if lo2 is LOW:
            raise ValueError("overlapping format ranges")
        if key(hi1) > key(lo2) or (key(hi1) == key(lo2)
                                   and hi1_inc and lo2_inc):
            raise ValueError("overlapping format ranges")
    return fmt


def sas_put_fmt(value, fmt):
    """Apply a user format: exact values, then ranges, then explicit missing,
    then OTHER, then the fallthrough rendering of the value itself. LOW
    excludes numeric missing."""
    def key(v):
        return v.rstrip(" ") if isinstance(v, str) else float(v)

    missing = is_sas_missing(value)
    if not missing and key(value) in fmt["values"]:
        return fmt["values"][key(value)]
    if not missing:
        kv = key(value)
        for (lo, hi, lo_inc, hi_inc), label in fmt["ranges"]:
            lo_ok = lo is LOW or (kv > key(lo) or (lo_inc and kv == key(lo)))
            hi_ok = hi is HIGH or (kv < key(hi) or (hi_inc and kv == key(hi)))
            if lo_ok and hi_ok:
                return label
    if missing:
        if fmt["missing"] is not None:
            return fmt["missing"]
        if fmt["other"] is not None:
            return fmt["other"]
        return "."
    if fmt["other"] is not None:
        return fmt["other"]
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value).rstrip(" ") if isinstance(value, str) else f"{value:g}"


def sas_freq_formatted(values, fmt):
    """PROC FREQ under a format: cells pool by FORMATTED value, first
    appearance order, the analysis-grain change the quirk warns about."""
    counts = {}
    for v in values:
        label = sas_put_fmt(v, fmt)
        counts[label] = counts.get(label, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Arrays (quirk 19). A SAS array is a NAME LIST, not a data structure: arr{i}
# ALIASES the i-th listed PDV variable, so writes through the array ARE
# writes to the variable and writes to the variable are visible through the
# array, where a Python list or R vector COPIES values at construction and
# silently divorces from the variables: the landmine. Subscripts are 1-based
# by default and support ARBITRARY declared bounds ({1990:1995} indexes by
# year, the census idiom); DIM is the element count, LBOUND and HBOUND the
# declared bounds. An out-of-range subscript HALTS the data step (array
# subscript out of range), a harder temperament than missing-with-a-note, so
# the reference raises. _TEMPORARY_ arrays own no PDV variables and are
# AUTOMATICALLY RETAINED across iterations (as are initial-value arrays),
# while ordinary PDV variables reset each iteration: the retention pin.
# Multi-dimensional arrays and old-style DO OVER stay deferred, documented.
# ---------------------------------------------------------------------------


class sas_array:
    """An aliasing view over a PDV dict: arr[i] reads and writes
    pdv[names[i - lo]]. Default 1-based; lo sets a custom lower bound."""

    def __init__(self, pdv, names, lo=1):
        self.pdv, self.names, self.lo = pdv, list(names), lo

    def _name(self, i):
        j = i - self.lo
        if j < 0 or j >= len(self.names):
            raise IndexError(
                f"array subscript out of range: {i} (bounds {self.lo}:"
                f"{self.lo + len(self.names) - 1}); SAS halts the data step")
        return self.names[j]

    def __getitem__(self, i):
        return self.pdv[self._name(i)]

    def __setitem__(self, i, v):
        self.pdv[self._name(i)] = v

    def dim(self):
        return len(self.names)

    def lbound(self):
        return self.lo

    def hbound(self):
        return self.lo + len(self.names) - 1

    def values(self):
        return [self.pdv[n] for n in self.names]


def sas_temp_array(n, init=None, lo=1):
    """_TEMPORARY_ array: no PDV variables and retained across iterations by
    definition; initial values allowed. The caller keeps the object across
    simulated iterations exactly as the PDV keeps temporaries."""
    store = {f"__temp{i}__": (init[i] if init else None) for i in range(n)}
    return sas_array(store, list(store.keys()), lo)


# ---------------------------------------------------------------------------
# Fisher exact, 2x2 (the 2018-corpus family). SAS PROC FREQ with an EXACT
# FISHER statement reports three p-values: left-sided (XPL_FISH),
# right-sided (XPR_FISH), and two-sided (XP2_FISH). R fisher.test and
# scipy.stats.fisher_exact BOTH default to two-sided, so a translation that
# wants the SAS left column must pass alternative='less' explicitly, and
# misreading XPL as XPR flips the tail silently. The two-sided definition is
# the standard one: sum the probabilities of every table with the same
# margins whose probability does not exceed the observed table's. One-sided
# 'less' is the lower tail on the top-left cell. Zero cells stay exact;
# scipy does not report the conditional-MLE odds ratio or its interval, so
# CI rows route to R.
# ---------------------------------------------------------------------------


def sas_fisher_exact(a, b, c, d, alternative="two"):
    """Exact Fisher p-value for the 2x2 table [[a, b], [c, d]] (top-left
    cell a). alternative: 'two' (default, matches R and scipy defaults),
    'less' (lower tail on a, the SAS left-sided column), or 'greater'.
    Pure integer hypergeometric, no float rounding: the same algorithm R
    and scipy implement for 2x2 tables."""

    from math import comb

    def pmf(x):
        return (comb(a + b, x) * comb(c + d, a + c - x)
                / comb(a + b + c + d, a + c))

    lo = max(0, a - d)
    hi = min(a + b, a + c)
    if alternative == "less":
        return sum(pmf(x) for x in range(lo, a + 1))
    if alternative == "greater":
        return sum(pmf(x) for x in range(a, hi + 1))
    p0 = pmf(a)
    return sum(pmf(x) for x in range(lo, hi + 1) if pmf(x) <= p0)


# ---------------------------------------------------------------------------
# Significant-digit rounding (the four-sig-fig surface). SAS has no %g-style
# significant-digit format; the policy (Census DSEP: four significant
# digits) is realized by rounding to an explicit power-of-ten unit with
# ROUND, then rendering with a normal format. R sprintf('%g') and Python
# '%g' formatting BOTH round half to even, so %g or signif() alone silently
# disagrees with SAS exactly where the policy lives: 0.125 to two digits is
# 0.13 in SAS and 0.12 in both open languages, and 9.995 to three digits is
# 10.0 in SAS (the ROUND fuzz absorbs the representation error) and 9.99 in
# both. Compute the unit from the magnitude first; never format sig figs
# via %g alone.
# ---------------------------------------------------------------------------


def sas_sigfig_round(x: float, n: int) -> float:
    """Round x to n significant digits the SAS way: unit from the
    magnitude, then sas_round (half away from zero, fuzzed). Zero is
    returned as-is. The rendered digits then come from a normal format
    (PUT w.d or a bare %f), never from %g."""
    if x == 0:
        return 0.0
    unit = 10.0 ** (math.floor(math.log10(abs(x))) - n + 1)
    return sas_round(x, unit)


# ---------------------------------------------------------------------------
# CSV import type inference (the PROC IMPORT surface). PROC IMPORT
# dbms=csv guesses column types from a WINDOW: the first guessingrows
# non-blank values (default 20). A column clean inside the window but dirty
# later is read NUMERIC by SAS and the late non-numeric value becomes
# missing with a note; pandas and R infer from the WHOLE file and read the
# same column character. Both defaults are right for their engine and the
# missing-value sets differ: the divergence must be pinned per file, never
# assumed. Leading-zero identifiers (zip codes, ids) are stripped by ALL
# three engines under default inference; identifiers read as character
# explicitly. SAS date guessing (informats) is deliberately not
# characterized here.
# ---------------------------------------------------------------------------


def sas_proc_import_guess(rows, guessingrows=20):
    """Emulate PROC IMPORT dbms=csv type guessing over a scan window:
    per column, examine the first guessingrows non-blank values; NUM if
    every one is numeric-shaped (sign, digits, optional decimal or
    exponent, surrounding spaces), else CHAR. A column of only blanks in
    the window reads CHAR. Rows are sequences of str values."""
    if not rows:
        return []
    n_cols = len(rows[0])
    num_re = (r"^\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
              r"(?:[eE][+-]?\d+)?\s*$")
    import re as _re
    types = []
    for c in range(n_cols):
        seen = []
        for row in rows:
            if len(seen) >= guessingrows:
                break
            v = str(row[c]).strip()
            if v != "":
                seen.append(v)
        if seen and all(_re.match(num_re, v) for v in seen):
            types.append("NUM")
        else:
            types.append("CHAR")
    return types


# ---------------------------------------------------------------------------
# PROC FREQ descriptive percents (the listing surface). SAS computes three
# percentages for a two-way table: the cell percent (count / grand total of
# non-missing), the row percent (count / row total), and the column percent
# (count / column total), displayed with one decimal by default. Missing
# levels are EXCLUDED from every denominator unless /MISSING is set. The
# 0/0 case (a zero cell on a zero row or column total) prints as '.' in the
# SAS listing; R prop.table and pandas crosstab normalize produce NaN, so a
# byte-for-byte listing translation must render non-finite percents
# explicitly. pandas crosstab margins combined with normalize compute
# normalized-value margins, never SAS totals: pin margins separately.
# ---------------------------------------------------------------------------


def sas_freq_pcts(a, b, c, d):
    """Cell, row, and column percents for table [[a, b], [c, d]] exactly as
    PROC FREQ computes them (missing excluded, one-decimal display is the
    caller's format). None marks a 0/0 percent, the SAS '.' cell."""
    n = a + b + c + d
    r1, r2 = a + b, c + d
    c1, c2 = a + c, b + d

    def pct(num, den):
        return None if den == 0 else 100.0 * num / den

    return {
        (0, 0): (a, pct(a, n), pct(a, r1), pct(a, c1)),
        (0, 1): (b, pct(b, n), pct(b, r1), pct(b, c2)),
        (1, 0): (c, pct(c, n), pct(c, r2), pct(c, c1)),
        (1, 1): (d, pct(d, n), pct(d, r2), pct(d, c2)),
    }


def sas_freq_oneway(counts):
    """One-way listing rows: (count, percent, cumulative count, cumulative
    percent) per level, the PROC FREQ default listing shape. None for a
    0/0 cumulative percent."""
    n = sum(counts)
    out, acc = [], 0
    for v in counts:
        acc += v
        out.append((v, None if n == 0 else 100.0 * v / n,
                    acc, None if n == 0 else 100.0 * acc / n))
    return out
