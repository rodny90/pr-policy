"""Tests for the policy rules themselves.

The rules are pure functions over a PullRequest, so these build one directly
rather than going through git.
"""

from __future__ import annotations

import pytest

from pr_policy.config import default_config
from pr_policy.context import Commit, PullRequest
from pr_policy.rules import NEEDS_METADATA, RULES, evaluate

AGENT_SIGN_OFF = "Add a thing\n\nSigned-off-by: Claude <noreply@anthropic.com>"
HUMAN_SIGN_OFF = "Add a thing\n\nSigned-off-by: A Human <human@example.com>"


def commit(message: str, sha: str = "a" * 40) -> Commit:
    return Commit(sha=sha, author_name="A Human", author_email="human@example.com", message=message)


def make_pr(messages: list[str] | None = None, **kwargs) -> PullRequest:
    # Distinct in the first 8 characters, so short shas do not collide.
    commits = [commit(m, sha=f"{i:x}" * 40) for i, m in enumerate(messages or [])]
    kwargs.setdefault("metadata_available", True)
    return PullRequest(commits=commits, **kwargs)


def run(pr: PullRequest, rule_name: str, **options):
    config = default_config()
    rule = config.rule(rule_name)
    merged = dict(rule.options)
    merged.update(options)
    from pr_policy.config import RuleConfig

    return list(
        RULES[rule_name](
            pr, RuleConfig(name=rule_name, enabled=True, severity="warn", options=merged)
        )
    )


# --- attribution -----------------------------------------------------------


def test_agent_sign_off_is_flagged() -> None:
    findings = run(make_pr([AGENT_SIGN_OFF]), "attribution")
    assert len(findings) == 1
    assert "names a coding agent" in findings[0].message
    assert "Only a human can certify the DCO" in findings[0].hint


def test_human_sign_off_is_accepted() -> None:
    assert run(make_pr([HUMAN_SIGN_OFF]), "attribution") == []


@pytest.mark.parametrize("agent", ["Claude", "GitHub Copilot", "Codex", "Cursor", "Devin"])
def test_every_known_agent_identity_is_matched(agent: str) -> None:
    message = f"Change\n\nSigned-off-by: {agent} <bot@example.com>"
    assert run(make_pr([message]), "attribution")


def test_co_authored_agent_is_steered_to_assisted_by() -> None:
    message = "Change\n\nCo-authored-by: Claude <noreply@anthropic.com>"
    findings = run(make_pr([message]), "attribution")
    assert len(findings) == 1
    assert "rather than 'Assisted-by'" in findings[0].message


def test_co_authored_agent_is_accepted_when_assisted_by_is_present() -> None:
    message = (
        "Change\n\nAssisted-by: Claude:claude-opus-5\n"
        "Co-authored-by: Claude <noreply@anthropic.com>"
    )
    assert run(make_pr([message]), "attribution") == []


def test_human_co_author_is_not_flagged() -> None:
    message = "Change\n\nCo-authored-by: Another Human <other@example.com>"
    assert run(make_pr([message]), "attribution") == []


def test_missing_sign_off_flagged_only_when_the_project_asks() -> None:
    pr = make_pr(["Change with no trailers"])
    assert run(pr, "attribution") == []
    assert run(pr, "attribution", require_signed_off=True)


def test_each_offending_commit_is_reported_separately() -> None:
    findings = run(make_pr([AGENT_SIGN_OFF, AGENT_SIGN_OFF]), "attribution")
    assert len({f.where for f in findings}) == 2


def test_forbid_agent_sign_off_can_be_turned_off() -> None:
    assert run(make_pr([AGENT_SIGN_OFF]), "attribution", forbid_agent_sign_off=False) == []


# --- disclosure ------------------------------------------------------------

TEMPLATE_BOX = (
    "## Generative AI\n\n"
    "- [ ] I did not use generative AI tools\n"
    "- [ ] I used generative AI tools, and a human reviewed the result\n"
)


def test_unticked_disclosure_box_is_flagged() -> None:
    findings = run(make_pr(body=TEMPLATE_BOX), "disclosure")
    assert len(findings) == 1
    assert "not ticked" in findings[0].message


@pytest.mark.parametrize("answer", ["did not use generative AI", "used generative AI tools"])
def test_either_answer_satisfies_the_rule(answer: str) -> None:
    assert run(make_pr(body=f"- [x] I {answer}"), "disclosure") == []


def test_uppercase_tick_is_accepted() -> None:
    assert run(make_pr(body="- [X] I did not use generative AI tools"), "disclosure") == []


def test_absent_disclosure_section_is_flagged_differently() -> None:
    findings = run(make_pr(body="Just a description."), "disclosure")
    assert "no AI-disclosure statement" in findings[0].message


# --- template --------------------------------------------------------------


def test_empty_body_is_flagged() -> None:
    assert run(make_pr(body=""), "template")


def test_body_of_only_template_comments_is_flagged() -> None:
    findings = run(make_pr(body="<!-- Describe your change here -->"), "template")
    assert "once template boilerplate is removed" in findings[0].message


def test_described_pull_request_passes() -> None:
    assert run(make_pr(body="This refactors the parser so it handles trailers."), "template") == []


def test_leftover_instruction_comments_are_flagged() -> None:
    body = "This refactors the parser so it handles trailers.\n\n<!-- Delete this line -->"
    findings = run(make_pr(body=body), "template")
    assert "template instruction comments" in findings[0].message


# --- linked issue ----------------------------------------------------------


@pytest.mark.parametrize("body", ["Closes #12", "fixes #3", "Resolves  #99", "Part of #4"])
def test_issue_references_are_accepted(body: str) -> None:
    assert run(make_pr(body=body), "linked_issue") == []


def test_cross_repository_reference_is_accepted() -> None:
    assert run(make_pr(body="Closes owner/repo#12"), "linked_issue") == []


def test_bare_issue_number_is_not_enough() -> None:
    assert run(make_pr(body="See #12 for background"), "linked_issue")


def test_missing_issue_reference_is_flagged() -> None:
    assert run(make_pr(body="A description with no issue."), "linked_issue")


# --- size ------------------------------------------------------------------


def test_large_diff_is_reported() -> None:
    findings = run(make_pr(additions=900, deletions=200), "size", max_lines=1000)
    assert "over the 1000-line guideline" in findings[0].message


def test_diff_within_the_guideline_is_silent() -> None:
    assert run(make_pr(additions=10, deletions=5), "size") == []


def test_too_many_files_is_reported() -> None:
    findings = run(make_pr(changed_files=[f"f{i}.py" for i in range(30)]), "size", max_files=10)
    assert "over the 10-file guideline" in findings[0].message


# --- evaluate --------------------------------------------------------------


def test_body_rules_are_skipped_without_metadata() -> None:
    pr = PullRequest(commits=[commit("Change")], metadata_available=False)
    _, checked, skipped = evaluate(pr, default_config())
    assert set(skipped) <= NEEDS_METADATA
    assert "template" in skipped
    assert "attribution" in checked


def test_disabled_rules_do_not_run() -> None:
    config = default_config()
    _, checked, _ = evaluate(make_pr(["Change"]), config)
    assert "linked_issue" not in checked  # off by default


def test_evaluate_collects_findings_across_rules() -> None:
    pr = make_pr([AGENT_SIGN_OFF], body="", additions=5000)
    findings, checked, _ = evaluate(pr, default_config())
    rules_hit = {f.rule for f in findings}
    assert {"attribution", "template", "size"} <= rules_hit
    assert "attribution" in checked
