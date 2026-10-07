"""Configuration loading for pr-policy.

The configuration is deliberately small. Every rule has an ``enabled`` flag, a
``severity``, and its own options; anything not set falls back to the defaults
below. Defaults are chosen so that a repository which installs pr-policy and
writes no configuration at all gets useful signal without ever failing a build.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATHS = (
    ".github/pr-policy.yml",
    ".github/pr-policy.yaml",
    "pr-policy.yml",
    "pr-policy.yaml",
)

SEVERITIES = ("error", "warn", "info")

# Identity fragments that coding agents put in their own commit trailers.
# This is not AI detection: it matches text the agent writes about itself, and
# a contributor who does not want to be matched simply does not add the trailer.
AGENT_IDENTITIES = (
    "claude",
    "copilot",
    "codex",
    "chatgpt",
    "cursor",
    "devin",
    "aider",
    "gemini",
    "windsurf",
    "amazon q",
    "noreply@anthropic.com",
    "noreply@openai.com",
)

DEFAULTS: dict[str, dict[str, Any]] = {
    "attribution": {
        "enabled": True,
        "severity": "warn",
        # The kernel policy: agents must never certify the DCO.
        "forbid_agent_sign_off": True,
        # Prefer `Assisted-by:` over `Co-authored-by:` for tool assistance.
        "prefer_assisted_by": True,
        # Off by default: only projects that actually run the DCO want this.
        "require_signed_off": False,
        "agent_identities": list(AGENT_IDENTITIES),
    },
    "disclosure": {
        "enabled": False,
        "severity": "warn",
        # Any one of these, present and ticked, satisfies the rule.
        "checkbox_patterns": [
            r"generative ai",
            r"\bai\b.*(tool|assist|generat)",
            r"(tool|assist|generat).*\bai\b",
        ],
    },
    "template": {
        "enabled": True,
        "severity": "warn",
        "min_body_chars": 30,
        "forbid_unedited_comments": True,
    },
    "linked_issue": {
        "enabled": False,
        "severity": "warn",
        "keywords": ["closes", "fixes", "resolves", "refs", "part of"],
    },
    "size": {
        "enabled": True,
        "severity": "info",
        "max_lines": 1000,
        "max_files": 100,
    },
}


class ConfigError(ValueError):
    """Raised when a configuration file is present but cannot be used."""


@dataclass(frozen=True)
class RuleConfig:
    name: str
    enabled: bool
    severity: str
    options: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, fallback: Any = None) -> Any:
        return self.options.get(key, fallback)


@dataclass(frozen=True)
class Config:
    enforce: bool = False
    rules: dict[str, RuleConfig] = field(default_factory=dict)
    source: str | None = None

    def rule(self, name: str) -> RuleConfig:
        return self.rules[name]


def _merge(name: str, defaults: dict[str, Any], overrides: Any) -> RuleConfig:
    if overrides is None:
        overrides = {}
    if isinstance(overrides, bool):  # `attribution: false` is a natural shorthand
        overrides = {"enabled": overrides}
    if not isinstance(overrides, dict):
        raise ConfigError(f"rule '{name}' must be a mapping or a boolean")

    unknown = set(overrides) - set(defaults)
    if unknown:
        raise ConfigError(f"rule '{name}' has unknown option(s): {', '.join(sorted(unknown))}")

    merged = {**defaults, **overrides}
    severity = merged["severity"]
    if severity not in SEVERITIES:
        raise ConfigError(
            f"rule '{name}' has severity '{severity}', expected one of {', '.join(SEVERITIES)}"
        )

    options = {k: v for k, v in merged.items() if k not in ("enabled", "severity")}
    return RuleConfig(
        name=name, enabled=bool(merged["enabled"]), severity=severity, options=options
    )


def default_config() -> Config:
    return Config(
        enforce=False,
        rules={name: _merge(name, defaults, {}) for name, defaults in DEFAULTS.items()},
    )


def find_config(root: Path) -> Path | None:
    for candidate in CONFIG_PATHS:
        path = root / candidate
        if path.is_file():
            return path
    return None


def load_config(root: Path, explicit: Path | None = None) -> Config:
    """Load configuration from ``explicit``, or from the first conventional path."""
    path = explicit or find_config(root)
    if path is None:
        return default_config()
    if not path.is_file():
        raise ConfigError(f"no such configuration file: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top level must be a mapping")

    unknown_top = set(raw) - {"version", "enforce", "rules"}
    if unknown_top:
        raise ConfigError(f"{path}: unknown top-level key(s): {', '.join(sorted(unknown_top))}")

    rules_raw = raw.get("rules") or {}
    if not isinstance(rules_raw, dict):
        raise ConfigError(f"{path}: 'rules' must be a mapping")

    unknown_rules = set(rules_raw) - set(DEFAULTS)
    if unknown_rules:
        raise ConfigError(f"{path}: unknown rule(s): {', '.join(sorted(unknown_rules))}")

    rules = {
        name: _merge(name, defaults, rules_raw.get(name)) for name, defaults in DEFAULTS.items()
    }
    return Config(enforce=bool(raw.get("enforce", False)), rules=rules, source=str(path))
