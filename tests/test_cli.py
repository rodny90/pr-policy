"""Tests for argument handling, output formats and exit codes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from repo_ready.checks import audit
from repo_ready.cli import Style, main, render_markdown, render_text


@pytest.fixture
def good_repo(tmp_path: Path) -> Path:
    (tmp_path / "LICENSE").write_text("MIT License\n" + "Permission is granted. " * 10)
    (tmp_path / "README.md").write_text(
        "# demo\n\n## Installation\n\npip install demo\n\n## Usage\n\ndemo .\n\n"
        + "Words to pass the length floor. " * 10
    )
    return tmp_path


def test_exit_zero_without_a_threshold(good_repo: Path, capsys) -> None:
    assert main([str(good_repo)]) == 0


def test_min_score_gate_fails_a_thin_repo(tmp_path: Path, capsys) -> None:
    assert main([str(tmp_path), "--min-score", "50"]) == 1


def test_min_score_gate_passes_when_met(good_repo: Path, capsys) -> None:
    score = audit(good_repo).score
    assert main([str(good_repo), "--min-score", str(score)]) == 0


def test_missing_path_reports_an_error(tmp_path: Path, capsys) -> None:
    assert main([str(tmp_path / "nope")]) == 2
    assert "is not a directory" in capsys.readouterr().err


def test_json_output_is_valid_json(good_repo: Path, capsys) -> None:
    main([str(good_repo), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["score"] == audit(good_repo).score
    assert payload["grade"]


def test_markdown_output_has_a_table(good_repo: Path, capsys) -> None:
    main([str(good_repo), "--format", "markdown"])
    out = capsys.readouterr().out
    assert "| --- | --- | --- |" in out
    assert "✅" in out and "❌" in out


def test_text_output_lists_fixes_by_default(tmp_path: Path, capsys) -> None:
    main([str(tmp_path)])
    assert "Fix these first:" in capsys.readouterr().out


def test_no_fixes_flag_suppresses_them(tmp_path: Path, capsys) -> None:
    main([str(tmp_path), "--no-fixes"])
    assert "Fix these first:" not in capsys.readouterr().out


def test_plain_style_emits_no_escape_codes(tmp_path: Path) -> None:
    output = render_text(audit(tmp_path), Style(enabled=False))
    assert "\033[" not in output


def test_enabled_style_emits_escape_codes(tmp_path: Path) -> None:
    output = render_text(audit(tmp_path), Style(enabled=True))
    assert "\033[" in output


def test_markdown_renderer_reports_the_score(tmp_path: Path) -> None:
    assert "0/100" in render_markdown(audit(tmp_path))


def test_version_flag(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "repo-ready" in capsys.readouterr().out
