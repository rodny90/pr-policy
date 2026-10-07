"""Tests for the GitHub Action's shell logic.

The action's `run:` block is the one part of the project that CI would otherwise
be the first thing to execute. These tests lift that script straight out of
action.yml and run it, so a change that breaks the action fails here instead of
on somebody's pull request.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ACTION = Path(__file__).resolve().parent.parent / "action.yml"

pytestmark = [
    pytest.mark.skipif(
        shutil.which("pr-policy") is None,
        reason="the action invokes the installed pr-policy console script",
    ),
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="the action's shell script needs a POSIX bash, not the WSL launcher",
    ),
]


def check_step_script() -> str:
    steps = yaml.safe_load(ACTION.read_text())["runs"]["steps"]
    return next(step for step in steps if step["name"] == "Check the pull request")["run"]


def run_step(cwd: Path, output: Path, **env_overrides: str) -> subprocess.CompletedProcess:
    env = {
        "PATH": os.environ["PATH"],
        "GITHUB_OUTPUT": str(output),
        "BASE": "",
        "BASE_REF": "",
        "CONFIG": "",
        "STRICT": "false",
    }
    env.update(env_overrides)
    output.write_text("")
    return subprocess.run(
        ["bash", "-c", check_step_script()], cwd=cwd, env=env, capture_output=True, text=True
    )


def outputs(path: Path) -> dict[str, str]:
    text = path.read_text()
    parsed = {}
    for line in text.splitlines():
        if "=" in line and "<<" not in line:
            key, _, value = line.partition("=")
            parsed[key] = value
    if "findings<<PR_POLICY_EOF" in text:
        parsed["findings"] = text.split("findings<<PR_POLICY_EOF\n")[1].split("\nPR_POLICY_EOF")[0]
    return parsed


@pytest.fixture
def offending(repo):
    repo.branch("feature")
    repo.commit("A change\n\nSigned-off-by: Claude <noreply@anthropic.com>")
    return repo


def test_action_is_valid_yaml_with_the_expected_interface() -> None:
    action = yaml.safe_load(ACTION.read_text())
    assert action["runs"]["using"] == "composite"
    assert {"config", "base", "strict", "comment"} <= set(action["inputs"])
    assert {"exit-code", "findings"} <= set(action["outputs"])


def test_findings_do_not_fail_the_job_by_default(offending, tmp_path: Path) -> None:
    out = tmp_path / "gh_output"
    result = run_step(offending.root, out, BASE=offending.default_branch)
    assert result.returncode == 0
    assert outputs(out)["exit-code"] == "0"


def test_findings_output_is_parseable_json(offending, tmp_path: Path) -> None:
    out = tmp_path / "gh_output"
    run_step(offending.root, out, BASE=offending.default_branch)
    payload = json.loads(outputs(out)["findings"])
    assert payload["counts"]["warn"] == 1
    assert payload["findings"][0]["rule"] == "attribution"


def test_strict_with_error_severity_fails_the_job(offending, tmp_path: Path) -> None:
    config = offending.write("strict.yml", "rules:\n  attribution:\n    severity: error\n")
    out = tmp_path / "gh_output"
    run_step(offending.root, out, BASE=offending.default_branch, CONFIG=str(config), STRICT="true")
    assert outputs(out)["exit-code"] == "1"


def test_missing_base_ref_is_an_error(offending, tmp_path: Path) -> None:
    result = run_step(offending.root, tmp_path / "gh_output")
    assert result.returncode == 2
    assert "No base ref" in result.stderr


def test_explicit_base_skips_the_fetch(offending, tmp_path: Path) -> None:
    # The fixture repo has no 'origin', so a fetch would fail loudly.
    result = run_step(offending.root, tmp_path / "gh_output", BASE=offending.default_branch)
    assert "could not read" not in result.stderr.lower()
    assert result.returncode == 0


def comment_step_script() -> str:
    steps = yaml.safe_load(ACTION.read_text())["runs"]["steps"]
    return next(step for step in steps if step["name"] == "Comment on the pull request")["run"]


def fake_gh(directory: Path, *, existing: str = "", fail_on: str = "") -> Path:
    """Put a stand-in `gh` on PATH that logs its calls and can fail on a given verb.

    `fail_on` is "lookup" (the GET that finds the sticky comment), "write" (the
    POST or PATCH), or "" for a token that can do both.
    """
    bin_dir = directory / "bin"
    bin_dir.mkdir()
    log = directory / "gh-calls.log"
    script = bin_dir / "gh"
    script.write_text(
        "#!/bin/bash\n"
        f'echo "$@" >> "{log}"\n'
        'case "$*" in\n'
        '  *"-X "*) verb=write ;;\n'
        "  *) verb=lookup ;;\n"
        "esac\n"
        f'if [ "$verb" = "{fail_on}" ]; then\n'
        '  echo "gh: Resource not accessible by integration (HTTP 403)" >&2\n'
        "  exit 1\n"
        "fi\n"
        f'if [ "$verb" = "lookup" ]; then printf \'%b\\n\' "{existing}"; fi\n'
        "exit 0\n"
    )
    script.chmod(0o755)
    return bin_dir


def run_comment_step(
    cwd: Path, bin_dir: Path, report: str | None = "### pr-policy\n\nNo findings.\n"
) -> subprocess.CompletedProcess:
    """Run the comment step; `report` is what the check step left in policy-comment.md."""
    if report is not None:
        (cwd / "policy-comment.md").write_text(report)
    env = {
        "PATH": os.pathsep.join([str(bin_dir), os.environ["PATH"]]),
        "GH_TOKEN": "not-a-real-token",
        "PR": "7",
        "REPO": "octo/demo",
    }
    return subprocess.run(
        ["bash", "-c", comment_step_script()], cwd=cwd, env=env, capture_output=True, text=True
    )


def test_comment_is_created_when_none_exists(tmp_path: Path) -> None:
    result = run_comment_step(tmp_path, fake_gh(tmp_path))
    assert result.returncode == 0
    assert "::warning" not in result.stdout
    calls = (tmp_path / "gh-calls.log").read_text()
    assert "-X POST repos/octo/demo/issues/7/comments" in calls


def test_existing_comment_is_updated_in_place(tmp_path: Path) -> None:
    result = run_comment_step(tmp_path, fake_gh(tmp_path, existing="4242"))
    assert result.returncode == 0
    calls = (tmp_path / "gh-calls.log").read_text()
    assert "-X PATCH repos/octo/demo/issues/comments/4242" in calls
    assert "-X POST" not in calls


def test_comment_body_carries_the_marker(tmp_path: Path) -> None:
    run_comment_step(tmp_path, fake_gh(tmp_path))
    assert "<!-- pr-policy -->" in (tmp_path / "policy-comment.md").read_text()


@pytest.mark.parametrize("fail_on", ["lookup", "write"])
def test_unwritable_token_warns_instead_of_failing_the_job(tmp_path: Path, fail_on: str) -> None:
    # A fork pull request's GITHUB_TOKEN is read-only: the API answers 403.
    result = run_comment_step(tmp_path, fake_gh(tmp_path, fail_on=fail_on))
    assert result.returncode == 0
    assert "::warning" in result.stdout
    assert "fork" in result.stdout
    assert "workflow_run" in result.stdout
    assert "comment: false" in result.stdout
    # The reason from the API is still visible in the log.
    assert "HTTP 403" in result.stderr


def test_warning_is_a_single_workflow_command_line(tmp_path: Path) -> None:
    result = run_comment_step(tmp_path, fake_gh(tmp_path, fail_on="write"))
    warnings = [line for line in result.stdout.splitlines() if line.startswith("::warning")]
    assert len(warnings) == 1


def test_a_failed_comment_does_not_change_the_check_result(offending, tmp_path: Path) -> None:
    # The job's result comes from the check step's exit code, applied in a
    # later step; the comment step has no way to alter it.
    config = offending.write("strict.yml", "rules:\n  attribution:\n    severity: error\n")
    out = tmp_path / "gh_output"
    run_step(offending.root, out, BASE=offending.default_branch, CONFIG=str(config), STRICT="true")
    assert outputs(out)["exit-code"] == "1"

    bin_dir = fake_gh(tmp_path, fail_on="write")
    assert run_comment_step(offending.root, bin_dir).returncode == 0

    steps = yaml.safe_load(ACTION.read_text())["runs"]["steps"]
    assert steps[-1]["run"] == "exit ${{ steps.check.outputs.exit-code }}"


@pytest.mark.parametrize("report", [None, ""])
def test_no_report_means_nothing_is_posted(tmp_path: Path, report: str | None) -> None:
    # A bare marker would overwrite a good sticky comment with an empty one.
    result = run_comment_step(tmp_path, fake_gh(tmp_path), report=report)
    assert result.returncode == 0
    assert "no comment to post" in result.stdout
    assert not (tmp_path / "gh-calls.log").exists()


def test_only_the_first_matching_comment_is_updated(tmp_path: Path) -> None:
    run_comment_step(tmp_path, fake_gh(tmp_path, existing="11\\n22"))
    calls = (tmp_path / "gh-calls.log").read_text()
    assert "-X PATCH repos/octo/demo/issues/comments/11" in calls
    assert "comments/22" not in calls


def test_the_lookup_only_trusts_the_actions_own_comments() -> None:
    # Anyone can paste the marker into a comment; only the bot's is the sticky one.
    assert 'select(.user.login == \\"github-actions[bot]\\"' in comment_step_script()


def test_a_config_error_leaves_no_report_to_post(offending, tmp_path: Path) -> None:
    bad = offending.write("bad.yml", "rules:\n  nonsense: {}\n")
    stale = offending.root / "policy-comment.md"
    stale.write_text("### pr-policy\n\nleft over from an earlier run\n")
    out = tmp_path / "gh_output"
    result = run_step(offending.root, out, BASE=offending.default_branch, CONFIG=str(bad))
    assert outputs(out)["exit-code"] == "2"
    assert not stale.exists()
    assert "::warning" not in result.stdout


def test_a_normal_run_leaves_a_report(offending, tmp_path: Path) -> None:
    run_step(offending.root, tmp_path / "gh_output", BASE=offending.default_branch)
    assert (offending.root / "policy-comment.md").read_text().startswith("### pr-policy")


def test_the_exit_code_output_documents_all_three_values() -> None:
    action = yaml.safe_load(ACTION.read_text())
    description = action["outputs"]["exit-code"]["description"]
    assert all(code in description for code in ("0", "1", "2"))


def test_the_comment_step_only_runs_on_pull_request_events() -> None:
    # pull_request_target would hand a write token to a job that checks out
    # attacker-controlled code, so the action does not support it.
    steps = yaml.safe_load(ACTION.read_text())["runs"]["steps"]
    step = next(s for s in steps if s["name"] == "Comment on the pull request")
    assert "github.event_name == 'pull_request'" in step["if"]
    assert "pull_request_target" not in comment_step_script()
