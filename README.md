# pr-policy

[![CI](https://github.com/rodny90/pr-policy/actions/workflows/ci.yml/badge.svg)](https://github.com/rodny90/pr-policy/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pr-policy.svg)](https://pypi.org/project/pr-policy/)
[![Python versions](https://img.shields.io/pypi/pyversions/pr-policy.svg)](https://pypi.org/project/pr-policy/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Check pull requests against the contribution policy your project already wrote down.**

`pr-policy` does not try to work out whether a human or a model wrote the code. It checks something it can actually know: whether the submission follows the rules in your `CONTRIBUTING.md` and your pull request template.

```
pr-policy

  warn  commit 4ea6a851 has 'Signed-off-by: Claude <noreply@anthropic.com>', which names a coding agent (claude)
        Only a human can certify the DCO. Sign off as yourself and record the tool with 'Assisted-by: <tool>:<model>'.

  warn  the AI-disclosure checkbox in the pull request template is not ticked
        Tick the option that applies. Either answer is accepted — the box only needs to be answered.

  warn  the pull request body does not reference an issue
        This project asks for an issue first. Add a line such as 'Closes #123' so the discussion and the change stay linked.

  rules run: attribution, disclosure, template, linked_issue, size
  3 warn
```

## Why this exists

Maintainers are being buried in contributions, and the tools arriving to help are mostly **throttles**: cap the number of open pull requests, restrict them to collaborators, turn them off. Those control *how many* submissions arrive. Nothing checks whether an arriving submission follows the rules the project published.

The gap is concrete. GitHub's issue forms have supported required fields and per-field validation for years; [issue forms are not supported for pull requests](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/about-issue-and-pull-request-templates). A pull request template is inert markdown. A contributor can delete the whole thing — including the AI-disclosure checkbox your project added — and nothing notices.

Projects have written the policies. MicroPython and ESLint require an AI declaration. The [Linux kernel](https://docs.kernel.org/process/coding-assistants.html) requires an `Assisted-by:` trailer and forbids agents from adding `Signed-off-by:`, because only a human can certify the DCO. `pr-policy` is the enforcement half those policies never got.

## Design

Three commitments, and the tool is built around them:

**It never tries to detect AI.** Detection is an arms race — any classifier good enough to identify AI output can be used to train past it — and maintainers have said plainly that they do not want a tool adjudicating authorship. Every rule here is deterministic: a trailer is present or it is not, a checkbox is ticked or it is not.

**It routes on disclosure and never judges it.** If your template asks whether AI was used, *either* answer passes. The rule fires when the question was ignored, not when it was answered in a way someone dislikes.

**It reports signals, not verdicts.** Nothing fails a build until you set `enforce: true`. The default posture is a comment on the pull request telling the maintainer what to look at, leaving the judgement where it belongs.

## Installation

```bash
pip install pr-policy
```

Or without installing anything:

```bash
pipx run pr-policy check --base origin/main
```

Requires Python 3.9 or newer.

## Quick start

### 1. Generate a config from your own documentation

```bash
pr-policy init
```

`init` reads your `CONTRIBUTING.md`, your pull request template and your `AGENTS.md`, and turns the enforceable parts into configuration — **quoting the line it relied on**, so you check the reasoning rather than trust it:

```yaml
rules:
  attribution:
    enabled: true
    severity: "warn"
    forbid_agent_sign_off: true
    prefer_assisted_by: true
    # CONTRIBUTING.md:31 — "All commits must carry a sign-off under the DCO: use `git commit -s`."
    require_signed_off: true

  disclosure:
    # .github/PULL_REQUEST_TEMPLATE.md:14 — "I used generative AI tools, and a human reviewed the result"
    enabled: true
    severity: "warn"
```

Inference is a heuristic and it will sometimes be wrong. That is exactly why it shows its evidence — read the file before you commit it.

### 2. Run it in CI

```yaml
name: pr-policy
on: pull_request

jobs:
  policy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # commit trailers need the branch history
      - uses: rodny90/pr-policy@v0
```

That posts a single sticky comment on the pull request and updates it on every push. It will not fail the job until your config says to.

`@v0` follows the newest 0.x release. Pin an exact tag (`@v0.1.0`) if you would rather approve every change yourself. While this project is pre-1.0, treat the rule set as settled and the configuration schema as still open to change.

### 3. Or run it locally

```bash
pr-policy check --base origin/main
pr-policy check --base origin/main --format json
pr-policy check --base origin/main --format markdown
pr-policy check --base origin/main --strict     # fail on error findings
```

## The rules

| Rule | Default | What it checks |
| --- | --- | --- |
| `attribution` | **on**, warn | Agents never add `Signed-off-by:`; tool assistance uses `Assisted-by:` rather than `Co-authored-by:`; optionally that every commit is signed off |
| `template` | **on**, warn | The description is not empty and the template's `<!-- ... -->` prompts were replaced |
| `size` | **on**, info | The diff is within the project's line and file guidelines |
| `disclosure` | off, warn | The AI-disclosure checkbox was answered — with either answer |
| `linked_issue` | off, warn | The body references an issue (`Closes #123`) |

`disclosure` and `linked_issue` are off until your documentation says the project wants them, which is what `pr-policy init` works out.

### The attribution rule

This is the one worth reading twice, because it encodes a real policy rather than a preference:

```
Signed-off-by: Claude <noreply@anthropic.com>     ← flagged: agents cannot certify the DCO
Co-authored-by: Claude <noreply@anthropic.com>    ← flagged: co-authorship implies authorship
Assisted-by: Claude:claude-opus-5                 ← correct
Signed-off-by: A Human <human@example.com>        ← correct
```

"Names a coding agent" means the trailer contains an identity the agent wrote about *itself*. That is not AI detection — it is reading a label the tool volunteered. A contributor who does not add the trailer is never matched by it.

## Configuration

`.github/pr-policy.yml`:

```yaml
version: 1
enforce: false        # true makes error findings fail the build

rules:
  attribution:
    enabled: true
    severity: warn                  # error | warn | info
    forbid_agent_sign_off: true
    prefer_assisted_by: true
    require_signed_off: false
    agent_identities: ["claude", "copilot", "codex", "cursor", "devin", "aider"]
  disclosure:
    enabled: true
    severity: warn
  template:
    enabled: true
    severity: warn
    min_body_chars: 30
  linked_issue:
    enabled: false
    severity: warn
    keywords: ["closes", "fixes", "resolves"]
  size:
    enabled: true
    severity: info
    max_lines: 1000
    max_files: 100
```

`rules: {size: false}` is shorthand for disabling a rule. Unknown rules and unknown options are errors rather than silent no-ops, so a typo never quietly turns a rule off.

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | No error findings, or the project is reporting-only |
| `1` | Error findings and `enforce: true` (or `--strict`) |
| `2` | Bad configuration, bad revision, or a missing file |

## Also included: `repo-ready`

You cannot enforce a policy that was never written down. `repo-ready` audits whether the documents exist at all — licence, README, tests, CI, `CONTRIBUTING`, `SECURITY` — and scores them out of 100:

```bash
repo-ready .
repo-ready . --min-score 80   # as a CI gate
```

See [`docs/repo-ready.md`](docs/repo-ready.md).

## What it is not

`pr-policy` checks compliance with rules, not quality of work. It cannot tell you whether a change is correct, whether the tests are meaningful, or whether a disclosed AI-assisted contribution is any good. It tells you which submissions ignored what you asked for — which is the part a maintainer can currently only find by reading every one.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Adding a rule is one function in `src/pr_policy/rules.py`, one entry in `DEFAULTS`, and a test.

## License

MIT — see [LICENSE](LICENSE).
