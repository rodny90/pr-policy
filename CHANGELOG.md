# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-09-12

First release. Two commands: `pr-policy`, which checks pull requests against the
policy a project wrote down, and `repo-ready`, which checks that the policy was
written down at all.

### Added — pr-policy

- **`attribution`** — enforces the [Linux kernel's AI attribution
  policy](https://docs.kernel.org/process/coding-assistants.html) on commit trailers:
  a coding agent must never add `Signed-off-by:` (only a human can certify the DCO),
  tool assistance belongs in `Assisted-by:` rather than `Co-authored-by:`, and
  optionally every commit must be signed off. Matching is on identities an agent
  writes about itself, never on the code.
- **`disclosure`** — checks that the project's AI-disclosure checkbox was answered.
  Either answer passes; the rule fires only when the question was ignored.
- **`template`** — checks the description is not empty and that the template's
  `<!-- ... -->` prompts were replaced.
- **`linked_issue`** — checks the body references an issue with a closing keyword.
- **`size`** — reports diffs over the project's line and file guidelines.
- **`pr-policy init`** — generates a starter config by reading `CONTRIBUTING.md`,
  the pull request template and `AGENTS.md`, quoting the line behind every
  inference so the maintainer can check the reasoning. Inference works over
  sentences, skips prohibitions ("agents must never sign off" is not a sign-off
  policy), and requires requirement-shaped language before enabling a rule.
- Reporting-only by default: nothing fails a build until `enforce: true` or `--strict`.
- Three output formats: `text` (coloured on a terminal, honouring `NO_COLOR`),
  `json`, and `markdown` for posting as a pull request comment.
- A composite GitHub Action that posts a single sticky comment and updates it on
  each push. It resolves the base branch with an explicit refspec, so it works on
  the default shallow checkout rather than only with `fetch-depth: 0`.
- Rules that read the pull request body are skipped, not failed, when no title or
  body is available — an absent body is not an empty one.
- Strict configuration validation: unknown rules and unknown options are errors,
  so a typo never quietly disables a rule.

### Added — release tooling

- A tag-driven release workflow publishing to PyPI through
  [trusted publishing](https://docs.pypi.org/trusted-publishers/), so no API token
  is stored in the repository. It refuses to publish when the tag and the packaged
  version disagree, and runs the full suite before building.
- The `v<major>` tag moves to each new release, so `uses: rodny90/pr-policy@v0`
  follows the newest 0.x.
- The action's shell logic is covered by tests that lift the `run:` block out of
  `action.yml` and execute it, rather than leaving CI to run it first.

### Added — repo-ready

- Twelve weighted repository readiness checks, an A–F grade, and a concrete
  suggested fix for every failure, ordered by weight.
- `--min-score N` to gate CI, plus `json` and `markdown` output.
- Case-insensitive file lookup that also searches `.github/` and `docs/`, and skips
  vendored directories so a dependency's tests cannot make a repository look tested.

[Unreleased]: https://github.com/rodny90/pr-policy/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/rodny90/pr-policy/releases/tag/v0.1.0
