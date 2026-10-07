"""Derive a starting configuration from the rules a project already wrote down.

A project that asks for a DCO sign-off, or asks contributors to declare AI use,
has already made its policy decisions — in prose. This module finds those
decisions in CONTRIBUTING.md and the pull request template, and turns the
enforceable ones into configuration, quoting the line it relied on so the
maintainer can check the inference rather than trust it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

SOURCE_FILES = (
    "CONTRIBUTING.md",
    ".github/CONTRIBUTING.md",
    "docs/CONTRIBUTING.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/pull_request_template.md",
    "PULL_REQUEST_TEMPLATE.md",
    "docs/PULL_REQUEST_TEMPLATE.md",
    "AGENTS.md",
)


@dataclass(frozen=True)
class Signal:
    """One inference, with the line that justified it."""

    rule: str
    option: str
    value: Any
    source: str
    quote: str


# A line that prohibits something is not a line that requires it. "An agent must
# never add a Signed-off-by trailer" mentions sign-off while asking for the
# opposite, so lines carrying a negation are passed over. This is a heuristic,
# which is exactly why every inference is written out with the line behind it.
NEGATION = re.compile(
    r"\b(never|not|n't|without|forbid(s|den)?|prohibit(s|ed)?|avoid)\b", re.IGNORECASE
)

# Documentation is prose, so inference works over sentences rather than lines: a
# sentence is the smallest unit that carries a complete instruction, and it is
# what a negation applies to. Markdown headings and list items break a unit too.
UNIT_BREAK = re.compile(r"(?<=[.!?])\s+|\n(?=\s*(?:#|[-*+]\s|\d+[.)]\s))|\n\s*\n")


@dataclass(frozen=True)
class Detector:
    rule: str
    option: str
    value: Any
    pattern: re.Pattern
    # An optional second pattern the same sentence must also match. It separates
    # a project stating a requirement from one merely mentioning the subject.
    requires: re.Pattern | None = None


DETECTORS = (
    Detector(
        rule="attribution",
        option="require_signed_off",
        value=True,
        pattern=re.compile(
            r"sign(ed)?[-\s]off|\bDCO\b|developer certificate of origin|git commit -s",
            re.IGNORECASE,
        ),
        requires=re.compile(
            r"\b(must|require[ds]?|please|need|should|all commits|every commit|use)\b",
            re.IGNORECASE,
        ),
    ),
    Detector(
        rule="disclosure",
        option="enabled",
        value=True,
        pattern=re.compile(
            r"(generative ai|ai[-\s]generated|ai (tool|assist|help)|\bllm\b|"
            r"copilot|chatgpt|claude|codex)",
            re.IGNORECASE,
        ),
    ),
    Detector(
        rule="linked_issue",
        option="enabled",
        value=True,
        pattern=re.compile(
            r"((closes|fixes|resolves)\s+#|link(ed|s)?\s+(to\s+)?(an?\s+)?issue|"
            r"open an issue (first|before)|issue (first|before))",
            re.IGNORECASE,
        ),
    ),
)


def _trim(line: str, limit: int = 90) -> str:
    line = re.sub(r"\s+", " ", line.strip().lstrip("#-*[ ]xX").strip())
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


def units(text: str) -> list[tuple[int, str]]:
    """Split documentation into sentence-like units paired with their line number."""
    starts = [0] + [match.end() for match in UNIT_BREAK.finditer(text)]
    spans = zip(starts, starts[1:] + [len(text)])
    found = []
    for start, end in spans:
        unit = text[start:end].strip()
        if unit:
            found.append((text.count("\n", 0, start) + 1, unit))
    return found


def scan(root: Path) -> list[Signal]:
    """Find every policy signal in the project's own contributor documentation."""
    signals: dict[tuple[str, str], Signal] = {}

    for relative in SOURCE_FILES:
        path = root / relative
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for number, unit in units(text):
            if NEGATION.search(unit):
                continue
            for detector in DETECTORS:
                key = (detector.rule, detector.option)
                if key in signals or not detector.pattern.search(unit):
                    continue
                if detector.requires and not detector.requires.search(unit):
                    continue
                signals[key] = Signal(
                    rule=detector.rule,
                    option=detector.option,
                    value=detector.value,
                    source=f"{relative}:{number}",
                    quote=_trim(unit),
                )
    return list(signals.values())


# The options written out per rule, in order. Options not listed (such as the
# agent identity list) keep their defaults and stay out of the generated file.
TEMPLATE: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "attribution",
        (
            "enabled",
            "severity",
            "forbid_agent_sign_off",
            "prefer_assisted_by",
            "require_signed_off",
        ),
    ),
    ("disclosure", ("enabled", "severity")),
    ("template", ("enabled", "severity", "min_body_chars")),
    ("linked_issue", ("enabled", "severity")),
    ("size", ("enabled", "severity", "max_lines", "max_files")),
)

HEADER = """\
# pr-policy configuration, generated by `pr-policy init` on {today}.
#
# Rules switched on by inference quote the line that justified them, so you can
# check the reasoning rather than take it on trust. Everything here is a
# starting point — edit it freely.
#
# Severities are `error`, `warn` or `info`. Nothing fails a build while
# `enforce` is false: pr-policy reports signals and leaves the decision to you.
"""

NO_SIGNALS = """\
#
# Nothing in this repository's CONTRIBUTING.md or pull request template implied
# a policy beyond the defaults, so these are the defaults. If the project does
# ask for something — a DCO sign-off, an AI declaration, an issue link — write
# it down there and re-run `pr-policy init`.
"""

BODY = """\
version: 1
enforce: false

rules:
"""


def render(root: Path, signals: list[Signal], defaults: dict[str, dict[str, Any]]) -> str:
    """Render a commented YAML configuration from the defaults and the signals."""
    by_option = {(s.rule, s.option): s for s in signals}
    lines = [HEADER.format(today=date.today().isoformat())]
    if not signals:
        lines.append(NO_SIGNALS)
    lines.append(BODY)

    for rule_name, options in TEMPLATE:
        lines.append(f"  {rule_name}:")
        for option in options:
            signal = by_option.get((rule_name, option))
            value = signal.value if signal else defaults[rule_name][option]
            if signal:
                lines.append(f'    # {signal.source} — "{signal.quote}"')
            lines.append(f"    {option}: {_yaml_scalar(value)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return f'"{value}"'
