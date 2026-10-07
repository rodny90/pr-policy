"""Tests for `pr-policy replay`, with `gh` faked at the subprocess boundary."""

from __future__ import annotations

import json
import subprocess

import pytest

from pr_policy import replay as replay_module
from pr_policy.cli import main

CLEAN = {
    "number": 1,
    "title": "Fix typo",
    "body": "Fixes a typo in the README so the install command reads correctly.",
    "author": {"login": "alice"},
    "labels": [],
    "files": [{"path": "a.py", "additions": 1, "deletions": 0}],
    "additions": 1,
    "deletions": 0,
    "commits": [
        {
            "oid": "a" * 40,
            "authors": [{"name": "Alice", "email": "a@example.com", "login": "alice"}],
            "messageHeadline": "Fix typo",
            "messageBody": "Signed-off-by: Alice <a@example.com>",
        }
    ],
}
AGENT = {
    **CLEAN,
    "number": 2,
    "commits": [
        {
            "oid": "b" * 40,
            "authors": [{"name": "Bob", "email": "b@example.com", "login": "bob"}],
            "messageHeadline": "Add thing",
            "messageBody": "Signed-off-by: Claude <noreply@anthropic.com>",
        }
    ],
}


@pytest.fixture
def fake_gh(monkeypatch):
    """Replace subprocess.run for gh; returns a state dict to tweak and inspect."""
    state = {"auth": 0, "list": 0, "stdout": json.dumps([CLEAN, AGENT]), "calls": [], "missing": 0}

    def run(cmd, **kwargs):
        assert cmd[0] == "gh"
        state["calls"].append(cmd)
        if state["missing"]:
            raise FileNotFoundError("gh")
        if cmd[1] == "auth":
            return subprocess.CompletedProcess(cmd, state["auth"], "", "not logged in")
        return subprocess.CompletedProcess(cmd, state["list"], state["stdout"], "boom")

    monkeypatch.setattr(replay_module.subprocess, "run", run)
    return state


def test_summary_counts_and_messages(fake_gh, tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["replay", "--repo", "o/n", "--last", "2"]) == 0
    out = capsys.readouterr().out
    assert "would have flagged 1 of 2 PRs" in out
    assert "attribution: 1" in out
    assert "#2" in out and "names a coding agent" in out
    assert "#1\n" not in out
    assert "signals, not verdicts" in out
    assert "built-in defaults" in out


def test_only_read_only_gh_calls(fake_gh, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    main(["replay", "--repo", "o/n", "--last", "7"])
    assert [c[1:3] for c in fake_gh["calls"]] == [["auth", "status"], ["pr", "list"]]
    assert "--limit" in fake_gh["calls"][1] and "7" in fake_gh["calls"][1]
    assert "merged" in fake_gh["calls"][1]


def test_local_config_is_used_and_explicit_config_wins(
    fake_gh, tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "pr-policy.yml").write_text(
        "rules:\n  attribution: false\n", encoding="utf-8"
    )
    assert main(["replay", "--repo", "o/n"]) == 0
    assert "would have flagged 0 of 2 PRs" in capsys.readouterr().out

    other = tmp_path / "other.yml"
    other.write_text("rules:\n  size:\n    enabled: false\n", encoding="utf-8")
    assert main(["replay", "--repo", "o/n", "--config", str(other)]) == 0
    assert "would have flagged 1 of 2 PRs" in capsys.readouterr().out


def test_gh_missing_exits_2(fake_gh, tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    fake_gh["missing"] = 1
    assert main(["replay", "--repo", "o/n"]) == 2
    assert "gh" in capsys.readouterr().err


def test_gh_unauthenticated_exits_2(fake_gh, tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    fake_gh["auth"] = 1
    assert main(["replay", "--repo", "o/n"]) == 2
    assert "not authenticated" in capsys.readouterr().err
    assert len(fake_gh["calls"]) == 1


def test_gh_failure_and_bad_input_exit_2(fake_gh, tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    fake_gh["list"] = 1
    assert main(["replay", "--repo", "o/n"]) == 2
    fake_gh["list"] = 0
    fake_gh["stdout"] = "not json"
    assert main(["replay", "--repo", "o/n"]) == 2
    assert main(["replay", "--repo", "o/n", "--last", "0"]) == 2


def _co_authored(n: int) -> dict:
    commits = [
        {
            "oid": f"{i:02d}" + "c" * 38,
            "authors": [{"name": "Bob", "email": "b@example.com", "login": "bob"}],
            "messageHeadline": f"Step {i}",
            "messageBody": "Co-authored-by: Claude <noreply@anthropic.com>",
        }
        for i in range(n)
    ]
    return {**CLEAN, "number": 3, "commits": commits}


def test_same_shape_findings_are_grouped(fake_gh, tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    fake_gh["stdout"] = json.dumps([_co_authored(16)])
    assert main(["replay", "--repo", "o/n", "--last", "1"]) == 0
    out = capsys.readouterr().out
    assert (
        "[attribution] 16 commits credit a coding agent (claude) with 'Co-authored-by' "
        "rather than 'Assisted-by' (00cccccc, 01cccccc, 02cccccc, ... +13 more)"
    ) in out
    assert out.count("Co-authored-by") == 1
    assert "attribution: 1" in out


def test_small_group_lists_all_shas_and_single_stays(
    fake_gh, tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    fake_gh["stdout"] = json.dumps([_co_authored(2), AGENT])
    assert main(["replay", "--repo", "o/n", "--last", "2"]) == 0
    out = capsys.readouterr().out
    assert "2 commits credit a coding agent (claude)" in out
    assert "(00cccccc, 01cccccc)" in out and "more" not in out
    assert "- [attribution] commit bbbbbbbb has" in out
