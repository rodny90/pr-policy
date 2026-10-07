# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-10-07

### Added

- **`pr-policy replay --repo OWNER/NAME [--last N] [--config PATH]`** — checks a project's recent merged pull requests against a policy, offline and read-only, via the `gh` CLI. Prints how many PRs would have been flagged, per-rule counts, and the findings per PR. Exits 2 if `gh` is missing or not authenticated. Findings of one rule with the same message shape (for example many `Co-authored-by` commits) are folded into one line listing at most three short SHAs; per-rule counts are unchanged.

### Changed

- README, package description and action description now lead with reducing low-effort and drive-by pull requests through checks the project writes down; the AI trailer and disclosure checks are described as two of five rules. No behaviour change.

## [0.2.0] - 2026-10-07

### Added

- **repo-ready `agents-md` check** — passes when the repository root has `AGENTS.md`
  or a tool-specific equivalent (`CLAUDE.md`, `GEMINI.md`, `.cursorrules`,
  `.github/copilot-instructions.md`). Worth 2 points, with a fix hint saying what
  the file should contain. This repository now has an `AGENTS.md` of its own.
- `examples/` with three copy-paste workflows (minimal, strict, custom config)
  pinned to `@v0`, and an annotated sample `pr-policy.yml`. A test keeps them
  valid.

### Changed

- The action's comment step no longer fails the job when it cannot write the comment, as on
  pull requests from forks (read-only token, HTTP 403). It logs a `::warning::` explaining
  why and what to do, and the job's result still comes only from the check's exit code.
  Failures of the check itself are not affected.
- The action posts its comment only on `pull_request` events, and the fork-PR warning now
  points at a `workflow_run` split rather than `pull_request_target`, which would hand a
  write token to a job that checks out the fork.
- The `exit-code` output documents `2` (bad configuration, revision or missing base).
- The `Changelog` URL in the package metadata pointed at `blob/main`; it now points at
  `blob/master`, the repository's default branch.
- repo-ready weights: `changelog` and `code-of-conduct` drop from 5 to 4 points to
  make room for `agents-md`. A repository's score can move by a point.
- The action is now named `pr-policy gate` with a shorter description, for the
  GitHub Marketplace listing. The `uses: rodny90/pr-policy@v0` reference is unchanged.
- README leads with a 30-second install, the real sticky-comment format, a
  comparison with related tools, and a reference for the action's inputs and outputs.

### Fixed

- Commit checks skip merge commits. On `pull_request` events the checkout is GitHub's
  synthetic merge of the branch into its base, which `require_signed_off` flagged on
  every pull request in projects that run the DCO.
- `attribution` matches agent names as whole words, so "Jo Raider" is no longer read as
  `aider`. A name followed by what reads as a surname, on an ordinary address ("Claude
  Dupont <claude@dupont.example>"), is treated as a person. Addresses such as
  `noreply@anthropic.com` still match anywhere, so real agent trailers are caught as before.
- Markdown output puts the contributor's `Signed-off-by` text in a code span. Before, a
  trailer could inject live `@mentions` and links into the bot's comment.
- `--format markdown` no longer crashes with `UnicodeEncodeError` when stdout uses a
  legacy Windows code page: it writes UTF-8.
- The action no longer overwrites a good sticky comment with a bare marker when the check
  fails with exit code 2: with no report there is nothing to post. A markdown report that
  comes out empty is removed and reported with a warning instead of being hidden.
- The sticky-comment lookup only considers comments by `github-actions[bot]` and only
  updates the first match, so a quoted marker or a second page of comments cannot redirect it.
- `pr-policy init` now requires requirement-shaped language before it enables
  `disclosure` or `linked_issue`, as the 0.1.0 notes already claimed. Before, any
  non-negated mention of AI tools or of issues switched the rule on ("You may use AI
  tools here." enabled `disclosure`). A sentence now has to ask for something: must,
  required, mandatory, please, should, have/need/expected to, or an imperative such as
  "Link the issue" or "Disclose AI use". "Welcome" and "always" do not count. In the
  pull request template, a checkbox item about the subject counts as the question being
  asked, as does a heading such as "Generative AI" for `disclosure`; negated answer
  options ("I did not use AI") are no longer discarded there. `require_signed_off` shares
  the same wording rules, so "we use the DCO" alone no longer enables it.
- `disclosure` recognises every box `init` can enable it from. The default
  `checkbox_patterns` now accept any label that mentions AI (and `llm`, `copilot`,
  `chatgpt`, `claude`, `codex`), where before `init` could enable the rule on wording the
  rule then failed to see as ticked. For templates that ask in prose under an AI heading,
  the rule passes while that section is kept and reports the body when it is deleted.
  `checkbox_patterns` is documented in the README.
- `pr-policy init` no longer strips leading `x`/`X` letters from the line it quotes
  ("Xcode users must ...").
- `repo-ready`'s `agents-md` check accepts only `.md` or extensionless names, so
  `claude.png` or `agents.txt` no longer pass for an instructions file.

## [0.1.0] - 2026-10-07

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

[Unreleased]: https://github.com/rodny90/pr-policy/compare/v0.2.0...HEAD
[0.3.0]: https://github.com/rodny90/pr-policy/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/rodny90/pr-policy/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/rodny90/pr-policy/releases/tag/v0.1.0
