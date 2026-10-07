"""The examples are copied verbatim into other repositories, so they must stay valid."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pr_policy.config import load_config

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
WORKFLOWS = sorted(EXAMPLES.glob("pr-policy-*.yml"))


def action_inputs() -> set[str]:
    return set(yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))["inputs"])


def uses_steps(path: Path) -> list[dict]:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    steps = [step for job in workflow["jobs"].values() for step in job["steps"]]
    return [step for step in steps if str(step.get("uses", "")).startswith("rodny90/pr-policy")]


def test_there_are_workflow_examples() -> None:
    assert len(WORKFLOWS) >= 3


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_uses_the_moving_major_tag(path: Path) -> None:
    steps = uses_steps(path)
    assert len(steps) == 1
    assert steps[0]["uses"] == "rodny90/pr-policy@v0"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_passes_only_inputs_the_action_declares(path: Path) -> None:
    (step,) = uses_steps(path)
    assert set(step.get("with", {})) <= action_inputs()


def test_sample_config_is_valid() -> None:
    config = load_config(EXAMPLES, EXAMPLES / "pr-policy.yml")
    assert config.source is not None
    assert config.enforce is False
