"""Core data types: rules, findings and check results."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

SEVERITIES = ("error", "warning", "info")


@dataclass(frozen=True)
class Rule:
    """A diagnostic rule. The why/cause/fix text is what a support engineer tells the customer."""

    id: str
    fmt: str
    severity: str
    title: str
    why: str
    cause: str
    fix: str


@dataclass
class Finding:
    rule: Rule
    message: str
    location: Optional[str] = None

    @property
    def severity(self) -> str:
        return self.rule.severity

    def to_dict(self) -> dict:
        return {
            "rule": self.rule.id,
            "severity": self.rule.severity,
            "title": self.rule.title,
            "message": self.message,
            "location": self.location,
            "why": self.rule.why,
            "likely_cause": self.rule.cause,
            "fix": self.rule.fix,
        }


@dataclass
class CheckResult:
    path: str
    fmt: str
    summary: str = ""
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")

    @property
    def exit_code(self) -> int:
        """0 = clean, 1 = at least one error, 2 = warnings only."""
        if self.errors:
            return 1
        if self.warnings:
            return 2
        return 0

    def to_dict(self) -> dict:
        return {
            "file": self.path,
            "format": self.fmt,
            "summary": self.summary,
            "errors": self.errors,
            "warnings": self.warnings,
            "exit_code": self.exit_code,
            "findings": [f.to_dict() for f in self.findings],
        }
