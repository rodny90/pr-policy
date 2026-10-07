"""The version is written in three places; they must not drift apart."""

from __future__ import annotations

import re
from pathlib import Path

import pr_policy
import repo_ready

ROOT = Path(__file__).resolve().parent.parent


def pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "pyproject.toml has no version"
    return match.group(1)


def test_the_three_versions_agree() -> None:
    assert pr_policy.__version__ == pyproject_version()
    assert repo_ready.__version__ == pyproject_version()


def test_the_changelog_has_a_heading_and_link_for_this_version() -> None:
    version = pyproject_version()
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = re.findall(r"^## \[(\d[^\]]*)\]", text, re.MULTILINE)
    assert headings[0] == version
    assert re.search(rf"^\[{re.escape(version)}\]: ", text, re.MULTILINE)
