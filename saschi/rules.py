"""Rulebook loader and construct map for saschi.

Loads docs/sasconversionrulebook.yaml into typed rules, keyed by rule_id,
and maps SAS constructs (statements, functions, families) to rules. The
construct map covers the gated families first (rounding, dates, missing
handling, merge, sort, character functions, arrays, formats, BY-group);
NO-DIRECT-EQUIVALENT rules route to human-review tickets.

Pure stdlib plus PyYAML. Deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

RULEBOOK_DEFAULT = Path(__file__).resolve().parent.parent / "docs" / "sasconversionrulebook.yaml"


@dataclass(frozen=True)
class Rule:
    """One rulebook entry, loaded from the shipped YAML."""

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
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RulebookError(f"cannot read rulebook: {path}") from exc
    except yaml.YAMLError as exc:
        raise RulebookError(f"rulebook is not valid YAML: {path}") from exc

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
    "arrays": "DS-016",
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
    (re.compile(r"^\s*PROC\s+SORT\b", re.I), "sort"),
    (re.compile(r"^\s*PROC\s+TRANSPOSE\b", re.I), "transpose"),
    (re.compile(r"^\s*PROC\s+FORMAT\b", re.I), "formats"),
    (re.compile(r"^\s*PROC\s+IMPORT\b", re.I), "import"),
    (re.compile(r"^\s*PROC\s+SURVEYSELECT\b", re.I), "survey-select"),
    (re.compile(r"^\s*PROC\s+SURVEYFREQ\b", re.I), "survey-freq"),
    (re.compile(r"^\s*PROC\s+SURVEYREG\b|SURVEYLOGISTIC\b|SURVEYPHREG\b", re.I), "survey-reg"),
    (re.compile(r"^\s*PROC\s+SURVEYMEANS\b", re.I), "survey-means"),
    (re.compile(r"^\s*PROC\s+GLM\b|REG\b|ANOVA\b", re.I), "stat-glm"),
    (re.compile(r"^\s*PROC\s+LOGISTIC\b", re.I), "stat-logistic"),
    (re.compile(r"^\s*PROC\s+GENMOD\b", re.I), "stat-gee"),
    (re.compile(r"^\s*PROC\s+MIXED\b|GLIMMIX\b", re.I), "stat-mixed"),
    (re.compile(r"^\s*PROC\s+PHREG\b|LIFETEST\b", re.I), "stat-survival"),
    (re.compile(r"^\s*PROC\s+PRINCOMP\b|FACTOR\b|CLUSTER\b|CORR\b", re.I), "stat-multivariate"),
    (re.compile(r"^\s*PROC\s+ARIMA\b|ESM\b|EXPAND\b", re.I), "stat-timeseries"),
    (re.compile(r"^\s*PROC\s+TTEST\b", re.I), "stat-ttest"),
    (re.compile(r"^\s*PROC\s+NPAR1WAY\b", re.I), "stat-wilcoxon"),
    (re.compile(r"^\s*PROC\s+FREQ\b", re.I), "stat-freq"),
    (re.compile(r"^\s*PROC\s+MEANS\b|SUMMARY\b|UNIVARIATE\b", re.I), "stat-means"),
    (re.compile(r"^\s*PROC\s+SQL\b", re.I), "sql-general"),
    (re.compile(r"^\s*PROC\s+DATASETS\b", re.I), "macro-autoexec"),
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
    (re.compile(r"\bROUND\s*\(", re.I), "round"),
    (re.compile(r"\bMOD\s*\(|\bINT\s*\(", re.I), "mod-int"),
    (re.compile(r"\bINTCK\s*\(|\bINTNX\s*\(", re.I), "date"),
    (re.compile(r"\bLAG\s*\(|\bDIF\s*\(", re.I), "lag-dif"),
    (re.compile(r"\bSCAN\s*\(|\bCATX\s*\(|\bSUBSTR\s*\(|\bINDEX\s*\(", re.I), "char-funcs"),
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


def route_statement(statement: str) -> tuple[str, str]:
    """Route one statement to (construct_name, rule_id).

    Unroutable statements return ("unknown", ""); the caller decides
    whether that is a ticket or a pass-through (v1: ticket).
    """
    for rx, construct in STATEMENT_ROUTER:
        if rx.search(statement):
            if construct == "sql-general":
                if INTO_MACRO_HINT.search(statement):
                    return "sql-into", CONSTRUCT_MAP["sql-into"]
                if REMERGE_HINT.search(statement):
                    return "sql-remerge", CONSTRUCT_MAP["sql-remerge"]
            rule_id = CONSTRUCT_MAP.get(construct, "")
            return construct, rule_id
    return "unknown", ""


def route_function(call: str) -> tuple[str, str]:
    """Route one function call to (construct_name, rule_id)."""
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
