"""Tests for inferring a configuration from a project's own documentation."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from pr_policy.config import DEFAULTS, load_config
from pr_policy.infer import render, scan

DCO_CONTRIBUTING = """\
# Contributing

Please open an issue first so we can agree on the approach.

All commits must carry a sign-off under the DCO: use `git commit -s`.
"""

AI_TEMPLATE = """\
## Description

<!-- What changes and why? -->

## Generative AI

- [ ] I did not use generative AI tools
- [ ] I used generative AI tools, and a human reviewed the result
"""


def signals_for(root: Path) -> dict[tuple[str, str], object]:
    return {(s.rule, s.option): s for s in scan(root)}


def test_dco_wording_enables_sign_off(tmp_path: Path) -> None:
    (tmp_path / "CONTRIBUTING.md").write_text(DCO_CONTRIBUTING)
    signal = signals_for(tmp_path)[("attribution", "require_signed_off")]
    assert signal.value is True
    assert signal.source.startswith("CONTRIBUTING.md:")


def test_issue_first_wording_enables_the_linked_issue_rule(tmp_path: Path) -> None:
    (tmp_path / "CONTRIBUTING.md").write_text(DCO_CONTRIBUTING)
    assert signals_for(tmp_path)[("linked_issue", "enabled")].value is True


def test_ai_section_in_the_template_enables_disclosure(tmp_path: Path) -> None:
    target = tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md"
    target.parent.mkdir()
    target.write_text(AI_TEMPLATE)
    signal = signals_for(tmp_path)[("disclosure", "enabled")]
    assert signal.value is True
    assert ".github/PULL_REQUEST_TEMPLATE.md" in signal.source


def test_signals_quote_the_line_they_relied_on(tmp_path: Path) -> None:
    (tmp_path / "CONTRIBUTING.md").write_text(DCO_CONTRIBUTING)
    signal = signals_for(tmp_path)[("attribution", "require_signed_off")]
    assert "DCO" in signal.quote


def test_a_silent_project_yields_no_signals(tmp_path: Path) -> None:
    (tmp_path / "CONTRIBUTING.md").write_text("# Contributing\n\nBe kind.\n")
    assert scan(tmp_path) == []


def test_scan_ignores_a_repository_with_no_documentation(tmp_path: Path) -> None:
    assert scan(tmp_path) == []


def test_docs_and_dot_github_locations_are_searched(tmp_path: Path) -> None:
    target = tmp_path / "docs" / "CONTRIBUTING.md"
    target.parent.mkdir()
    target.write_text(DCO_CONTRIBUTING)
    assert ("attribution", "require_signed_off") in signals_for(tmp_path)


def test_first_occurrence_wins(tmp_path: Path) -> None:
    (tmp_path / "CONTRIBUTING.md").write_text(DCO_CONTRIBUTING)
    (tmp_path / "AGENTS.md").write_text("Use the DCO.\n")
    signal = signals_for(tmp_path)[("attribution", "require_signed_off")]
    assert signal.source.startswith("CONTRIBUTING.md:")


def test_rendered_config_is_valid_yaml(tmp_path: Path) -> None:
    (tmp_path / "CONTRIBUTING.md").write_text(DCO_CONTRIBUTING)
    parsed = yaml.safe_load(render(tmp_path, scan(tmp_path), DEFAULTS))
    assert parsed["version"] == 1
    assert parsed["rules"]["attribution"]["require_signed_off"] is True


def test_rendered_config_round_trips_through_the_loader(tmp_path: Path) -> None:
    (tmp_path / "CONTRIBUTING.md").write_text(DCO_CONTRIBUTING)
    target = tmp_path / ".github" / "pr-policy.yml"
    target.parent.mkdir()
    target.write_text(render(tmp_path, scan(tmp_path), DEFAULTS), encoding="utf-8")

    config = load_config(tmp_path)
    assert config.rule("attribution").get("require_signed_off") is True
    assert config.rule("linked_issue").enabled is True


def test_rendered_config_cites_its_evidence_in_comments(tmp_path: Path) -> None:
    (tmp_path / "CONTRIBUTING.md").write_text(DCO_CONTRIBUTING)
    text = render(tmp_path, scan(tmp_path), DEFAULTS)
    assert "# CONTRIBUTING.md:5" in text
    assert "git commit -s" in text


def test_rendered_config_defaults_to_reporting_only(tmp_path: Path) -> None:
    assert yaml.safe_load(render(tmp_path, [], DEFAULTS))["enforce"] is False


def test_silent_project_gets_an_explanatory_note(tmp_path: Path) -> None:
    assert "Nothing in this repository" in render(tmp_path, [], DEFAULTS)


def test_a_prohibition_is_not_read_as_a_requirement(tmp_path: Path) -> None:
    # "must never add a Signed-off-by" asks for the opposite of a DCO policy.
    (tmp_path / "CONTRIBUTING.md").write_text(
        "An agent must never add a `Signed-off-by:` trailer.\n"
    )
    assert ("attribution", "require_signed_off") not in signals_for(tmp_path)


def test_a_requirement_alongside_a_prohibition_is_still_found(tmp_path: Path) -> None:
    (tmp_path / "CONTRIBUTING.md").write_text(
        "An agent must never add a `Signed-off-by:` trailer.\n"
        "Humans must sign off with `git commit -s`.\n"
    )
    assert signals_for(tmp_path)[("attribution", "require_signed_off")].value is True


def test_negation_wrapped_onto_the_previous_line_is_honoured(tmp_path: Path) -> None:
    (tmp_path / "CONTRIBUTING.md").write_text(
        "An agent must never add a sign-off trailer. Only a human can certify\n"
        "the Developer Certificate of Origin.\n"
    )
    assert ("attribution", "require_signed_off") not in signals_for(tmp_path)


def test_a_mention_without_a_requirement_is_not_a_policy(tmp_path: Path) -> None:
    # Describing what the DCO is does not mean the project runs one.
    (tmp_path / "CONTRIBUTING.md").write_text(
        "Only a human can certify the Developer Certificate of Origin.\n"
    )
    assert ("attribution", "require_signed_off") not in signals_for(tmp_path)


def test_units_split_on_sentences_not_lines() -> None:
    from pr_policy.infer import units

    found = units("First sentence here. Second one follows.\n\n# Heading\n")
    assert [u for _, u in found] == ["First sentence here.", "Second one follows.", "# Heading"]


def test_unit_line_numbers_track_the_source() -> None:
    from pr_policy.infer import units

    found = units("line one.\n\nline three.\n")
    assert [n for n, _ in found] == [1, 3]


def write_contributing(root: Path, text: str) -> None:
    (root / "CONTRIBUTING.md").write_text(text)


def test_a_mention_of_ai_is_not_a_disclosure_policy(tmp_path: Path) -> None:
    write_contributing(
        tmp_path, "You may use AI tools here. Copilot is popular with contributors.\n"
    )
    assert ("disclosure", "enabled") not in signals_for(tmp_path)


def test_a_requirement_about_ai_enables_disclosure(tmp_path: Path) -> None:
    write_contributing(tmp_path, "You must disclose any AI tools you used.\n")
    signal = signals_for(tmp_path)[("disclosure", "enabled")]
    assert signal.value is True
    assert signal.source == "CONTRIBUTING.md:1"


@pytest.mark.parametrize(
    "sentence",
    [
        "Contributions that use generative AI must say so in the description.",
        "Please tell us if an LLM wrote part of the change.",
        "Disclose AI-generated code in the pull request.",
        "AI tools should be mentioned in the pull request.",
    ],
)
def test_requirement_shaped_ai_wording_enables_disclosure(tmp_path: Path, sentence: str) -> None:
    write_contributing(tmp_path, sentence + "\n")
    assert ("disclosure", "enabled") in signals_for(tmp_path)


def test_a_prohibition_on_ai_is_not_a_disclosure_policy(tmp_path: Path) -> None:
    write_contributing(tmp_path, "You must not submit AI-generated code.\n")
    assert ("disclosure", "enabled") not in signals_for(tmp_path)


def test_an_ai_checkbox_in_the_template_needs_no_extra_wording(tmp_path: Path) -> None:
    # The checkbox is the question; the template does not also have to say "must".
    target = tmp_path / ".github" / "pull_request_template.md"
    target.parent.mkdir()
    target.write_text("- [ ] I used ChatGPT for part of this change\n")
    assert ("disclosure", "enabled") in signals_for(tmp_path)


def test_a_checkbox_outside_the_template_is_just_a_mention(tmp_path: Path) -> None:
    write_contributing(tmp_path, "- [ ] I used ChatGPT for part of this change\n")
    assert ("disclosure", "enabled") not in signals_for(tmp_path)


def test_ai_prose_in_the_template_is_just_a_mention(tmp_path: Path) -> None:
    target = tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md"
    target.parent.mkdir()
    target.write_text("Many changes here are written with Copilot.\n")
    assert ("disclosure", "enabled") not in signals_for(tmp_path)


def test_a_mention_of_issues_is_not_a_linked_issue_policy(tmp_path: Path) -> None:
    write_contributing(
        tmp_path,
        "GitHub links a pull request to an issue when the body says Closes #12.\n"
        "Issues are triaged on Fridays.\n",
    )
    assert ("linked_issue", "enabled") not in signals_for(tmp_path)


@pytest.mark.parametrize(
    "sentence",
    [
        "Every pull request must link to an issue.",
        "Please open an issue first so we can agree on the approach.",
        "Link to an issue that this change fixes.",
        "The description should say Closes #123.",
    ],
)
def test_requirement_shaped_issue_wording_enables_linked_issue(
    tmp_path: Path, sentence: str
) -> None:
    write_contributing(tmp_path, sentence + "\n")
    assert ("linked_issue", "enabled") in signals_for(tmp_path)


def test_mentions_alone_enable_nothing(tmp_path: Path) -> None:
    write_contributing(
        tmp_path, "Claude and Copilot are popular. Issue first-timers are welcome here.\n"
    )
    assert scan(tmp_path) == []


# Paraphrased from the shape of two real templates. The first asks with checkboxes
# and every answer contains a negation; the second asks in prose under a heading.
CHECKBOX_STYLE_TEMPLATE = """\
<!-- Thanks for the pull request! Fill in each section. -->

#### Prerequisites checklist

- [ ] I have read the contributing guidelines.

#### AI acknowledgement

- [ ] I did not use AI to generate this change.
- [ ] I used AI, and I have not submitted anything I do not understand.

#### What changes did you make?
"""

PROSE_STYLE_TEMPLATE = """\
### Summary

<!-- Explain the change and why it is needed. -->

### Testing

### Generative AI

<!-- Keep the sentence that applies and delete the other. -->

I did not use generative AI tools when creating this PR.

I used generative AI tools when creating this PR, but a human has checked the
code and is responsible for the description and all code changes.
"""


def write_template(root: Path, text: str) -> None:
    target = root / ".github" / "PULL_REQUEST_TEMPLATE.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


def disclosure_findings(root: Path, body: str) -> list:
    """What the disclosure rule says about `body`, using the config `init` generates."""
    from pr_policy.context import PullRequest
    from pr_policy.rules import evaluate

    target = root / ".github" / "pr-policy.yml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(root, scan(root), DEFAULTS), encoding="utf-8")
    pr = PullRequest(body=body, metadata_available=True)
    findings, _, _ = evaluate(pr, load_config(root))
    return [f for f in findings if f.rule == "disclosure"]


def test_a_checkbox_template_whose_answers_are_negated_enables_disclosure(tmp_path: Path) -> None:
    write_template(tmp_path, CHECKBOX_STYLE_TEMPLATE)
    signal = signals_for(tmp_path)[("disclosure", "enabled")]
    assert signal.source == ".github/PULL_REQUEST_TEMPLATE.md:7"
    assert signal.quote == "AI acknowledgement"


def test_negated_answer_options_alone_enable_disclosure(tmp_path: Path) -> None:
    # No heading to rely on: the checkbox is the question, whatever it says.
    write_template(tmp_path, "- [ ] I did not use AI to write this.\n- [ ] I used AI.\n")
    signal = signals_for(tmp_path)[("disclosure", "enabled")]
    assert signal.quote == "I did not use AI to write this."


def test_a_prose_template_with_an_ai_heading_enables_disclosure(tmp_path: Path) -> None:
    write_template(tmp_path, PROSE_STYLE_TEMPLATE)
    signal = signals_for(tmp_path)[("disclosure", "enabled")]
    assert signal.source == ".github/PULL_REQUEST_TEMPLATE.md:7"
    assert signal.quote == "Generative AI"


def test_an_ai_heading_in_contributing_is_not_a_template_question(tmp_path: Path) -> None:
    write_contributing(tmp_path, "## Generative AI\n\nWe have thoughts about this.\n")
    assert ("disclosure", "enabled") not in signals_for(tmp_path)


def test_a_ticked_answer_satisfies_the_generated_config(tmp_path: Path) -> None:
    write_template(tmp_path, CHECKBOX_STYLE_TEMPLATE)
    body = "- [x] I did not use AI to generate this change.\n"
    assert disclosure_findings(tmp_path, body) == []


def test_an_untouched_checkbox_template_is_still_reported(tmp_path: Path) -> None:
    write_template(tmp_path, CHECKBOX_STYLE_TEMPLATE)
    findings = disclosure_findings(tmp_path, CHECKBOX_STYLE_TEMPLATE)
    assert [f.message for f in findings] == [
        "the AI-disclosure checkbox in the pull request template is not ticked"
    ]


def test_a_prose_template_passes_while_its_section_is_kept(tmp_path: Path) -> None:
    write_template(tmp_path, PROSE_STYLE_TEMPLATE)
    assert disclosure_findings(tmp_path, PROSE_STYLE_TEMPLATE) == []


def test_a_prose_template_fails_when_the_section_is_deleted(tmp_path: Path) -> None:
    write_template(tmp_path, PROSE_STYLE_TEMPLATE)
    body = "### Summary\n\nThis fixes the parser.\n\n### Testing\n\nRan the suite.\n"
    findings = disclosure_findings(tmp_path, body)
    assert [f.message for f in findings] == [
        "the pull request body carries no AI-disclosure statement"
    ]


# Everything `init` reacts to must be something the rule then recognises when ticked.
INIT_TRIGGERS = [
    "You must disclose generative AI use.",
    "Please say if AI-generated code is included.",
    "You should declare any AI tools you used.",
    "Disclose any AI assistance.",
    "Please tell us if AI helped.",
    "Disclose LLM assistance.",
    "Please tell us about Copilot use.",
    "Please mention ChatGPT usage.",
    "You must note if Claude helped.",
    "Declare Codex output.",
]


@pytest.mark.parametrize("sentence", INIT_TRIGGERS)
def test_what_init_reacts_to_is_recognised_by_the_rule_when_ticked(
    tmp_path: Path, sentence: str
) -> None:
    write_contributing(tmp_path, sentence + "\n")
    assert ("disclosure", "enabled") in signals_for(tmp_path)
    assert disclosure_findings(tmp_path, f"- [x] {sentence}\n") == []


def test_the_rule_default_covers_the_vocabulary_init_uses() -> None:
    from pr_policy.config import DISCLOSURE_CHECKBOX_PATTERNS
    from pr_policy.infer import AI_MENTION

    assert DEFAULTS["disclosure"]["checkbox_patterns"] == list(DISCLOSURE_CHECKBOX_PATTERNS)
    for sample in ["generative ai", "ai-generated", "ai tool", "ai assist", "ai help"]:
        assert AI_MENTION.search(sample)
        assert any(re.search(p, sample, re.IGNORECASE) for p in DISCLOSURE_CHECKBOX_PATTERNS)


@pytest.mark.parametrize(
    "sentence",
    [
        "You have to say if AI tools were used.",
        "Disclosing AI tools is mandatory.",
        "Please disclose any AI assistance.",
    ],
)
def test_more_requirement_wording_enables_disclosure(tmp_path: Path, sentence: str) -> None:
    write_contributing(tmp_path, sentence + "\n")
    assert ("disclosure", "enabled") in signals_for(tmp_path)


@pytest.mark.parametrize(
    "sentence",
    [
        "Contributions made with AI tools are always welcome.",
        "AI tools are welcome here, and we love Copilot.",
        "Mail tools are always handy.",
    ],
)
def test_welcome_is_not_a_requirement(tmp_path: Path, sentence: str) -> None:
    write_contributing(tmp_path, sentence + "\n")
    assert ("disclosure", "enabled") not in signals_for(tmp_path)


@pytest.mark.parametrize(
    "sentence",
    [
        "Link the issue it fixes.",
        "Please reference an issue in the description.",
        "Every change needs an associated issue, which you should link.",
        "Each pull request must link to the related issue.",
    ],
)
def test_more_issue_wording_enables_linked_issue(tmp_path: Path, sentence: str) -> None:
    write_contributing(tmp_path, sentence + "\n")
    assert ("linked_issue", "enabled") in signals_for(tmp_path)


def test_a_linked_issue_checkbox_in_the_template_counts(tmp_path: Path) -> None:
    write_template(tmp_path, "- [ ] I linked an issue that this change closes.\n")
    assert ("linked_issue", "enabled") in signals_for(tmp_path)


def test_a_linked_issue_checkbox_in_contributing_is_just_a_mention(tmp_path: Path) -> None:
    write_contributing(tmp_path, "- [ ] I linked an issue that this change closes.\n")
    assert ("linked_issue", "enabled") not in signals_for(tmp_path)


def test_issue_first_timers_are_not_an_issue_policy(tmp_path: Path) -> None:
    write_contributing(tmp_path, "Issue first-timers are always welcome.\n")
    assert scan(tmp_path) == []


@pytest.mark.parametrize(
    "sentence",
    [
        "All commits must be signed off.",
        "Use `git commit -s` for your commits.",
        "Every commit needs to carry a DCO sign-off.",
    ],
)
def test_attribution_shares_the_requirement_wording(tmp_path: Path, sentence: str) -> None:
    write_contributing(tmp_path, sentence + "\n")
    assert ("attribution", "require_signed_off") in signals_for(tmp_path)


def test_we_use_the_dco_alone_is_not_a_requirement(tmp_path: Path) -> None:
    write_contributing(tmp_path, "The kernel mirror uses the DCO.\n")
    assert ("attribution", "require_signed_off") not in signals_for(tmp_path)


def test_quotes_keep_their_leading_letters(tmp_path: Path) -> None:
    # "Xcode" and "xargs" start with characters the old trimming stripped.
    write_contributing(tmp_path, "Xcode users must link to an issue first.\n")
    assert signals_for(tmp_path)[("linked_issue", "enabled")].quote.startswith("Xcode users")

    from pr_policy.infer import _trim

    assert _trim("xargs: you must link an issue") == "xargs: you must link an issue"
    assert _trim("- [ ] I used generative AI") == "I used generative AI"
    assert _trim("- [x] ticked item") == "ticked item"
    assert _trim("### Generative AI") == "Generative AI"
    assert _trim("1. First step") == "First step"
