"""Replay recent merged pull requests against a policy, offline and read-only.

Pull request data comes from the ``gh`` CLI (``gh pr list``, a read-only call) and
is turned into the same :class:`PullRequest` the ``check`` command evaluates, so a
replay and a live check agree. Nothing is ever written to GitHub.
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from dataclasses import dataclass, field

from pr_policy.config import Config
from pr_policy.context import Commit, PullRequest
from pr_policy.report import Finding
from pr_policy.rules import evaluate

JSON_FIELDS = "number,title,body,author,labels,commits,files,additions,deletions"


class ReplayError(RuntimeError):
    """Raised when gh is missing, not signed in, or returns something unusable."""


def _gh(*args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except FileNotFoundError as exc:
        raise ReplayError("the GitHub CLI (gh) is not installed or not on PATH") from exc


def fetch_merged(repo: str, limit: int) -> list[dict]:
    """Return the ``limit`` most recently merged pull requests of ``repo``."""
    if _gh("auth", "status").returncode != 0:
        raise ReplayError("gh is not authenticated (run 'gh auth login')")
    proc = _gh(
        "pr",
        "list",
        "--repo",
        repo,
        "--state",
        "merged",
        "--limit",
        str(limit),
        "--json",
        JSON_FIELDS,
    )
    if proc.returncode != 0:
        raise ReplayError(f"gh pr list failed: {proc.stderr.strip()}")
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise ReplayError(f"gh returned invalid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ReplayError("gh returned an unexpected response")
    return data


def to_pull_request(item: dict) -> PullRequest:
    """Map one ``gh pr list --json`` entry onto a :class:`PullRequest`."""
    commits = []
    for raw in item.get("commits") or []:
        authors = raw.get("authors") or [{}]
        headline = raw.get("messageHeadline") or ""
        body = raw.get("messageBody") or ""
        commits.append(
            Commit(
                sha=raw.get("oid") or "",
                author_name=authors[0].get("name") or authors[0].get("login") or "",
                author_email=authors[0].get("email") or "",
                message=f"{headline}\n\n{body}" if body.strip() else headline,
            )
        )
    return PullRequest(
        title=item.get("title") or "",
        body=item.get("body") or "",
        author=(item.get("author") or {}).get("login") or "",
        commits=commits,
        changed_files=[f.get("path", "") for f in item.get("files") or []],
        additions=item.get("additions") or 0,
        deletions=item.get("deletions") or 0,
        labels=[label.get("name", "") for label in item.get("labels") or []],
        metadata_available=True,
    )


@dataclass
class Replay:
    total: int = 0
    flagged: list[tuple[int, list[Finding]]] = field(default_factory=list)
    rule_counts: Counter = field(default_factory=Counter)
    checked: list[str] = field(default_factory=list)


def replay(items: list[dict], config: Config) -> Replay:
    result = Replay(total=len(items))
    for item in items:
        findings, checked, _ = evaluate(to_pull_request(item), config)
        result.checked = checked
        if findings:
            result.flagged.append((int(item.get("number") or 0), findings))
            # Count each rule once per pull request, not once per finding.
            result.rule_counts.update({f.rule for f in findings})
    return result


def render(result: Replay, repo: str, config: Config) -> str:
    source = config.source or "built-in defaults"
    lines = [
        f"pr-policy replay: {repo} (config: {source})",
        "",
        f"  would have flagged {len(result.flagged)} of {result.total} PRs",
    ]
    if result.rule_counts:
        lines += ["", "  per rule (PRs flagged):"]
        for rule, count in sorted(result.rule_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"    {rule}: {count}")
    for number, findings in result.flagged:
        lines += ["", f"  #{number}"]
        lines += [f"    - [{f.rule}] {f.message}" for f in findings]
    lines += [
        "",
        f"  rules run: {', '.join(result.checked) or 'none'}",
        "  These are signals, not verdicts. Nothing was posted or changed on GitHub.",
    ]
    return "\n".join(lines)
