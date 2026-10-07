"""The checks that make up a repo-ready audit.

Every check is a pure function from a :class:`Repo` to a :class:`Result`, so
each one can be tested in isolation and new checks can be added by appending to
:data:`CHECKS`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# Directories that never contain a project's own source or docs. Skipped when
# looking for tests so that a vendored dependency cannot fake a passing check.
IGNORED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".tox",
        ".venv",
        ".mypy_cache",
        ".pytest_cache",
        "__pycache__",
        "node_modules",
        "vendor",
        "third_party",
        "build",
        "dist",
        "target",
        "site-packages",
    }
)


class Repo:
    """Read-only view of a repository on disk.

    Lookups are case-insensitive because the filesystem may or may not be, and
    ``LICENSE``, ``License`` and ``license.md`` are all equally valid to GitHub.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def find(self, *stems: str, dirs: Sequence[str] = (".", ".github", "docs")) -> Path | None:
        """Return the first file whose name (minus extension) matches a stem."""
        wanted = {stem.lower() for stem in stems}
        for directory in dirs:
            base = self.root / directory
            if not base.is_dir():
                continue
            for entry in sorted(base.iterdir()):
                if entry.is_file() and entry.stem.lower() in wanted:
                    return entry
        return None

    def read(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def walk(self) -> Iterable[Path]:
        """Yield every file in the repo, skipping vendored and cache dirs."""
        stack = [self.root]
        while stack:
            current = stack.pop()
            try:
                entries = sorted(current.iterdir())
            except OSError:
                continue
            for entry in entries:
                if entry.is_dir():
                    if entry.name not in IGNORED_DIRS:
                        stack.append(entry)
                elif entry.is_file():
                    yield entry

    def rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)


@dataclass(frozen=True)
class Result:
    """The outcome of running one check against one repository."""

    id: str
    title: str
    passed: bool
    weight: int
    detail: str
    fix: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "passed": self.passed,
            "weight": self.weight,
            "detail": self.detail,
            "fix": self.fix,
        }


@dataclass(frozen=True)
class Check:
    id: str
    title: str
    weight: int
    fix: str
    run: Callable[[Repo], tuple[bool, str]]

    def __call__(self, repo: Repo) -> Result:
        passed, detail = self.run(repo)
        return Result(
            id=self.id,
            title=self.title,
            passed=passed,
            weight=self.weight,
            detail=detail,
            fix="" if passed else self.fix,
        )


@dataclass(frozen=True)
class Report:
    """The full audit of a repository."""

    path: str
    results: list[Result] = field(default_factory=list)

    @property
    def score(self) -> int:
        total = sum(r.weight for r in self.results)
        if total == 0:
            return 0
        earned = sum(r.weight for r in self.results if r.passed)
        return round(earned * 100 / total)

    @property
    def passed(self) -> list[Result]:
        return [r for r in self.results if r.passed]

    @property
    def failed(self) -> list[Result]:
        # Heaviest failures first: that is the order worth fixing them in.
        return sorted((r for r in self.results if not r.passed), key=lambda r: -r.weight)

    @property
    def grade(self) -> str:
        score = self.score
        if score >= 90:
            return "A"
        if score >= 75:
            return "B"
        if score >= 60:
            return "C"
        if score >= 40:
            return "D"
        return "F"

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "score": self.score,
            "grade": self.grade,
            "checks": [r.as_dict() for r in self.results],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.as_dict(), indent=indent)


# --------------------------------------------------------------------------
# Individual checks
# --------------------------------------------------------------------------

MIN_README_CHARS = 300

TEST_DIR_NAMES = frozenset({"test", "tests", "spec", "specs", "__tests__"})
TEST_FILE_PATTERN = re.compile(
    r"(^test_.*\.py$|.*_test\.(py|go|rb|rs)$|.*\.(test|spec)\.(js|jsx|ts|tsx)$)"
)

CI_FILES = (
    ".gitlab-ci.yml",
    ".travis.yml",
    "azure-pipelines.yml",
    ".circleci/config.yml",
)

MANIFESTS = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "Gemfile",
    "composer.json",
)


def _check_license(repo: Repo) -> tuple[bool, str]:
    found = repo.find("license", "licence", "copying")
    if found is None:
        return False, "no LICENSE file found"
    if len(repo.read(found).strip()) < 100:
        return False, f"{repo.rel(found)} looks empty or truncated"
    return True, f"found {repo.rel(found)}"


def _check_readme(repo: Repo) -> tuple[bool, str]:
    found = repo.find("readme")
    if found is None:
        return False, "no README file found"
    length = len(repo.read(found).strip())
    if length < MIN_README_CHARS:
        return False, f"{repo.rel(found)} is only {length} characters"
    return True, f"found {repo.rel(found)} ({length} characters)"


def _check_readme_sections(repo: Repo) -> tuple[bool, str]:
    found = repo.find("readme")
    if found is None:
        return False, "no README file to inspect"
    text = repo.read(found).lower()
    missing = []
    if not re.search(r"\b(install|installation|getting started|setup)\b", text):
        missing.append("an install")
    if not re.search(r"\b(usage|example|examples|quick ?start)\b", text):
        missing.append("a usage")
    if missing:
        return False, "README is missing " + " and ".join(missing) + " section"
    return True, "README documents installation and usage"


def _check_manifest(repo: Repo) -> tuple[bool, str]:
    for name in MANIFESTS:
        candidate = repo.root / name
        if candidate.is_file():
            return True, f"found {name}"
    return False, "no package manifest found"


def _check_tests(repo: Repo) -> tuple[bool, str]:
    for path in repo.walk():
        if path.parent.name.lower() in TEST_DIR_NAMES and path.suffix:
            return True, f"found tests in {repo.rel(path.parent)}/"
        if TEST_FILE_PATTERN.match(path.name):
            return True, f"found {repo.rel(path)}"
    return False, "no test files found"


def _check_ci(repo: Repo) -> tuple[bool, str]:
    workflows = repo.root / ".github" / "workflows"
    if workflows.is_dir():
        files = [p for p in sorted(workflows.iterdir()) if p.suffix in {".yml", ".yaml"}]
        if files:
            return True, f"found {len(files)} GitHub Actions workflow(s)"
    for name in CI_FILES:
        if (repo.root / name).is_file():
            return True, f"found {name}"
    return False, "no CI configuration found"


def _presence_check(*stems: str, label: str) -> Callable[[Repo], tuple[bool, str]]:
    def run(repo: Repo) -> tuple[bool, str]:
        found = repo.find(*stems)
        if found is None:
            return False, f"no {label} found"
        return True, f"found {repo.rel(found)}"

    return run


def _check_gitignore(repo: Repo) -> tuple[bool, str]:
    path = repo.root / ".gitignore"
    if not path.is_file():
        return False, "no .gitignore found"
    return True, "found .gitignore"


def _check_issue_templates(repo: Repo) -> tuple[bool, str]:
    directory = repo.root / ".github" / "ISSUE_TEMPLATE"
    if directory.is_dir() and any(directory.iterdir()):
        return True, "found .github/ISSUE_TEMPLATE/"
    if repo.find("issue_template", dirs=(".github", ".")) is not None:
        return True, "found an issue template"
    return False, "no issue template found"


CHECKS: tuple[Check, ...] = (
    Check(
        id="license",
        title="Has a LICENSE",
        weight=15,
        fix=(
            "Add a LICENSE file. Pick one at https://choosealicense.com — "
            "MIT and Apache-2.0 are the safe defaults."
        ),
        run=_check_license,
    ),
    Check(
        id="readme",
        title="Has a substantial README",
        weight=15,
        fix=(
            f"Write a README of at least {MIN_README_CHARS} characters explaining "
            "what the project does and who it is for."
        ),
        run=_check_readme,
    ),
    Check(
        id="readme-sections",
        title="README covers install and usage",
        weight=5,
        fix="Add an Installation section and a Usage section with at least one runnable example.",
        run=_check_readme_sections,
    ),
    Check(
        id="tests",
        title="Has automated tests",
        weight=15,
        fix=(
            "Add a tests/ directory. Even three tests of the happy path tell "
            "contributors what 'working' means."
        ),
        run=_check_tests,
    ),
    Check(
        id="ci",
        title="Runs CI on every push",
        weight=15,
        fix=("Add a .github/workflows/ci.yml that installs the project and runs the test suite."),
        run=_check_ci,
    ),
    Check(
        id="contributing",
        title="Has CONTRIBUTING guidance",
        weight=8,
        fix=(
            "Add CONTRIBUTING.md describing how to set up the project, run tests "
            "and open a pull request."
        ),
        run=_presence_check("contributing", label="CONTRIBUTING file"),
    ),
    Check(
        id="security",
        title="Has a security policy",
        weight=7,
        fix="Add SECURITY.md telling people where to report vulnerabilities privately.",
        run=_presence_check("security", label="SECURITY file"),
    ),
    Check(
        id="manifest",
        title="Has a package manifest",
        weight=5,
        fix=(
            "Add a manifest (pyproject.toml, package.json, Cargo.toml, ...) so the "
            "project can be installed rather than copied."
        ),
        run=_check_manifest,
    ),
    Check(
        id="changelog",
        title="Has a CHANGELOG",
        weight=5,
        fix="Add CHANGELOG.md and record user-visible changes under each released version.",
        run=_presence_check("changelog", "changes", "history", label="CHANGELOG file"),
    ),
    Check(
        id="code-of-conduct",
        title="Has a code of conduct",
        weight=5,
        fix="Add CODE_OF_CONDUCT.md. The Contributor Covenant is the usual choice.",
        run=_presence_check("code_of_conduct", "code-of-conduct", label="CODE_OF_CONDUCT file"),
    ),
    Check(
        id="gitignore",
        title="Has a .gitignore",
        weight=3,
        fix="Add a .gitignore so build output and local caches stay out of the history.",
        run=_check_gitignore,
    ),
    Check(
        id="issue-templates",
        title="Has an issue template",
        weight=2,
        fix=(
            "Add .github/ISSUE_TEMPLATE/bug_report.md so bug reports arrive with "
            "the details you need."
        ),
        run=_check_issue_templates,
    ),
)


def audit(root: Path, checks: Sequence[Check] = CHECKS) -> Report:
    """Run every check against ``root`` and collect the results."""
    repo = Repo(root)
    return Report(path=str(root), results=[check(repo) for check in checks])
