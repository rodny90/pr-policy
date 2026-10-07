"""Tests for the pr-policy command line: output formats and exit codes."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pr_policy.cli import main

AGENT_SIGN_OFF = "Add a thing\n\nSigned-off-by: Claude <noreply@anthropic.com>"


@pytest.fixture
def branch(repo):
    """A feature branch whose single commit breaks the attribution rule."""
    repo.branch("feature")
    repo.commit(AGENT_SIGN_OFF)
    return repo


def check(repo, *extra: str) -> list[str]:
    return [
        "check",
        "--repo",
        str(repo.root),
        "--base",
        repo.default_branch,
        "--head",
        "feature",
        *extra,
    ]


def test_findings_do_not_fail_the_build_by_default(branch, capsys) -> None:
    assert main(check(branch)) == 0
    assert "names a coding agent" in capsys.readouterr().out


def test_strict_fails_only_on_errors(branch, capsys) -> None:
    # Default severity is warn, so --strict alone still passes.
    assert main(check(branch, "--strict")) == 0

    branch.write(".github/pr-policy.yml", "rules:\n  attribution:\n    severity: error\n")
    assert main(check(branch, "--strict")) == 1


def test_enforce_in_the_config_fails_without_the_flag(branch, capsys) -> None:
    branch.write(
        ".github/pr-policy.yml",
        "enforce: true\nrules:\n  attribution:\n    severity: error\n",
    )
    assert main(check(branch)) == 1


def test_reporting_only_note_is_shown(branch, capsys) -> None:
    branch.write(".github/pr-policy.yml", "rules:\n  attribution:\n    severity: error\n")
    main(check(branch))
    assert "reporting only" in capsys.readouterr().out


def test_clean_branch_reports_no_findings(repo, capsys) -> None:
    repo.branch("feature")
    repo.commit("A change\n\nSigned-off-by: A Human <human@example.com>")
    body = repo.write("b.md", "This change adds the module we agreed on in triage.")
    assert main(check(repo, "--body-file", str(body))) == 0
    assert "No findings" in capsys.readouterr().out


def test_json_output_is_valid_and_complete(branch, capsys) -> None:
    main(check(branch, "--format", "json"))
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"]["warn"] == 1
    assert payload["findings"][0]["rule"] == "attribution"
    assert payload["exit_code"] == 0
    assert "attribution" in payload["checked"]


def test_markdown_output_is_a_comment_body(branch, capsys) -> None:
    main(check(branch, "--format", "markdown"))
    out = capsys.readouterr().out
    assert out.startswith("### pr-policy")
    assert "🟡" in out
    assert "not a verdict" in out


def test_markdown_output_when_clean(repo, capsys) -> None:
    repo.branch("feature")
    repo.commit("A change")
    main(check(repo, "--format", "markdown"))
    assert "No findings" in capsys.readouterr().out


def test_body_file_makes_the_body_rules_run(branch, capsys) -> None:
    body = branch.write("body.md", "## Description\n\nThis explains the change fully.\n")
    main(check(branch, "--body-file", str(body)))
    out = capsys.readouterr().out
    assert "template" in out.split("rules run:")[1]
    assert "skipped" not in out


def test_missing_body_file_is_an_error(branch, capsys) -> None:
    assert main(check(branch, "--body-file", str(branch.root / "absent.md"))) == 2
    assert "cannot read" in capsys.readouterr().err


def test_body_can_be_read_from_stdin(branch, capsys, monkeypatch) -> None:
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("A description long enough to pass."))
    main(check(branch, "--body-file", "-"))
    assert "template" in capsys.readouterr().out.split("rules run:")[1]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="named pipes need a POSIX platform")
def test_body_from_a_fifo_is_read(branch, capsys) -> None:
    fifo = branch.root / "body.fifo"
    os.mkfifo(fifo)
    if os.fork() == 0:  # pragma: no cover - child writes then exits
        fifo.write_text("A description long enough to pass the minimum.")
        os._exit(0)
    assert main(check(branch, "--body-file", str(fifo))) == 0


def test_unknown_revision_is_an_error(branch, capsys) -> None:
    assert main(["check", "--repo", str(branch.root), "--base", "nope", "--head", "feature"]) == 2
    assert "pr-policy:" in capsys.readouterr().err


def test_broken_config_is_an_error(branch, capsys) -> None:
    branch.write(".github/pr-policy.yml", "rules:\n  nonsense: true\n")
    assert main(check(branch)) == 2
    assert "unknown rule" in capsys.readouterr().err


def test_skipped_rules_are_reported(branch, capsys) -> None:
    main(check(branch))
    assert "skipped (no pull request title or body available)" in capsys.readouterr().out


# --- init ------------------------------------------------------------------


def test_init_writes_a_config(repo, capsys) -> None:
    repo.write("CONTRIBUTING.md", "All commits must be signed off: use `git commit -s`.\n")
    assert main(["init", "--repo", str(repo.root)]) == 0
    written = (repo.root / ".github" / "pr-policy.yml").read_text(encoding="utf-8")
    assert "require_signed_off: true" in written
    assert "attribution.require_signed_off" in capsys.readouterr().out


def test_init_refuses_to_overwrite(repo, capsys) -> None:
    repo.write(".github/pr-policy.yml", "version: 1\n")
    assert main(["init", "--repo", str(repo.root)]) == 2
    assert "already exists" in capsys.readouterr().err


def test_init_force_overwrites(repo, capsys) -> None:
    repo.write(".github/pr-policy.yml", "version: 1\n")
    assert main(["init", "--repo", str(repo.root), "--force"]) == 0
    assert "rules:" in (repo.root / ".github" / "pr-policy.yml").read_text(encoding="utf-8")


def test_init_stdout_writes_nothing(repo, capsys) -> None:
    assert main(["init", "--repo", str(repo.root), "--stdout"]) == 0
    assert "version: 1" in capsys.readouterr().out
    assert not (repo.root / ".github" / "pr-policy.yml").exists()


def test_init_reports_when_nothing_was_inferred(repo, capsys) -> None:
    assert main(["init", "--repo", str(repo.root)]) == 0
    assert "No project-specific policy found" in capsys.readouterr().out


def test_init_on_a_missing_directory(tmp_path: Path, capsys) -> None:
    assert main(["init", "--repo", str(tmp_path / "absent")]) == 2


def test_bare_invocation_prints_help(capsys) -> None:
    assert main([]) == 0
    assert "usage:" in capsys.readouterr().out


def test_version_flag(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "pr-policy" in capsys.readouterr().out


def test_markdown_never_lets_a_trailer_mention_or_link(repo, capsys) -> None:
    repo.branch("feature")
    repo.commit(
        "A change\n\nSigned-off-by: Claude @maintainer [free money](http://evil.example) "
        "<noreply@anthropic.com>"
    )
    main(check(repo, "--format", "markdown"))
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if "@maintainer" in ln)
    # Every attacker-controlled character sits inside the code span.
    outside = line.split("`")[0] + line.rsplit("`", 1)[1]
    assert "@maintainer" not in outside
    assert "evil.example" not in outside
    assert "[free money]" not in outside


def test_code_span_survives_backticks_in_the_text() -> None:
    from pr_policy.report import code_span

    assert code_span("a `b` c") == "``a `b` c``"
    assert code_span("`edge`") == "`` `edge` ``"
    assert code_span("two   spaces\nnewline") == "`two spaces newline`"


def test_markdown_survives_a_legacy_windows_code_page(branch, monkeypatch) -> None:
    import io
    import sys

    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252", newline=""))
    assert main(check(branch, "--format", "markdown")) == 0
    sys.stdout.flush()
    assert "🟡".encode() in raw.getvalue()
