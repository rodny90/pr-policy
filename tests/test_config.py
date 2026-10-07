"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from pr_policy.config import DEFAULTS, ConfigError, default_config, find_config, load_config


def test_defaults_cover_every_rule() -> None:
    config = default_config()
    assert set(config.rules) == set(DEFAULTS)


def test_default_posture_is_reporting_only() -> None:
    assert default_config().enforce is False


def test_attribution_is_on_by_default_and_sign_off_is_not() -> None:
    rule = default_config().rule("attribution")
    assert rule.enabled
    assert rule.get("forbid_agent_sign_off") is True
    assert rule.get("require_signed_off") is False


def test_missing_config_falls_back_to_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    assert config.source is None
    assert config.enforce is False


def test_loads_from_dot_github(tmp_path: Path) -> None:
    target = tmp_path / ".github" / "pr-policy.yml"
    target.parent.mkdir()
    target.write_text("version: 1\nenforce: true\n")
    config = load_config(tmp_path)
    assert config.enforce is True
    assert config.source == str(target)


def test_find_config_prefers_dot_github(tmp_path: Path) -> None:
    (tmp_path / "pr-policy.yml").write_text("version: 1\n")
    target = tmp_path / ".github" / "pr-policy.yml"
    target.parent.mkdir()
    target.write_text("version: 1\n")
    assert find_config(tmp_path) == target


def test_rule_options_merge_over_defaults(tmp_path: Path) -> None:
    (tmp_path / "pr-policy.yml").write_text(
        "rules:\n  size:\n    max_lines: 50\n",
    )
    rule = load_config(tmp_path).rule("size")
    assert rule.get("max_lines") == 50
    assert rule.get("max_files") == DEFAULTS["size"]["max_files"]
    assert rule.enabled is True


def test_boolean_shorthand_disables_a_rule(tmp_path: Path) -> None:
    (tmp_path / "pr-policy.yml").write_text("rules:\n  size: false\n")
    assert load_config(tmp_path).rule("size").enabled is False


def test_unknown_rule_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "pr-policy.yml").write_text("rules:\n  nonsense:\n    enabled: true\n")
    with pytest.raises(ConfigError, match="unknown rule"):
        load_config(tmp_path)


def test_unknown_option_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "pr-policy.yml").write_text("rules:\n  size:\n    max_liness: 10\n")
    with pytest.raises(ConfigError, match="unknown option"):
        load_config(tmp_path)


def test_unknown_top_level_key_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "pr-policy.yml").write_text("enforcee: true\n")
    with pytest.raises(ConfigError, match="unknown top-level"):
        load_config(tmp_path)


def test_bad_severity_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "pr-policy.yml").write_text("rules:\n  size:\n    severity: loud\n")
    with pytest.raises(ConfigError, match="severity"):
        load_config(tmp_path)


def test_invalid_yaml_is_reported(tmp_path: Path) -> None:
    (tmp_path / "pr-policy.yml").write_text("rules: [unclosed\n")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_config(tmp_path)


def test_non_mapping_top_level_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "pr-policy.yml").write_text("- a\n- b\n")
    with pytest.raises(ConfigError, match="must be a mapping"):
        load_config(tmp_path)


def test_explicit_missing_path_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="no such configuration file"):
        load_config(tmp_path, tmp_path / "absent.yml")


def test_empty_config_file_is_valid(tmp_path: Path) -> None:
    (tmp_path / "pr-policy.yml").write_text("")
    assert load_config(tmp_path).enforce is False
