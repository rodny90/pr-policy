"""repo-ready: score a repository's open-source readiness."""

from repo_ready.checks import CHECKS, Check, Report, Result, audit

__version__ = "0.1.0"

__all__ = ["CHECKS", "Check", "Report", "Result", "audit", "__version__"]
