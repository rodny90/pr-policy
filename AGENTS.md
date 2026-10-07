# AGENTS.md

Instructions for coding agents working in this repository. Humans: see [CONTRIBUTING.md](CONTRIBUTING.md).

## What this is

Two small Python tools in one package (Python 3.9+):

- `src/pr_policy/` — `pr-policy`, a deterministic pull request policy gate. Rules are in `rules.py`, defaults in `config.py`, output formats in `report.py` and `cli.py`. The GitHub Action is `action.yml`.
- `src/repo_ready/` — `repo-ready`, a repository hygiene scorer. Checks are in `checks.py`.

## Setup and checks

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
ruff check .
ruff format --check .
repo-ready . --min-score 100
```

CI runs exactly these. Run all of them before you finish; `ruff format .` fixes formatting.

## Conventions

- Match the surrounding style. Line length is 100; keep `from __future__ import annotations` at the top of modules so the code stays valid on Python 3.9.
- `pr-policy` rules must stay deterministic. A rule may check that a trailer exists or a box is ticked; it must never try to infer whether a human or a model wrote something.
- `repo-ready` makes no network calls and has no dependencies besides the standard library. Keep it that way.
- Every new `repo-ready` check needs a concrete `fix` hint, and the check weights must total 100.
- Add tests for the passing and the failing case. User-visible changes get a line under `Unreleased` in `CHANGELOG.md`.
- The JSON output shapes are scripted against. Do not change them without a changelog note.
- `examples/` is copied into other repositories and tested; keep it pointing at `rodny90/pr-policy@v0`.

## Commits and pull requests

- Record tool assistance with an `Assisted-by:` trailer, for example `Assisted-by: Claude:claude-opus-5`, as described in CONTRIBUTING.md.
- Never add a `Signed-off-by:` trailer. Only a human can certify the DCO.
- Do not use `Co-authored-by:` for a tool.
- Do not tag, publish or push to the default branch; releases follow [docs/releasing.md](docs/releasing.md).
- Whoever opens the pull request is responsible for its content. Answer the AI-disclosure checkbox in the template.
