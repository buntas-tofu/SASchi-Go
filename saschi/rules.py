"""Rulebook loader and construct map for saschi.

Loads docs/sasconversionrulebook.json into typed rules, keyed by rule_id,
and maps SAS constructs (statements, functions, families) to rules. The
construct map covers the gated families first (rounding, dates, missing
handling, merge, sort, character functions, arrays, formats, BY-group);
NO-DIRECT-EQUIVALENT rules route to human-review tickets.

Pure standard library. Deterministic. The rulebook ships as JSON so the tool
carries no third-party dependency to read its own guardrails.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from .parser import Kind, ParseError, tokenize

RULEBOOK_DEFAULT = Path(__file__).resolve().parent.parent / "docs" / "sasconversionrulebook.json"
if not RULEBOOK_DEFAULT.is_file():
    RULEBOOK_DEFAULT = Path(__file__).resolve().parent / "data" / "sasconversionrulebook.json"


@dataclass(frozen=True)
class Rule:
    """One rulebook entry, loaded from the shipped rulebook."""

    rule_id: str
    sas_pattern: str
    scope: str
    equivalence_class: str
    action: Optional[str] = None
    rationale: Optional[str] = None
    detection: Optional[str] = None
    rule_text: Optional[str] = None
    language_routing: Optional[str] = None
    python_target: dict[str, str] = field(default_factory=dict)
    r_target: dict[str, str] = field(default_factory=dict)
    required_settings: list[str] = field(default_factory=list)
    forbidden_patterns: list[str] = field(default_factory=list)
    silent_difference_checks: list[str] = field(default_factory=list)
    validation_test: Optional[str] = None
    confidence: Optional[str] = None
    sources: list[str] = field(default_factory=list)
    alternates_when: Optional[str] = None

    @property
    def is_ticket(self) -> bool:
        """True when this rule forbids direct code generation."""
        return self.equivalence_class.startswith("NO-DIRECT-EQUIVALENT")

    @property
    def is_r_required(self) -> bool:
        return self.language_routing == "R-required"


class RulebookError(ValueError):
    """Raised when the shipped rulebook is malformed."""


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _as_dict(value: Any) -> dict[str, str]:
    if not value:
        return {}
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items()}


def _parse_rule(raw: dict[str, Any]) -> Rule:
    rule_id = raw.get("rule_id")
    if not rule_id:
        raise RulebookError("rulebook entry missing rule_id")
    sas_pattern = raw.get("sas_pattern")
    scope = raw.get("scope")
    eq_class = raw.get("equivalence_class")
    if not sas_pattern or not scope or not eq_class:
        raise RulebookError(f"rule {rule_id} missing sas_pattern, scope, or equivalence_class")
    return Rule(
        rule_id=str(rule_id),
        sas_pattern=str(sas_pattern),
        scope=str(scope),
        equivalence_class=str(eq_class),
        action=str(raw["action"]) if raw.get("action") else None,
        rationale=str(raw["rationale"]) if raw.get("rationale") else None,
        detection=str(raw["detection"]) if raw.get("detection") else None,
        rule_text=str(raw["rule"]) if raw.get("rule") else None,
        language_routing=str(raw["language_routing"]) if raw.get("language_routing") else None,
        python_target=_as_dict(raw.get("python_target")),
        r_target=_as_dict(raw.get("r_target")),
        required_settings=_as_list(raw.get("required_settings")),
        forbidden_patterns=_as_list(raw.get("forbidden_patterns")),
        silent_difference_checks=_as_list(raw.get("silent_difference_checks")),
        validation_test=str(raw["validation_test"]) if raw.get("validation_test") else None,
        confidence=str(raw["confidence"]) if raw.get("confidence") else None,
        sources=_as_list(raw.get("sources")),
        alternates_when=str(raw["alternates_when"]) if raw.get("alternates_when") else None,
    )


def load_rulebook(path: Optional[Path] = None) -> dict[str, Rule]:
    """Load and validate the rulebook. Returns {rule_id: Rule}."""
    path = Path(path) if path else RULEBOOK_DEFAULT
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RulebookError(f"cannot read rulebook: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RulebookError(f"rulebook is not valid JSON: {path}") from exc

    if not isinstance(raw, dict) or "rules" not in raw:
        raise RulebookError("rulebook missing top-level 'rules' list")

    rules: dict[str, Rule] = {}
    for entry in raw["rules"]:
        rule = _parse_rule(entry)
        if rule.rule_id in rules:
            raise RulebookError(f"duplicate rule_id: {rule.rule_id}")
        rules[rule.rule_id] = rule
    return rules


# ---------------------------------------------------------------------------
# Construct map: canonical construct name -> rule_id.
# Gated families first, per the frontier plan (rounding, dates, missing
# handling, merge, sort, character functions, arrays, formats, BY-group),
# then the rest of the data-step surface, then families that route to
# tickets until their tracks land.
# ---------------------------------------------------------------------------

CONSTRUCT_MAP: dict[str, str] = {
    "numeric-value": "DS-084",
    "formatted-groups": "DS-085",
    "groupformat-input": "DS-086",
    "postal-format": "DS-092",
    "postal-library": "DS-093",
    "postal-cmplib": "DS-093",
    "postal-input": "DS-094",
    "postal-sort": "DS-095",
    "postal-report": "ST-030",
    "postal-local-call": "DS-093",
    "week-library": "DS-089",
    "week-cmplib": "DS-089",
    "week-format": "DS-090",
    "week-format-callback": "DS-090",
    "week-input": "DS-091",
    "week-report": "ST-029",
    "number-picture-input": "DS-088",
    "number-picture": "DS-087",
    "number-picture-report": "ST-028",
    "group-detail-report": "ST-027",
    "date-picture": "DS-082",
    "picture-date-input": "DS-083",
    "picture-date-print": "ST-026",
    "date-input": "DS-080",
    "nested-date-format": "DS-081",
    "date-print": "ST-025",
    "directed-sort": "DS-073",
    "descriptor-sort-all": "DS-074",
    "sort-input-keep": "DS-075",
    "sort-input-drop": "DS-078",
    "sort-directed-projection": "DS-079",
    "bitwise-output": "DS-070",
    "numeric-invalue": "DS-071",
    "formatted-input": "DS-072",
    "labelled-print": "ST-021",
    "default-means": "ST-022",
    "informat-title": "ST-023",
    # Gated data-step families (fixture gates exist or land with Track B/C).
    "round": "DS-012",
    "mod-int": "DS-013",
    "sigfig": "DS-020",
    "date": "DS-011",
    "missing": "DS-019",
    "merge": "DS-002",
    "merge-many-to-many": "DS-003",
    "sort": "DS-008",
    "char-funcs": "DS-015",
    "count": "DS-022",
    "put-literal": "DS-023",
    "put-character-list": "DS-024",
    "put-mixed-numeric": "DS-042",
    "trim-strip": "DS-043",
    "case-search": "DS-096",
    "word-functions": "DS-097",
    "character-rewriting": "DS-098",
    "missing-summaries": "DS-099",
    "numeric-helpers": "DS-100",
    "calendar-intervals": "DS-101",
    "whitespace-alignment": "DS-102",
    "cat-functions": "DS-103",
    "character-validation": "DS-104",
    "search-extraction": "DS-105",
    "row-statistics": "DS-106",
    "datetime-components": "DS-107",
    "function-consumers": "DS-108",
    "selection-consumers": "DS-115",
    "where-composition": "DS-122",
    "subsetting-if": "DS-121",
    "selector-expressions": "DS-120",
    "boolean-conditions": "DS-119",
    "comparisons-and-truth": "DS-118",
    "numeric-expressions": "DS-117",
    "character-expressions": "DS-116",
    'calendar-constructors': 'DS-114',
    'zero-fuzz-numeric': 'DS-113',
    'ranks-and-sums-of-squares': 'DS-112',
    "selection-and-lookup": "DS-111",
    "ascii-positions": "DS-110",
    "text-and-quoting": "DS-109",
    "input-list": "DS-044",
    "multiplication": "DS-045",
    "put-numeric-discovery": "DS-046",
    "projection": "DS-047",
    "projection-options": "DS-048",
    "binary64": "DS-049",
    "elementary-functions": "DS-050",
    "fractional-put": "DS-051",
    "numeric-projection": "DS-052",
    "numeric-set": "DS-053",
    "pipeline-input": "DS-054",
    "pipeline-arrays": "DS-055",
    "pipeline-loops": "DS-056",
    "numeric-pipeline": "DS-057",
    "inline-csv": "DS-058",
    "input-ranges": "DS-059",
    "grouped-do": "DS-060",
    "loop-transfer": "DS-061",
    "numeric-ranges": "DS-062",
    "csv-export": "DS-063",
    "scalar-jump": "DS-064",
    "scalar-link": "DS-065",
    "numeric-sqrt": "DS-066",
    "numeric-log": "DS-067",
    "rounded-sum": "DS-068",
    "character-input": "DS-069",
    "mixed-print": "ST-019",
    "logical-title": "ST-020",
    "proc-means": "ST-017",
    "proc-print": "ST-018",
    "put-all": "DS-025",
    "do-counted": "DS-026",
    "do-if": "DS-031",
    "bitwise": "DS-032",
    "calendar": "DS-033",
    "division": "DS-036",
    "int": "DS-037",
    "do-while": "DS-038",
    "sum-statement": "DS-034",
    "do-until": "DS-035",
    "put-numeric-list": "DS-027",
    "length-reverse": "DS-028",
    "length-list": "DS-028",

    "concat-catx": "DS-029",
    "substr": "DS-030",
    "arrays": "DS-016",
    "numeric-arrays": "DS-039",
    "do-over": "DS-040",
    "do-counted-bounded": "DS-041",
    "formats": "DS-010",
    "by-group": "DS-006",
    # Rest of the data-step surface.
    "set": "DS-001",
    "update": "DS-004",
    "if-then-else": "DS-005",
    "lag-dif": "DS-007",
    "transpose": "DS-009",
    "hash": "DS-017",
    "sas7bdat": "DS-018",
    "import": "DS-021",
    "sum-func": "DS-014",
    # SQL family (tickets in v1; gated later).
    "sql-general": "SQL-001",
    "sql-create": "SQL-004",
    "sql-remerge": "SQL-002",
    "sql-into": "SQL-003",
    # Stat-proc family (tickets until Track B gates them).
    "stat-means": "ST-001",
    "stat-quantiles": "ST-002",
    "stat-chisq": "ST-003",
    "stat-cmh": "ST-004",
    "stat-ttest": "ST-005",
    "stat-wilcoxon": "ST-006",
    "stat-glm": "ST-007",
    "stat-logistic": "ST-008",
    "stat-gee": "ST-009",
    "stat-mixed": "ST-010",
    "stat-survival": "ST-011",
    "stat-multivariate": "ST-012",
    "stat-timeseries": "ST-013",
    "stat-fisher": "ST-014",
    "stat-freq": "ST-015",
    # Survey family (R-required; tickets until gated).
    "survey-means": "SV-001",
    "survey-domain": "SV-002",
    "survey-repweights": "SV-003",
    "survey-freq": "SV-004",
    "survey-reg": "SV-005",
    "survey-select": "SV-006",
    # Macro family (tickets until Track C gates them).
    "macro-let": "MC-001",
    "macro-def": "MC-002",
    "macro-do": "MC-003",
    "macro-execute": "MC-004",
    "macro-include": "MC-005",
    "macro-systask": "MC-006",
    "macro-ods": "MC-007",
    "macro-syserr": "MC-008",
    "macro-autoexec": "MC-009",
}

# Statement-level routing: statement-start regex -> construct name.
# Order matters: longest/most specific first.
STATEMENT_ROUTER: list[tuple[re.Pattern, str]] = [
    (re.compile(r'^\s*PROC\s+MEANS\s+DATA\s*=\s*[A-Za-z_][A-Za-z0-9_]{0,31}\s+NOPRINT\s+VARDEF\s*=\s*DF\s*;?\s*$', re.I | re.ASCII), 'proc-means'),
    (re.compile(r'^\s*PROC\s+PRINT\s+DATA\s*=\s*[A-Za-z_][A-Za-z0-9_]{0,31}\s+NOOBS\s*;?\s*$', re.I | re.ASCII), 'proc-print'),
    (re.compile(r'^\s*FILE\b(?!\s*=)', re.I | re.ASCII), 'csv-export'),
    (re.compile(r'^\s*(?:PUT\s+|[A-Za-z_][A-Za-z0-9_]{0,31}\s*=\s*SUM\s*\(\s*OF\s+)[A-Za-z_][A-Za-z0-9_]*[0-9]\s*-\s*[A-Za-z_][A-Za-z0-9_]*[0-9](?=\s|;|\)|$)', re.I | re.ASCII), 'numeric-ranges'),
    (re.compile(r'^\s*INFILE\b(?!\s*=)', re.I), 'inline-csv'),
    (re.compile(r'^\s*INPUT\b(?!\s*=).*?[A-Za-z_][A-Za-z0-9_]*[0-9]\s*-\s*[A-Za-z_][A-Za-z0-9_]*[0-9](?=\s|;|$)', re.I | re.ASCII | re.S), 'input-ranges'),
    (re.compile(r'^\s*(?:INPUT\b(?!\s*=)|(?:CARDS|DATALINES)\s*$)', re.I), 'input-list'),
    (re.compile(r'^\s*DO\s+OVER\b', re.I), 'do-over'),
    (re.compile(r'^\s*DO\s+WHILE\b', re.I), 'do-while'),
    (re.compile(r'^\s*DO\s+UNTIL\b', re.I), 'do-until'),
    (re.compile(r'^\s*[A-Za-z_][A-Za-z0-9_]{0,31}\s*\+(?!=)', re.I), 'sum-statement'),
    (re.compile(r"^\s*PROC\s+SORT\b", re.I), "sort"),
    (re.compile(r"^\s*PROC\s+TRANSPOSE\b", re.I), "transpose"),
    (re.compile(r"^\s*PROC\s+FORMAT\b", re.I), "formats"),
    (re.compile(r"^\s*PROC\s+IMPORT\b", re.I), "import"),
    (re.compile(r"^\s*PROC\s+SURVEYSELECT\b", re.I), "survey-select"),
    (re.compile(r"^\s*PROC\s+SURVEYFREQ\b", re.I), "survey-freq"),
    (re.compile(r"^\s*PROC\s+(?:SURVEYREG|SURVEYLOGISTIC|SURVEYPHREG)\b", re.I), "survey-reg"),
    (re.compile(r"^\s*PROC\s+SURVEYMEANS\b", re.I), "survey-means"),
    (re.compile(r"^\s*PROC\s+(?:GLM|REG|ANOVA)\b", re.I), "stat-glm"),
    (re.compile(r"^\s*PROC\s+LOGISTIC\b", re.I), "stat-logistic"),
    (re.compile(r"^\s*PROC\s+GENMOD\b", re.I), "stat-gee"),
    (re.compile(r"^\s*PROC\s+(?:MIXED|GLIMMIX)\b", re.I), "stat-mixed"),
    (re.compile(r"^\s*PROC\s+(?:PHREG|LIFETEST)\b", re.I), "stat-survival"),
    (re.compile(r"^\s*PROC\s+(?:PRINCOMP|FACTOR|CLUSTER|CORR)\b", re.I), "stat-multivariate"),
    (re.compile(r"^\s*PROC\s+(?:ARIMA|ESM|EXPAND)\b", re.I), "stat-timeseries"),
    (re.compile(r"^\s*PROC\s+TTEST\b", re.I), "stat-ttest"),
    (re.compile(r"^\s*PROC\s+NPAR1WAY\b", re.I), "stat-wilcoxon"),
    (re.compile(r"^\s*PROC\s+FREQ\b", re.I), "stat-freq"),
    (re.compile(r"^\s*PROC\s+(?:MEANS|SUMMARY|UNIVARIATE)\b", re.I), "stat-means"),
    (re.compile(r"^\s*PROC\s+SQL\b", re.I), "sql-general"),
    (re.compile(r"^\s*PROC\s+DATASETS\b", re.I), "macro-autoexec"),
    (re.compile(r"^\s*LENGTH\b(?!\s*=)", re.I), "length-reverse"),
    (re.compile(r'^\s*(?:[A-Za-z_][A-Za-z0-9_]{0,31}\s*:|(?:(?:IF\b.+\bTHEN|ELSE)\s+)?(?:GO\s*TO\s+[A-Za-z_][A-Za-z0-9_]{0,31}|STOP)\s*;?\s*$)', re.I | re.ASCII), 'scalar-jump'),
    (re.compile(r'^\s*(?:(?:IF\b.+\bTHEN|ELSE)\s+)?(?:LINK\s+[A-Za-z_][A-Za-z0-9_]{0,31}|RETURN)\s*;?\s*$', re.I | re.ASCII), 'scalar-link'),
    (re.compile(r'^\s*(?:DO|(?:IF\b.+\bTHEN|ELSE)\s+DO)\s*;?\s*$', re.I | re.ASCII), 'grouped-do'),
    (re.compile(r'^\s*(?:(?:IF\b.+\bTHEN)\s+)?(?:LEAVE|CONTINUE)\s*;?\s*$', re.I | re.ASCII), 'loop-transfer'),
    (re.compile(r"^\s*DO\b(?!\s*=)", re.I), "do-counted"),
    (re.compile(r"^\s*(?:IF|ELSE)\b(?!\s*=)", re.I), "do-if"),
    (re.compile(r"^\s*UPDATE\b", re.I), "update"),
    (re.compile(r"^\s*MERGE\b", re.I), "merge"),
    (re.compile(r"^\s*SET\b", re.I), "set"),
    (re.compile(r"^\s*DATA\b", re.I), "data-step"),
    (re.compile(r"^\s*%MACRO\b", re.I), "macro-def"),
    (re.compile(r"^\s*%LET\b", re.I), "macro-let"),
    (re.compile(r"^\s*%DO\b", re.I), "macro-do"),
    (re.compile(r"^\s*%INCLUDE\b", re.I), "macro-include"),
    (re.compile(r"^\s*SYSTASK\b", re.I), "macro-systask"),
    (re.compile(r"^\s*ODS\b", re.I), "macro-ods"),
]

# Function-level routing: function call regex -> construct name.
FUNCTION_ROUTER: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\b(?:HMS|YYQ|DATEJUL|JULDATE7)\s*\(',re.I),'calendar-constructors'),
    (re.compile(r'\b(?:CEILZ|FLOORZ|INTZ|ROUNDZ|MODZ)\s*\(',re.I),'zero-fuzz-numeric'),
    (re.compile(r'\b(?:LARGEST|SMALLEST|CSS|USS)\s*\(',re.I),'ranks-and-sums-of-squares'),
    (re.compile(r'\b(?:IFN|IFC|CHOOSEN|CHOOSEC|WHICHN|WHICHC)\s*\(',re.I),'selection-and-lookup'),
    (re.compile(r'\b(?:ANYLOWER|ANYUPPER|ANYPUNCT|ANYXDIGIT|NOTALPHA|NOTALNUM|NOTSPACE)\s*\(',re.I),'ascii-positions'),
    (re.compile(r'\b(?:PROPCASE|QUOTE|DEQUOTE|COUNTC|TRANSTRN)\s*\(',re.I),'text-and-quoting'),
    (re.compile(r'\b(?:VERIFY|ANYALPHA|ANYDIGIT|ANYALNUM|ANYSPACE|NOTDIGIT)\s*\(',re.I),'character-validation'),
    (re.compile(r'\b(?:FINDC|FINDW|INDEXC|INDEXW|SUBSTRN)\s*\(',re.I),'search-extraction'),
    (re.compile(r'\b(?:MEDIAN|RANGE|VAR|STD)\s*\(',re.I),'row-statistics'),
    (re.compile(r'\b(?:QTR|DHMS|DATEPART|TIMEPART|HOUR|MINUTE|SECOND)\s*\(',re.I),'datetime-components'),
    (re.compile(r'\b(?:CAT|CATS|CATT)\s*\(',re.I),'cat-functions'),
    (re.compile(r'\b(?:LEFT|RIGHT|COMPBL|TRIMN)\s*\(',re.I),'whitespace-alignment'),
    (re.compile(r'\b(?:YEAR|MONTH|DAY|INTCK|INTNX)\s*\(',re.I),'calendar-intervals'),
    (re.compile(r'\b(?:ABS|SIGN|CEIL|FLOOR)\s*\(',re.I),'numeric-helpers'),
    (re.compile(r'\b(?:MISSING|N|NMISS|CMISS|COALESCE|COALESCEC|MEAN)\s*\(',re.I),'missing-summaries'),
    (re.compile(r'\b(?:COMPRESS|TRANSLATE|TRANWRD)\s*\(',re.I),'character-rewriting'),
    (re.compile(r'\b(?:SCAN|COUNTW)\s*\(',re.I),'word-functions'),
    (re.compile(r'\b(?:UPCASE|LOWCASE|INDEX|FIND)\s*\(',re.I),'case-search'),
    (re.compile(r'\bINT\s*\(', re.I), 'int'),
    (re.compile(r"\b(?:MDY|WEEKDAY)\s*\(", re.I), "calendar"),
    (re.compile(r"\b(?:BAND|BOR|BXOR|BNOT|BLSHIFT|BRSHIFT)\s*\(", re.I), "bitwise"),
    (re.compile(r"\bCOUNT\s*\(", re.I), "count"),
    (re.compile(r"\bROUND\s*\(", re.I), "round"),
    (re.compile(r"\bMOD\s*\(|\bINT\s*\(", re.I), "mod-int"),
    (re.compile(r"\bINTCK\s*\(|\bINTNX\s*\(", re.I), "date"),
    (re.compile(r"\b(?:LAG|DIF)[0-9]*\s*\(", re.I), "lag-dif"),
    (re.compile(r"\bREVERSE\s*\(", re.I), "length-reverse"),
    (re.compile(r"\b(?:TRIM|STRIP)\s*\(", re.I), "trim-strip"),
    (re.compile(r"\bSUBSTR\s*\(", re.I), "substr"),
    (re.compile(r"\bSCAN\s*\(|\bCATX\s*\(|\bINDEX\s*\(", re.I), "char-funcs"),
    (re.compile(r"\bTRANWRD\s*\(|\bCOMPRESS\s*\(|\bPUT\s*\(|\bINPUT\s*\(", re.I), "char-funcs"),
    (re.compile(r"\bSUM\s*\(", re.I), "sum-func"),
]

# MERGE routing doctrine: many-to-many (DS-003) is a DATA property, not a
# statement property. The rulebook's detection is a per-key group-size
# cross-tab of both inputs, which only exists at runtime. Statement routing
# therefore always lands MERGE+BY on DS-002 (1:1 / 1:many); the emitted code
# carries the group-size check and raises the DS-003 human-review ticket when
# it fires. Do not route on statement shape.
MERGE_MANY_TO_MANY_HINT = re.compile(r"\bMERGE\b[\s\S]*?\bBY\b", re.I)
REMERGE_HINT = re.compile(r"\bSELECT\b[\s\S]*?(AVG|SUM|MEAN|MAX|MIN)\s*\([\s\S]*?\bFROM\b", re.I)
INTO_MACRO_HINT = re.compile(r"\bINTO\s*:", re.I)


def route_statement(statement: str, context: str | None = None) -> tuple[str, str]:
    """Route one statement to (construct_name, rule_id).

    Unroutable statements return ("unknown", ""); the caller decides
    whether that is a ticket or a pass-through (v1: ticket).
    """
    # Only recognized source headers establish these contexts. No Plan data
    # or global VAR/OUTPUT route can manufacture a procedure classification.
    if context in ('proc-means', 'proc-print'):
        text = statement.strip().removesuffix(';').strip()
        name = r'[A-Za-z_][A-Za-z0-9_]{0,31}'
        if re.fullmatch(r'run', text, re.I | re.ASCII):
            return context, CONSTRUCT_MAP[context]
        if context == 'proc-means':
            if re.fullmatch(r'(?:by|var)\s+' + name, text, re.I | re.ASCII):
                return context, CONSTRUCT_MAP[context]
            output = re.fullmatch(r'output\s+out\s*=\s*' + name + r'\s+(.+)\s*/\s*noinherit', text, re.I | re.ASCII)
            if output:
                pattern = r'(n|nmiss|mean|var)\s*=\s*' + name
                statistics = re.findall(pattern, output[1], re.I | re.ASCII)
                if (len(statistics) == 4 and set(map(str.lower, statistics)) == {'n','nmiss','mean','var'}
                        and not re.sub(pattern, '', output[1], flags=re.I | re.ASCII).strip()):
                    return context, CONSTRUCT_MAP[context]
        elif re.fullmatch(r'var\s+' + name + r'(?:\s+' + name + r'){0,31}', text, re.I | re.ASCII):
            return context, CONSTRUCT_MAP[context]
    # SQL clauses arrive separately after statement splitting.
    if context == "sql" and re.match(r"^\s*(select|create|insert|update|delete)\b", statement, re.I):
        if INTO_MACRO_HINT.search(statement):
            return "sql-into", CONSTRUCT_MAP["sql-into"]
        return "sql-general", CONSTRUCT_MAP["sql-general"]
    if re.match(r'^\s*put\b', statement, re.I):
        if re.fullmatch(r'\s*put\s+_all_\s*;?\s*', statement, re.I):
            return 'put-all', CONSTRUCT_MAP['put-all']
        try:
            items = tokenize(statement.strip().removesuffix(';'))[1:]
        except ParseError:
            items = []
        if items and all(item.kind == Kind.STRING for item in items):
            return 'put-literal', CONSTRUCT_MAP['put-literal']
        if items and all(item.kind == Kind.STRING or item.kind == Kind.WORD and
                         re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,31}', item.text) for item in items):
            return 'put-character-list', CONSTRUCT_MAP['put-character-list']
    for rx, construct in STATEMENT_ROUTER:
        if context == "opaque" and construct in ("proc-means", "proc-print"):
            continue
        if rx.search(statement):
            if construct == "sql-general":
                if INTO_MACRO_HINT.search(statement):
                    return "sql-into", CONSTRUCT_MAP["sql-into"]
                if REMERGE_HINT.search(statement):
                    return "sql-remerge", CONSTRUCT_MAP["sql-remerge"]
            rule_id = CONSTRUCT_MAP.get(construct, "")
            return construct, rule_id
    return "unknown", ""


def character_report_routes(source, statements):
    """Classify validated source spans, independently of the compiled Plan.

    Source syntax validators are shared with compilation. Independent hand/R
    lexers provide the separate whole-program statement-accounting cross-check.
    Indices keep distinct statements on the same physical line distinct.
    """
    from .postal_function import source_steps as postal_steps
    _, _, postal_routes, postal_selected = postal_steps(source, statements)
    if postal_selected:
        return postal_routes
    from .week_callbacks import source_steps as week_steps
    _, _, week_routes, week_selected = week_steps(source, statements)
    if week_selected:
        return week_routes
    from .numeric_pictures import source_steps as number_steps
    _, _, number_routes, number_selected = number_steps(source, statements)
    if number_selected:
        return number_routes
    from .groupformat import source_steps as groupformat_steps
    _, _, groupformat_routes, groupformat_selected = groupformat_steps(source, statements)
    if groupformat_selected:
        return groupformat_routes
    from .picture_dates import source_steps as picture_steps
    _, _, picture_routes, picture_selected = picture_steps(source, statements)
    if picture_selected:
        return picture_routes
    from .date_program import source_steps as date_steps
    _, _, date_routes, date_selected = date_steps(source, statements)
    if date_selected:
        return date_routes
    from .sort_composition import source_steps as composition_steps
    _, _, composition_routes, composition_selected = composition_steps(source, statements)
    if composition_selected:
        return composition_routes
    from .sort_duplicates import source_steps as duplicate_steps
    _, _, duplicate_routes, duplicate_selected = duplicate_steps(source, statements)
    if duplicate_selected:
        return duplicate_routes
    from .sort_projection import source_steps as projection_steps
    _, _, projection_routes, projection_selected = projection_steps(source, statements)
    if projection_selected:
        return projection_routes
    from .sort_options import source_steps as sort_steps
    _, _, sort_routes, sort_selected = sort_steps(source, statements)
    if sort_selected:
        return sort_routes
    from .formatted_program import source_steps
    _, _, formatted_routes, selected = source_steps(source, statements)
    if selected:
        return formatted_routes
    from .character_input import _parse_block
    from .mixed_reports import parse_title, parse_print
    routes = {}
    position = 0
    while position < len(statements):
        statement = statements[position]
        if (any(token.kind is Kind.DATA for token in statement.tokens)
                or re.match(r'^data\s', statement.text, re.I | re.ASCII) is None):
            position += 1
            continue
        end = position + 1
        while end < len(statements):
            current = statements[end]
            if not any(token.kind is Kind.DATA for token in current.tokens):
                if current.text.lower() == 'run':
                    end += 1
                    break
                if re.match(r'^(?:data|proc)(?:\s|$)', current.text, re.I | re.ASCII):
                    break
            end += 1
        try:
            _parse_block(statements[position:end], source)
        except (ValueError, TypeError, KeyError):
            pass
        else:
            for index in range(position,end):
                if not any(token.kind is Kind.DATA for token in statements[index].tokens):
                    routes[index] = ('character-input', CONSTRUCT_MAP['character-input'])
        position = end
    if not routes:
        return routes
    position, active = 0, False
    while position < len(statements):
        statement = statements[position]
        if any(token.kind is Kind.DATA for token in statement.tokens):
            position += 1
            continue
        text = statement.text
        try:
            if not active and re.match(r'^title(?:\s|$)', text, re.I | re.ASCII):
                parse_title(statement)
                routes[position] = ('logical-title', CONSTRUCT_MAP['logical-title'])
            elif not active and re.match(r'^proc\s+print\b', text, re.I | re.ASCII):
                parse_print(statements[position:position+2])
                for index in (position,position+1):
                    routes[index] = ('mixed-print', CONSTRUCT_MAP['mixed-print'])
                position += 2
                continue
        except (ValueError, TypeError, KeyError):
            pass
        if re.match(r'^(?:data|proc)(?:\s|$)', text, re.I | re.ASCII):
            active = True
        if text.lower() in ('run','quit'):
            active = False
        position += 1
    return routes


def route_function(call: str) -> tuple[str, str]:
    """Route one function call to (construct_name, rule_id)."""
    # Function names inside literals are data, not calls.
    call = re.sub(r"\"(?:\"\"|[^\"])*\"|'(?:''|[^'])*'", " ", call)
    for rx, construct in FUNCTION_ROUTER:
        if rx.search(call):
            rule_id = CONSTRUCT_MAP.get(construct, "")
            return construct, rule_id
    return "unknown", ""


def family_counts(rules: dict[str, Rule]) -> dict[str, int]:
    """Count rules per family prefix (DS, SQL, ST, SV, MC, MX)."""
    counts: dict[str, int] = {}
    for rule_id in rules:
        prefix = rule_id.split("-", 1)[0]
        counts[prefix] = counts.get(prefix, 0) + 1
    return counts
