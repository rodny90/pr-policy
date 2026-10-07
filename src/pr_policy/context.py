"""The pull request under inspection.

Everything pr-policy evaluates comes from two places: the git history of the
branch, and — when running inside a GitHub Action — the event payload, which is
the only source for the pull request's title, body and labels.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# A git trailer: "Key: value", where the key has no whitespace.
TRAILER = re.compile(r"^(?P<key>[A-Za-z][A-Za-z0-9-]*):[ \t]*(?P<value>.+?)\s*$")

UNIT = "\x1f"
RECORD = "\x1e"


class GitError(RuntimeError):
    """Raised when git is unavailable or a revision cannot be resolved."""


def _git(root: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:  # pragma: no cover - depends on the host
        raise GitError("git is not installed or not on PATH") from exc
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def parse_trailers(message: str) -> dict[str, list[str]]:
    """Return the trailers from a commit message, keyed by lowercased name.

    Git treats only the final paragraph as the trailer block, and so do we: a
    line reading "Note: see below" halfway through a commit body is prose, not
    a trailer.
    """
    paragraphs = [p for p in re.split(r"\n\s*\n", message.strip()) if p.strip()]
    if not paragraphs:
        return {}

    trailers: dict[str, list[str]] = {}
    for line in paragraphs[-1].splitlines():
        match = TRAILER.match(line)
        if match:
            trailers.setdefault(match.group("key").lower(), []).append(match.group("value"))
    return trailers


@dataclass(frozen=True)
class Commit:
    sha: str
    author_name: str
    author_email: str
    message: str

    @property
    def subject(self) -> str:
        return self.message.strip().splitlines()[0] if self.message.strip() else ""

    @property
    def short_sha(self) -> str:
        return self.sha[:8]

    @property
    def trailers(self) -> dict[str, list[str]]:
        return parse_trailers(self.message)

    def trailer(self, name: str) -> list[str]:
        return self.trailers.get(name.lower(), [])


@dataclass(frozen=True)
class PullRequest:
    """A pull request, as far as pr-policy can see it."""

    title: str = ""
    body: str = ""
    author: str = ""
    commits: list[Commit] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    labels: list[str] = field(default_factory=list)
    # False when nothing supplied the title and body — running over a local
    # branch rather than inside a pull request. Rules that read the body are
    # skipped rather than guessing, because an absent body is not an empty one.
    metadata_available: bool = False

    @property
    def total_lines(self) -> int:
        return self.additions + self.deletions


def commits_between(root: Path, base: str, head: str) -> list[Commit]:
    raw = _git(
        root,
        "log",
        f"--format=%H{UNIT}%an{UNIT}%ae{UNIT}%B{RECORD}",
        f"{base}..{head}",
    )
    commits = []
    for record in raw.split(RECORD):
        record = record.strip("\n")
        if not record.strip():
            continue
        sha, name, email, message = record.split(UNIT, 3)
        commits.append(Commit(sha=sha, author_name=name, author_email=email, message=message))
    return commits


def diff_stats(root: Path, base: str, head: str) -> tuple[list[str], int, int]:
    """Return changed files and line counts for ``base...head`` (merge base)."""
    raw = _git(root, "diff", "--numstat", f"{base}...{head}")
    files: list[str] = []
    additions = deletions = 0
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, removed, path = parts
        files.append(path)
        # Binary files report "-" rather than a count.
        additions += int(added) if added.isdigit() else 0
        deletions += int(removed) if removed.isdigit() else 0
    return files, additions, deletions


def load_event(path: str | None = None) -> dict:
    """Read the GitHub Actions event payload, if this is running in one."""
    event_path = path or os.environ.get("GITHUB_EVENT_PATH")
    if not event_path or not Path(event_path).is_file():
        return {}
    try:
        return json.loads(Path(event_path).read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def from_git(
    root: Path,
    base: str,
    head: str = "HEAD",
    event: dict | None = None,
    title: str | None = None,
    body: str | None = None,
) -> PullRequest:
    """Build a :class:`PullRequest` from the repository and, optionally, an event.

    ``title`` and ``body`` override the event payload, which is what makes the
    body rules runnable outside a pull request.
    """
    commits = commits_between(root, base, head)
    files, additions, deletions = diff_stats(root, base, head)

    payload = (event or {}).get("pull_request") or {}
    has_metadata = bool(payload) or title is not None or body is not None

    return PullRequest(
        title=title if title is not None else (payload.get("title") or ""),
        body=body if body is not None else (payload.get("body") or ""),
        author=(payload.get("user") or {}).get("login") or "",
        commits=commits,
        changed_files=files,
        additions=payload.get("additions", additions),
        deletions=payload.get("deletions", deletions),
        labels=[label.get("name", "") for label in payload.get("labels") or []],
        metadata_available=has_metadata,
    )
