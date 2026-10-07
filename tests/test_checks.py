"""Tests for the individual checks and the scoring model."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_ready.checks import CHECKS, Repo, audit

LICENSE_TEXT = "MIT License\n\n" + "Permission is hereby granted, free of charge. " * 5
README_TEXT = (
    "# demo\n\nA demo project used by the test suite.\n\n"
    "## Installation\n\n    pip install demo\n\n"
    "## Usage\n\n    demo --help\n\n"
) + "Filler prose to clear the minimum length. " * 10


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """An empty directory standing in for a repository."""
    return tmp_path


def result_for(root: Path, check_id: str):
    report = audit(root)
    return next(r for r in report.results if r.id == check_id)


def test_empty_repo_scores_zero(repo: Path) -> None:
    report = audit(repo)
    assert report.score == 0
    assert report.grade == "F"
    assert all(not r.passed for r in report.results)


def test_every_failure_carries_a_fix(repo: Path) -> None:
    report = audit(repo)
    assert all(r.fix for r in report.failed)


def test_weights_sum_to_one_hundred() -> None:
    assert sum(check.weight for check in CHECKS) == 100


def test_check_ids_are_unique() -> None:
    ids = [check.id for check in CHECKS]
    assert len(ids) == len(set(ids))


def test_license_detected_case_insensitively(repo: Path) -> None:
    (repo / "license.md").write_text(LICENSE_TEXT)
    assert result_for(repo, "license").passed


def test_stub_license_is_rejected(repo: Path) -> None:
    (repo / "LICENSE").write_text("MIT")
    result = result_for(repo, "license")
    assert not result.passed
    assert "empty or truncated" in result.detail


def test_short_readme_is_rejected(repo: Path) -> None:
    (repo / "README.md").write_text("# demo\n")
    result = result_for(repo, "readme")
    assert not result.passed
    assert "characters" in result.detail


def test_readme_sections_require_install_and_usage(repo: Path) -> None:
    (repo / "README.md").write_text("# demo\n\n## Installation\n\npip install demo\n")
    result = result_for(repo, "readme-sections")
    assert not result.passed
    assert "a usage" in result.detail


def test_complete_readme_passes_both_checks(repo: Path) -> None:
    (repo / "README.md").write_text(README_TEXT)
    assert result_for(repo, "readme").passed
    assert result_for(repo, "readme-sections").passed


def test_tests_found_by_directory(repo: Path) -> None:
    (repo / "tests").mkdir()
    (repo / "tests" / "test_thing.py").write_text("def test_x(): pass\n")
    assert result_for(repo, "tests").passed


def test_tests_found_by_filename_convention(repo: Path) -> None:
    (repo / "widget.test.ts").write_text("it('works', () => {});\n")
    assert result_for(repo, "tests").passed


def test_vendored_tests_do_not_count(repo: Path) -> None:
    vendored = repo / "node_modules" / "left-pad" / "tests"
    vendored.mkdir(parents=True)
    (vendored / "test_pad.py").write_text("def test_x(): pass\n")
    assert not result_for(repo, "tests").passed


def test_ci_found_in_github_workflows(repo: Path) -> None:
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: ci\n")
    assert result_for(repo, "ci").passed


def test_ci_ignores_non_yaml_files(repo: Path) -> None:
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "README.md").write_text("notes\n")
    assert not result_for(repo, "ci").passed


def test_ci_found_in_gitlab_config(repo: Path) -> None:
    (repo / ".gitlab-ci.yml").write_text("stages: [test]\n")
    assert result_for(repo, "ci").passed


def test_docs_directory_is_searched(repo: Path) -> None:
    (repo / "docs").mkdir()
    (repo / "docs" / "CONTRIBUTING.md").write_text("How to contribute.\n")
    assert result_for(repo, "contributing").passed


def test_issue_template_directory(repo: Path) -> None:
    directory = repo / ".github" / "ISSUE_TEMPLATE"
    directory.mkdir(parents=True)
    (directory / "bug_report.md").write_text("## Bug\n")
    assert result_for(repo, "issue-templates").passed


def test_score_is_weighted_not_counted(repo: Path) -> None:
    # .gitignore is worth 3 points; one of twelve checks would be 8%.
    (repo / ".gitignore").write_text("*.pyc\n")
    assert audit(repo).score == 3


def test_failed_results_are_ordered_by_weight(repo: Path) -> None:
    weights = [r.weight for r in audit(repo).failed]
    assert weights == sorted(weights, reverse=True)


def test_grades_track_score_bands(repo: Path) -> None:
    (repo / "LICENSE").write_text(LICENSE_TEXT)
    (repo / "README.md").write_text(README_TEXT)
    report = audit(repo)
    assert report.score == 35
    assert report.grade == "F"


def test_report_serialises_to_json(repo: Path) -> None:
    payload = audit(repo).as_dict()
    assert payload["score"] == 0
    assert len(payload["checks"]) == len(CHECKS)
    assert {"id", "title", "passed", "weight", "detail", "fix"} == set(payload["checks"][0])


def test_repo_find_returns_none_when_absent(repo: Path) -> None:
    assert Repo(repo).find("nothing-here") is None
