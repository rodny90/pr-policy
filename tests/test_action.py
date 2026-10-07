"""Tests for the GitHub Action's shell logic.

The action's `run:` block is the one part of the project that CI would otherwise
be the first thing to execute. These tests lift that script straight out of
action.yml and run it, so a change that breaks the action fails here instead of
on somebody's pull request.
"""

from __future__ import annotations

import json
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
        "PATH": __import__("os").environ["PATH"],
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
