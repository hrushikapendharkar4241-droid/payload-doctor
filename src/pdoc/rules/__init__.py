"""Rule registry. Each format module registers its rules with `define()`."""
from __future__ import annotations

from ..models import Finding, Rule

RULES: dict[str, Rule] = {}


def define(id: str, fmt: str, severity: str, title: str, why: str, cause: str, fix: str) -> Rule:
    if id in RULES:
        raise ValueError(f"duplicate rule id {id}")
    rule = Rule(id, fmt, severity, title, why, cause, fix)
    RULES[id] = rule
    return rule


def hit(rule_id: str, message: str, location: str | None = None) -> Finding:
    return Finding(RULES[rule_id], message, location)


def all_rules() -> list[Rule]:
    # import side effects register every rule
    from . import as2_rules, csv_rules, edifact_rules, epcis_rules, general, x12_rules  # noqa: F401

    return sorted(RULES.values(), key=lambda r: r.id)
