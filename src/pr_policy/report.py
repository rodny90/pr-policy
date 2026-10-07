"""Findings and the ways they get rendered.

pr-policy reports signals, not verdicts. A finding says what it saw and where;
whether that should block anything is a separate decision, made by the
``enforce`` setting rather than by the rule.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

ERROR = "error"
WARN = "warn"
INFO = "info"

RANK = {ERROR: 0, WARN: 1, INFO: 2}


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    message: str
    hint: str = ""
    where: str = ""

    def as_dict(self) -> dict:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "hint": self.hint,
            "where": self.where,
        }


@dataclass(frozen=True)
class Report:
    findings: list[Finding] = field(default_factory=list)
    enforce: bool = False
    checked: list[str] = field(default_factory=list)

    @property
    def ordered(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: (RANK.get(f.severity, 9), f.rule))

    def of_severity(self, severity: str) -> list[Finding]:
        return [f for f in self.findings if f.severity == severity]

    @property
    def errors(self) -> list[Finding]:
        return self.of_severity(ERROR)

    @property
    def clean(self) -> bool:
        return not self.findings

    @property
    def exit_code(self) -> int:
        """Non-zero only when the project asked for enforcement and something failed."""
        return 1 if self.enforce and self.errors else 0

    def counts(self) -> dict[str, int]:
        return {sev: len(self.of_severity(sev)) for sev in (ERROR, WARN, INFO)}

    def as_dict(self) -> dict:
        return {
            "enforce": self.enforce,
            "checked": self.checked,
            "counts": self.counts(),
            "exit_code": self.exit_code,
            "findings": [f.as_dict() for f in self.ordered],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.as_dict(), indent=indent)


def summarise(report: Report) -> str:
    counts = report.counts()
    parts = [f"{counts[sev]} {sev}" for sev in (ERROR, WARN, INFO) if counts[sev]]
    return ", ".join(parts) if parts else "no findings"
