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

from pr_policy.config import AI_HEADING, DISCLOSURE_CHECKBOX_PATTERNS

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
    # A second pattern the same sentence must also match. It separates a project
    # stating a requirement from one merely mentioning the subject.
    requires: re.Pattern | None = None
    # A pattern that states the requirement on its own: "use `git commit -s`" is
    # an instruction without needing "must" beside it.
    suffices: re.Pattern | None = None
    # In a pull request template, a checkbox item is itself the question put to the
    # contributor, and so is a heading that opens the section ("## Generative AI").
    # Both count without requirement wording, and a negation in a checkbox is just
    # one of the answers ("I did not use AI"). `template_pattern` widens what a
    # checkbox may mention; `heading` is what a section heading may say.
    template_question: bool = False
    template_pattern: re.Pattern | None = None
    heading: re.Pattern | None = None


# Words that make a sentence ask for something rather than describe it. There is
# deliberately no bare "always" or "welcome": "contributions are always welcome"
# invites, it does not require.
REQUIREMENT = re.compile(
    r"\b(must|required?|requires?|mandatory|please|should"
    r"|(have|has|need|needs|expected) to|all commits|every commit|every pull request)\b"
    # An instruction can also be an imperative: "Link the issue." "Disclose AI use."
    r"|^[\W_]*(open|file|create|link|reference|mention|add"
    r"|disclose|declare|state|tell|say|indicate)\b",
    re.IGNORECASE,
)

CHECKBOX_ITEM = re.compile(r"^[-*+]\s*\[[ xX]\]")
HEADING = re.compile(r"^#{1,6}\s")
# The markdown that introduces a line: "## ", "- [ ] ", "1. ".
LEADING_MARKUP = re.compile(r"^(?:#{1,6}\s+|[-*+]\s+(?:\[[ xX]\]\s*)?|\d+[.)]\s+)")

# What a prose sentence has to mention to be about AI use. This is narrower than the
# rule's own checkbox patterns (config.DISCLOSURE_CHECKBOX_PATTERNS), which must
# accept everything matched here, or init could switch the rule on from wording the
# rule then fails to recognise. tests/test_infer.py holds the two together.
AI_MENTION = re.compile(
    r"\b(generative ai|ai[-\s]generated|ai (tool|assist|help)|llm|"
    r"copilot|chatgpt|claude|codex)",
    re.IGNORECASE,
)

DETECTORS = (
    Detector(
        rule="attribution",
        option="require_signed_off",
        value=True,
        pattern=re.compile(
            r"sign(ed)?[-\s]off|\bDCO\b|developer certificate of origin|git commit -s",
            re.IGNORECASE,
        ),
        requires=REQUIREMENT,
        suffices=re.compile(r"git commit -s", re.IGNORECASE),
    ),
    Detector(
        rule="disclosure",
        option="enabled",
        value=True,
        pattern=AI_MENTION,
        requires=REQUIREMENT,
        template_question=True,
        template_pattern=re.compile("|".join(DISCLOSURE_CHECKBOX_PATTERNS), re.IGNORECASE),
        heading=re.compile(AI_HEADING, re.IGNORECASE),
    ),
    Detector(
        rule="linked_issue",
        option="enabled",
        value=True,
        pattern=re.compile(
            r"((closes|fixes|resolves)\s+#|"
            r"link(ed|s)?\s+(to\s+)?((the|an?)\s+)?(\w+\s+)?issue|"
            r"reference[sd]?\s+((the|an?)\s+)?(\w+\s+)?issue|associated issue|"
            r"open an issue (first|before)|issue (first|before))",
            re.IGNORECASE,
        ),
        requires=REQUIREMENT,
        template_question=True,
    ),
)


def _trim(line: str, limit: int = 90) -> str:
    line = LEADING_MARKUP.sub("", re.sub(r"\s+", " ", line.strip()))
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


def _matches(detector: Detector, unit: str, is_template: bool) -> bool:
    """Whether a sentence states the policy the detector looks for."""
    if is_template and detector.template_question:
        if CHECKBOX_ITEM.match(unit):
            # The answers to the question, whatever they say: "I did not use AI".
            return bool((detector.template_pattern or detector.pattern).search(unit))
        if HEADING.match(unit) and detector.heading and detector.heading.search(unit):
            return True

    if NEGATION.search(unit) or not detector.pattern.search(unit):
        return False
    if detector.suffices and detector.suffices.search(unit):
        return True
    return detector.requires is None or bool(detector.requires.search(unit))


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

        is_template = "pull_request_template" in relative.lower()

        for number, unit in units(text):
            for detector in DETECTORS:
                key = (detector.rule, detector.option)
                if key in signals or not _matches(detector, unit, is_template):
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
