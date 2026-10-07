"""Command line interface for pr-policy."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from pr_policy import __version__
from pr_policy.config import DEFAULTS, ConfigError, load_config
from pr_policy.context import GitError, from_git, load_event
from pr_policy.infer import render, scan
from pr_policy.report import ERROR, INFO, WARN, Report, summarise
from pr_policy.rules import evaluate

MARKS = {ERROR: "error", WARN: "warn", INFO: "info"}
COLOURS = {ERROR: "31", WARN: "33", INFO: "36"}


class Style:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def paint(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def severity(self, severity: str) -> str:
        return self.paint(COLOURS.get(severity, "0"), MARKS.get(severity, severity))

    def bold(self, text: str) -> str:
        return self.paint("1", text)

    def dim(self, text: str) -> str:
        return self.paint("2", text)

    def green(self, text: str) -> str:
        return self.paint("32", text)


def _colour_enabled(stream) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def render_text(report: Report, style: Style, skipped: list[str]) -> str:
    lines = [style.bold("pr-policy"), ""]

    if report.clean:
        lines.append(style.green("  No findings. This pull request follows the policy."))
    else:
        for finding in report.ordered:
            lines.append(f"  {style.severity(finding.severity)}  {finding.message}")
            if finding.hint:
                lines.append(f"        {style.dim(finding.hint)}")
            lines.append("")
        lines.pop()

    lines += ["", style.dim(f"  rules run: {', '.join(report.checked) or 'none'}")]
    if skipped:
        lines.append(
            style.dim(f"  skipped (no pull request title or body available): {', '.join(skipped)}")
        )
    lines.append(f"  {summarise(report)}")

    if report.errors and not report.enforce:
        lines.append(
            style.dim("  reporting only — set 'enforce: true' to fail the build on errors")
        )
    return "\n".join(lines)


def render_markdown(report: Report, skipped: list[str]) -> str:
    """A comment body suitable for posting on the pull request."""
    if report.clean:
        return (
            "### pr-policy\n\nNo findings — this pull request follows the project's "
            "contribution policy.\n"
        )

    icons = {ERROR: "🔴", WARN: "🟡", INFO: "🔵"}
    lines = ["### pr-policy", "", f"Found {summarise(report)}.", ""]
    for finding in report.ordered:
        lines.append(f"- {icons.get(finding.severity, '•')} **{finding.message}**")
        if finding.hint:
            lines.append(f"  {finding.hint}")
    lines.append("")
    lines.append(
        f"<sub>Rules run: {', '.join(report.checked) or 'none'}."
        + (f" Skipped: {', '.join(skipped)}." if skipped else "")
        + " These are signals for the maintainer, not a verdict on your change.</sub>"
    )
    return "\n".join(lines) + "\n"


def _add_check_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    parser.add_argument("--base", default="origin/HEAD", help="base ref to compare against")
    parser.add_argument("--head", default="HEAD", help="head ref of the pull request")
    parser.add_argument("--config", type=Path, default=None, help="path to pr-policy.yml")
    parser.add_argument("--title", default=None, help="pull request title")
    parser.add_argument(
        "--body-file",
        type=Path,
        default=None,
        help="file holding the pull request body, or - for stdin",
    )
    parser.add_argument("-f", "--format", choices=("text", "json", "markdown"), default="text")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail on error findings even if the configuration does not enforce",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pr-policy",
        description=(
            "Check a pull request against the contribution policy the project "
            "wrote down. Deterministic: it never tries to detect AI."
        ),
    )
    parser.add_argument("--version", action="version", version=f"pr-policy {__version__}")
    sub = parser.add_subparsers(dest="command")

    check = sub.add_parser("check", help="check a pull request against the policy")
    _add_check_arguments(check)

    init = sub.add_parser(
        "init", help="write a starter config inferred from CONTRIBUTING.md and the PR template"
    )
    init.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    init.add_argument(
        "--stdout", action="store_true", help="print the configuration instead of writing it"
    )
    init.add_argument("--force", action="store_true", help="overwrite an existing config")
    return parser


def run_check(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.repo, args.config)
    except ConfigError as exc:
        print(f"pr-policy: {exc}", file=sys.stderr)
        return 2

    body = None
    if args.body_file is not None:
        try:
            # Read rather than stat: the body often arrives through a pipe or a
            # process substitution, neither of which is a regular file.
            if str(args.body_file) == "-":
                body = sys.stdin.read()
            else:
                body = args.body_file.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"pr-policy: cannot read {args.body_file}: {exc.strerror}", file=sys.stderr)
            return 2

    try:
        pr = from_git(
            args.repo, args.base, args.head, event=load_event(), title=args.title, body=body
        )
    except GitError as exc:
        print(f"pr-policy: {exc}", file=sys.stderr)
        return 2

    findings, checked, skipped = evaluate(pr, config)
    report = Report(findings=findings, enforce=config.enforce or args.strict, checked=checked)

    if args.format == "json":
        print(report.to_json())
    elif args.format == "markdown":
        print(render_markdown(report, skipped), end="")
    else:
        print(render_text(report, Style(_colour_enabled(sys.stdout)), skipped))
    return report.exit_code


def run_init(args: argparse.Namespace) -> int:
    if not args.repo.is_dir():
        print(f"pr-policy: {args.repo} is not a directory", file=sys.stderr)
        return 2

    signals = scan(args.repo)
    content = render(args.repo, signals, DEFAULTS)

    if args.stdout:
        print(content, end="")
        return 0

    target = args.repo / ".github" / "pr-policy.yml"
    if target.exists() and not args.force:
        print(f"pr-policy: {target} already exists (use --force to overwrite)", file=sys.stderr)
        return 2

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    print(f"Wrote {target}")
    if signals:
        print("\nInferred from this project's own documentation:")
        for signal in signals:
            print(f"  {signal.rule}.{signal.option}  <-  {signal.source}")
    else:
        print("\nNo project-specific policy found; wrote the defaults.")
    print("\nReview it, then run: pr-policy check --base origin/main")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "check":
        return run_check(args)
    if args.command == "init":
        return run_init(args)
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
