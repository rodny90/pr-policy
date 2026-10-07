"""The policy rules.

Every rule is deterministic. None of them tries to work out whether a human or
a model wrote the code — that is an arms race, and maintainers have said
repeatedly that they do not want a tool adjudicating it. These rules check
whether a submission follows the rules the project itself wrote down.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Callable

from pr_policy.config import Config, RuleConfig
from pr_policy.context import PullRequest
from pr_policy.report import Finding

RuleFn = Callable[[PullRequest, RuleConfig], Iterable[Finding]]

# "- [x] I did not use generative AI" / "* [X] ..." — a ticked markdown checkbox.
TICKED = re.compile(r"^\s*[-*]\s*\[[xX]\]\s*(?P<label>.+?)\s*$", re.MULTILINE)
UNTICKED = re.compile(r"^\s*[-*]\s*\[\s*\]\s*(?P<label>.+?)\s*$", re.MULTILINE)
# "<!-- anything -->" — the instructional comments left in an unedited template.
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def _mentions_agent(text: str, identities: Iterable[str]) -> str | None:
    lowered = text.lower()
    for identity in identities:
        if identity.lower() in lowered:
            return identity
    return None


def _strip_template_noise(body: str) -> str:
    return HTML_COMMENT.sub("", body).strip()


def check_attribution(pr: PullRequest, rule: RuleConfig) -> Iterable[Finding]:
    """Enforce the Linux kernel's AI attribution policy on commit trailers.

    Only humans can certify the Developer Certificate of Origin, so an agent
    must never add ``Signed-off-by``; tool assistance belongs in ``Assisted-by``.
    Matching is on identities the agent writes about itself, never on the code.
    """
    identities = rule.get("agent_identities", [])

    for commit in pr.commits:
        trailers = commit.trailers
        signed_off = trailers.get("signed-off-by", [])
        assisted_by = trailers.get("assisted-by", [])
        co_authored = trailers.get("co-authored-by", [])

        if rule.get("forbid_agent_sign_off"):
            for value in signed_off:
                identity = _mentions_agent(value, identities)
                if identity:
                    yield Finding(
                        rule=rule.name,
                        severity=rule.severity,
                        message=(
                            f"commit {commit.short_sha} has 'Signed-off-by: {value}', "
                            f"which names a coding agent ({identity})"
                        ),
                        hint=(
                            "Only a human can certify the DCO. Sign off as yourself and "
                            "record the tool with 'Assisted-by: <tool>:<model>'."
                        ),
                        where=commit.short_sha,
                    )

        if rule.get("prefer_assisted_by") and not assisted_by:
            for value in co_authored:
                identity = _mentions_agent(value, identities)
                if identity:
                    yield Finding(
                        rule=rule.name,
                        severity=rule.severity,
                        message=(
                            f"commit {commit.short_sha} credits a coding agent "
                            f"({identity}) with 'Co-authored-by' rather than 'Assisted-by'"
                        ),
                        hint=(
                            "Co-authorship implies authorship. Use "
                            "'Assisted-by: <tool>:<model>' to record tool assistance."
                        ),
                        where=commit.short_sha,
                    )

        if rule.get("require_signed_off") and not signed_off:
            yield Finding(
                rule=rule.name,
                severity=rule.severity,
                message=f"commit {commit.short_sha} has no 'Signed-off-by' trailer",
                hint="This project runs the DCO. Commit with 'git commit -s'.",
                where=commit.short_sha,
            )


def check_disclosure(pr: PullRequest, rule: RuleConfig) -> Iterable[Finding]:
    """Check that the project's AI-disclosure question was actually answered.

    The rule routes on disclosure and never adjudicates it: a ticked box passes,
    whichever answer it was. An untouched checkbox is the thing worth flagging.
    """
    patterns = [re.compile(p, re.IGNORECASE) for p in rule.get("checkbox_patterns", [])]
    if not patterns:
        return

    ticked = [m.group("label") for m in TICKED.finditer(pr.body)]
    unticked = [m.group("label") for m in UNTICKED.finditer(pr.body)]

    def matches(label: str) -> bool:
        return any(p.search(label) for p in patterns)

    if any(matches(label) for label in ticked):
        return

    relevant_unticked = [label for label in unticked if matches(label)]
    if relevant_unticked:
        yield Finding(
            rule=rule.name,
            severity=rule.severity,
            message="the AI-disclosure checkbox in the pull request template is not ticked",
            hint=(
                "Tick the option that applies. Either answer is accepted — "
                "the box only needs to be answered."
            ),
            where="pull request body",
        )
    else:
        yield Finding(
            rule=rule.name,
            severity=rule.severity,
            message="the pull request body carries no AI-disclosure statement",
            hint=(
                "This project asks contributors to declare whether AI tools were used. "
                "Keep that section of the pull request template and answer it."
            ),
            where="pull request body",
        )


def check_template(pr: PullRequest, rule: RuleConfig) -> Iterable[Finding]:
    """Check that the pull request was described, and the template edited."""
    stripped = _strip_template_noise(pr.body)
    minimum = int(rule.get("min_body_chars", 30))

    if len(stripped) < minimum:
        yield Finding(
            rule=rule.name,
            severity=rule.severity,
            message=(
                f"the pull request description is {len(stripped)} characters once "
                f"template boilerplate is removed (minimum {minimum})"
            ),
            hint="Describe what changes and why. Reviewers read this before the diff.",
            where="pull request body",
        )
        return

    if rule.get("forbid_unedited_comments") and HTML_COMMENT.search(pr.body):
        yield Finding(
            rule=rule.name,
            severity=rule.severity,
            message="the pull request body still contains template instruction comments",
            hint="Replace the <!-- ... --> prompts from the template with your own text.",
            where="pull request body",
        )


def check_linked_issue(pr: PullRequest, rule: RuleConfig) -> Iterable[Finding]:
    """Check that the pull request references an issue."""
    keywords = rule.get("keywords", [])
    alternatives = "|".join(re.escape(k) for k in keywords)
    pattern = re.compile(
        rf"(?:{alternatives})\s+(?:[\w.-]+/[\w.-]+)?#\d+",
        re.IGNORECASE,
    )
    if keywords and pattern.search(pr.body):
        return
    yield Finding(
        rule=rule.name,
        severity=rule.severity,
        message="the pull request body does not reference an issue",
        hint=(
            "This project asks for an issue first. Add a line such as "
            "'Closes #123' so the discussion and the change stay linked."
        ),
        where="pull request body",
    )


def check_size(pr: PullRequest, rule: RuleConfig) -> Iterable[Finding]:
    """Report pull requests large enough that review quality drops."""
    max_lines = int(rule.get("max_lines", 1000))
    max_files = int(rule.get("max_files", 100))

    if pr.total_lines > max_lines:
        yield Finding(
            rule=rule.name,
            severity=rule.severity,
            message=(
                f"this pull request changes {pr.total_lines} lines "
                f"(+{pr.additions}/-{pr.deletions}), over the {max_lines}-line guideline"
            ),
            hint="Large changes are reviewed less carefully. Consider splitting it.",
            where="diff",
        )

    if len(pr.changed_files) > max_files:
        yield Finding(
            rule=rule.name,
            severity=rule.severity,
            message=(
                f"this pull request touches {len(pr.changed_files)} files, "
                f"over the {max_files}-file guideline"
            ),
            hint="Consider splitting the change so each pull request has one subject.",
            where="diff",
        )


# Rules that read the pull request title or body. Without an event payload
# there is no body to read, so these are skipped rather than failed.
NEEDS_METADATA = frozenset({"disclosure", "template", "linked_issue"})

RULES: dict[str, RuleFn] = {
    "attribution": check_attribution,
    "disclosure": check_disclosure,
    "template": check_template,
    "linked_issue": check_linked_issue,
    "size": check_size,
}


def evaluate(pr: PullRequest, config: Config) -> tuple[list[Finding], list[str], list[str]]:
    """Run every enabled rule.

    Returns the findings, the rules that ran, and the rules that were skipped
    because the pull request's title and body were not available.
    """
    findings: list[Finding] = []
    checked: list[str] = []
    skipped: list[str] = []
    for name, run in RULES.items():
        rule = config.rules.get(name)
        if rule is None or not rule.enabled:
            continue
        if name in NEEDS_METADATA and not pr.metadata_available:
            skipped.append(name)
            continue
        checked.append(name)
        findings.extend(run(pr, rule))
    return findings, checked, skipped
