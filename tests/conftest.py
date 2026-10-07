"""Shared fixtures: a throwaway git repository the tests can commit into."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


class GitRepo:
    """A real git repository in a temporary directory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._git("init", "-q", ".")
        self._git("config", "user.email", "human@example.com")
        self._git("config", "user.name", "A Human")
        self._git("config", "commit.gpgsign", "false")
        (root / "README.md").write_text("demo repository\n")
        self._git("add", "-A")
        self._git("commit", "-qm", "Initial commit")
        self.default_branch = self._git("rev-parse", "--abbrev-ref", "HEAD").strip()

    def _git(self, *args: str) -> str:
        proc = subprocess.run(
            ["git", *args], cwd=self.root, capture_output=True, text=True, check=True
        )
        return proc.stdout

    def branch(self, name: str) -> None:
        self._git("checkout", "-qb", name)

    def commit(self, message: str, path: str = "file.py", content: str = "value = 1\n") -> str:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(content)
        self._git("add", "-A")
        self._git("commit", "-q", "-m", message)
        return self._git("rev-parse", "HEAD").strip()

    def write(self, path: str, content: str) -> Path:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target


@pytest.fixture
def repo(tmp_path: Path) -> GitRepo:
    return GitRepo(tmp_path)


@pytest.fixture(autouse=True)
def _isolate_from_github_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the tests hermetic when they run inside a real pull request job.

    The tool reads the live pull request from GITHUB_EVENT_PATH, so without this
    the suite would judge the pull request that is running it.
    """
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
