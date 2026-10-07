"""Tests for trailer parsing and for reading a pull request out of git."""

from __future__ import annotations

import json
from pathlib import Path

from pr_policy.context import commits_between, diff_stats, from_git, load_event, parse_trailers


def test_parses_trailers_from_the_final_paragraph() -> None:
    trailers = parse_trailers(
        "Subject\n\nSome body text.\n\nSigned-off-by: A <a@b.c>\nAssisted-by: Claude:opus"
    )
    assert trailers == {"signed-off-by": ["A <a@b.c>"], "assisted-by": ["Claude:opus"]}


def test_prose_colons_in_the_body_are_not_trailers() -> None:
    trailers = parse_trailers("Subject\n\nNote: this is prose.\n\nSigned-off-by: A <a@b.c>")
    assert "note" not in trailers


def test_trailer_keys_are_case_insensitive() -> None:
    assert "signed-off-by" in parse_trailers("Subject\n\nSIGNED-OFF-BY: A <a@b.c>")


def test_repeated_trailers_are_all_kept() -> None:
    trailers = parse_trailers("S\n\nCo-authored-by: A <a@b.c>\nCo-authored-by: B <b@b.c>")
    assert len(trailers["co-authored-by"]) == 2


def test_message_without_trailers() -> None:
    assert parse_trailers("Just a subject line") == {}


def test_empty_message() -> None:
    assert parse_trailers("") == {}


def test_commits_are_read_in_range(repo) -> None:
    repo.branch("feature")
    repo.commit("First change")
    repo.commit("Second change")
    pr = from_git(repo.root, repo.default_branch, "feature")
    assert [c.subject for c in pr.commits] == ["Second change", "First change"]


def test_commit_exposes_author_and_trailers(repo) -> None:
    repo.branch("feature")
    repo.commit("A change\n\nSigned-off-by: A Human <human@example.com>")
    commit = from_git(repo.root, repo.default_branch, "feature").commits[0]
    assert commit.author_email == "human@example.com"
    assert commit.trailer("Signed-off-by") == ["A Human <human@example.com>"]
    assert commit.short_sha == commit.sha[:8]


def test_diff_stats_counts_lines_and_files(repo) -> None:
    repo.branch("feature")
    repo.commit("Change", path="a.py", content="one\ntwo\n")
    repo.commit("Change again", path="b.py", content="three\n")
    files, additions, deletions = diff_stats(repo.root, repo.default_branch, "feature")
    assert sorted(files) == ["a.py", "b.py"]
    assert additions == 3
    assert deletions == 0


def test_metadata_is_absent_without_an_event(repo) -> None:
    repo.branch("feature")
    repo.commit("Change")
    assert from_git(repo.root, repo.default_branch, "feature").metadata_available is False


def test_explicit_body_supplies_metadata(repo) -> None:
    repo.branch("feature")
    repo.commit("Change")
    pr = from_git(repo.root, repo.default_branch, "feature", body="Some description")
    assert pr.metadata_available is True
    assert pr.body == "Some description"


def test_event_payload_supplies_title_body_and_labels(repo) -> None:
    repo.branch("feature")
    repo.commit("Change")
    event = {
        "pull_request": {
            "title": "Add a thing",
            "body": "Because reasons.",
            "user": {"login": "someone"},
            "labels": [{"name": "enhancement"}],
        }
    }
    pr = from_git(repo.root, repo.default_branch, "feature", event=event)
    assert pr.title == "Add a thing"
    assert pr.author == "someone"
    assert pr.labels == ["enhancement"]
    assert pr.metadata_available is True


def test_explicit_body_overrides_the_event(repo) -> None:
    repo.branch("feature")
    repo.commit("Change")
    event = {"pull_request": {"title": "From event", "body": "From event"}}
    pr = from_git(repo.root, repo.default_branch, "feature", event=event, body="Override")
    assert pr.body == "Override"
    assert pr.title == "From event"


def test_total_lines_sums_the_diff(repo) -> None:
    repo.branch("feature")
    repo.commit("Change", content="a\nb\nc\n")
    pr = from_git(repo.root, repo.default_branch, "feature")
    assert pr.total_lines == pr.additions + pr.deletions


def test_load_event_reads_a_payload(tmp_path: Path) -> None:
    path = tmp_path / "event.json"
    path.write_text(json.dumps({"pull_request": {"title": "x"}}))
    assert load_event(str(path))["pull_request"]["title"] == "x"


def test_load_event_tolerates_a_missing_or_broken_file(tmp_path: Path) -> None:
    assert load_event(str(tmp_path / "absent.json")) == {}
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    assert load_event(str(broken)) == {}


def test_the_synthetic_merge_commit_of_a_pull_request_is_not_a_contributor_commit(repo) -> None:
    # On `pull_request`, actions/checkout leaves HEAD on GitHub's merge of the
    # branch into its base: a merge commit nobody signed off.
    repo.branch("feature")
    mine = repo.commit("My change\n\nSigned-off-by: A Human <human@example.com>")
    repo._git("checkout", "-q", repo.default_branch)
    repo._git("branch", "base")
    repo._git("merge", "--no-ff", "-q", "-m", "Merge feature into base", "feature")

    commits = commits_between(repo.root, "base", "HEAD")
    assert [c.sha for c in commits] == [mine]


def test_a_merge_of_the_base_back_into_the_branch_is_not_a_contributor_commit(repo) -> None:
    repo.branch("feature")
    mine = repo.commit("My change")
    repo._git("checkout", "-q", repo.default_branch)
    repo.commit("Upstream change", path="upstream.py")
    repo._git("checkout", "-q", "feature")
    repo._git("merge", "--no-ff", "-q", "-m", "Merge base into feature", repo.default_branch)

    shas = [c.sha for c in commits_between(repo.root, repo.default_branch, "feature")]
    assert shas == [mine]


def test_require_signed_off_does_not_flag_the_merge_commit(repo) -> None:
    from pr_policy.config import RuleConfig
    from pr_policy.rules import check_attribution

    repo.branch("feature")
    repo.commit("My change\n\nSigned-off-by: A Human <human@example.com>")
    repo._git("checkout", "-q", repo.default_branch)
    repo._git("branch", "base")
    repo._git("merge", "--no-ff", "-q", "-m", "Merge feature into base", "feature")

    pr = from_git(repo.root, "base", "HEAD")
    rule = RuleConfig("attribution", True, "warn", {"require_signed_off": True})
    assert list(check_attribution(pr, rule)) == []
