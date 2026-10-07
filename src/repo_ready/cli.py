"""Command line interface for repo-ready."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from repo_ready import __version__
from repo_ready.checks import Report, audit

PASS_MARK = "PASS"
FAIL_MARK = "FAIL"


class Style:
    """ANSI colours, disabled when the output is not an interactive terminal."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def green(self, text: str) -> str:
        return self._wrap("32", text)

    def red(self, text: str) -> str:
        return self._wrap("31", text)

    def yellow(self, text: str) -> str:
        return self._wrap("33", text)

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)


def _colour_enabled(stream) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def render_text(report: Report, style: Style, show_fixes: bool = True) -> str:
    lines = [style.bold(f"repo-ready  {report.path}"), ""]
    width = max(len(r.title) for r in report.results)
    for result in report.results:
        mark = style.green(PASS_MARK) if result.passed else style.red(FAIL_MARK)
        lines.append(f"  {mark}  {result.title.ljust(width)}  {style.dim(result.detail)}")

    score = report.score
    paint = style.green if score >= 75 else style.yellow if score >= 40 else style.red
    lines += ["", paint(style.bold(f"Score: {score}/100  (grade {report.grade})"))]

    if show_fixes and report.failed:
        lines += ["", style.bold("Fix these first:")]
        for result in report.failed:
            lines.append(f"  [{result.weight:>2} pts] {result.title}")
            lines.append(f"           {style.dim(result.fix)}")
    return "\n".join(lines)


def render_markdown(report: Report) -> str:
    lines = [
        f"### repo-ready: {report.score}/100 (grade {report.grade})",
        "",
        "| | Check | Detail |",
        "| --- | --- | --- |",
    ]
    for result in report.results:
        icon = "✅" if result.passed else "❌"
        lines.append(f"| {icon} | {result.title} | {result.detail} |")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repo-ready",
        description="Score a repository on the things contributors and users look for.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="path to the repository (default: the current directory)",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="output format (default: text)",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=0,
        metavar="N",
        help="exit with status 1 if the score is below N, for use as a CI gate",
    )
    parser.add_argument(
        "--no-fixes",
        action="store_true",
        help="omit the suggested fixes from text output",
    )
    parser.add_argument("--version", action="version", version=f"repo-ready {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.path.is_dir():
        print(f"repo-ready: {args.path} is not a directory", file=sys.stderr)
        return 2

    report = audit(args.path)

    if args.format == "json":
        print(report.to_json())
    elif args.format == "markdown":
        print(render_markdown(report))
    else:
        style = Style(_colour_enabled(sys.stdout))
        print(render_text(report, style, show_fixes=not args.no_fixes))

    return 1 if report.score < args.min_score else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
