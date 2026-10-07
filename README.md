# pr-policy

[![CI](https://github.com/rodny90/pr-policy/actions/workflows/ci.yml/badge.svg)](https://github.com/rodny90/pr-policy/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pr-policy.svg)](https://pypi.org/project/pr-policy/)
[![Python versions](https://img.shields.io/pypi/pyversions/pr-policy.svg)](https://pypi.org/project/pr-policy/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Reduce low-effort and drive-by pull requests with checks your project writes down.**

`pr-policy` checks each pull request against the rules your project already stated: a linked issue, a size guideline, a completed pull request template, and the project's AI-assistance rules. It posts what it found as one comment that updates on every push. It never tries to detect AI. The AI trailer and disclosure checks are only two of its five rules, so it suits projects that allow AI, restrict it, or say nothing about it. Findings are warnings by default, and nothing blocks a pull request unless the maintainer sets `enforce: true` (or `--strict`).

## Install in 30 seconds

**1. Generate a config from your own documentation.** Run this in your repository:

```bash
pipx run pr-policy init
```

It reads `CONTRIBUTING.md`, the pull request template and `AGENTS.md`, writes `.github/pr-policy.yml`, and quotes the line behind every rule it switches on, so you can check its reasoning. No config yet? The defaults work too.

**2. Add the GitHub Action.** Save as `.github/workflows/pr-policy.yml`:

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

That is all. It is reporting-only: findings default to warnings, and the job fails only if your config sets `enforce: true` (or the action's `strict` input is on) and a finding has severity `error`. Ready-made variants (strict, custom config) are in [`examples/`](examples/).

## What the maintainer sees

One sticky comment, edited in place on each push. This is the format `pr-policy check --format markdown` produces, rendered:

> ### pr-policy
>
> Found 3 warn.
>
> - 🟡 **commit 4ea6a851 has 'Signed-off-by: Claude <noreply@anthropic.com>', which names a coding agent (claude)**
>   Only a human can certify the DCO. Sign off as yourself and record the tool with 'Assisted-by: <tool>:<model>'.
> - 🟡 **the AI-disclosure checkbox in the pull request template is not ticked**
>   Tick the option that applies. Either answer is accepted — the box only needs to be answered.
> - 🟡 **the pull request body does not reference an issue**
>   This project asks for an issue first. Add a line such as 'Closes #123' so the discussion and the change stay linked.
>
> <sub>Rules run: attribution, disclosure, template, linked_issue, size. These are signals for the maintainer, not a verdict on your change.</sub>

A clean pull request gets one line saying so. Findings are 🔴 error, 🟡 warn or 🔵 info.

## How this compares

These tools overlap less than their names suggest, and most projects could reasonably run several of them.

| Tool | What it does | How `pr-policy` differs |
| --- | --- | --- |
| GitHub Community Standards | A repository-level checklist (README, licence, contributing guide, templates, ...) on the Insights page. | It checks that the files exist, once, for the repository. `pr-policy` checks each pull request against what those files say. (`repo-ready`, below, is the closer analogue.) |
| [Danger.js](https://danger.systems/js/) | A framework: you write rules in a Dangerfile and it comments on pull requests. | Danger can express almost any rule, but you write and maintain the code. `pr-policy` ships a fixed set of rules configured in YAML, with no code and no Node, and `init` derives the config from your docs. |
| CodeRabbit-style AI review | A language model reviews the content of the change and comments on it. | Those tools judge the code. `pr-policy` never reads it for quality and uses no model, so the same pull request always gets the same findings. |
| SlopGuard-style detection | Tools that try to flag pull requests that look AI-generated or low-effort. | `pr-policy` does not classify who or what wrote anything. It checks only rules your project published, such as a trailer present or a checkbox answered. |

What `pr-policy` cannot do: tell you whether a change is correct, whether its tests mean anything, or whether a disclosed AI-assisted contribution is any good.

## Why this exists

Maintainers are being buried in contributions, and the tools arriving to help are mostly **throttles**: cap the number of open pull requests, restrict them to collaborators, turn them off. Those control *how many* submissions arrive. Nothing checks whether an arriving submission follows the rules the project published.

The gap is concrete. GitHub's issue forms have supported required fields and per-field validation for years; [issue forms are not supported for pull requests](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms). A pull request template is inert markdown. A contributor can delete the whole thing — including the AI-disclosure checkbox your project added — and nothing notices.

Projects have written the policies. MicroPython and ESLint require an AI declaration. The [Linux kernel](https://docs.kernel.org/process/coding-assistants.html) requires an `Assisted-by:` trailer and forbids agents from adding `Signed-off-by:`, because only a human can certify the DCO. `pr-policy` is the enforcement half those policies never got.

## Design

Three commitments, and the tool is built around them:

**It never tries to detect AI.** Detection is an arms race — any classifier good enough to identify AI output can be used to train past it — and maintainers have said plainly that they do not want a tool adjudicating authorship. Every rule here is deterministic: a trailer is present or it is not, a checkbox is ticked or it is not.

**It routes on disclosure and never judges it.** If your template asks whether AI was used, *either* answer passes. The rule fires when the question was ignored, not when it was answered in a way someone dislikes.

**It reports signals, not verdicts.** Nothing fails a build until you set `enforce: true`. The default posture is a comment on the pull request telling the maintainer what to look at, leaving the judgement where it belongs.

## Usage

### Install the CLI

```bash
pip install pr-policy
```

Or without installing anything:

```bash
pipx run pr-policy check --base origin/main
```

Requires Python 3.9 or newer.

### Generate a config

```bash
pr-policy init
```

`init` turns the enforceable parts of your documentation into configuration, quoting the line it relied on:

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

Inference is a heuristic and it will sometimes be wrong. That is exactly why it shows its evidence — read the file before you commit it. A sample config is in [`examples/pr-policy.yml`](examples/pr-policy.yml).

### Run it locally

```bash
pr-policy check --base origin/main
pr-policy check --base origin/main --format json
pr-policy check --base origin/main --format markdown
pr-policy check --base origin/main --strict     # fail on error findings
```

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

### Replay it on past pull requests

```bash
pr-policy replay --repo OWNER/NAME --last 20
pr-policy replay --repo OWNER/NAME --config .github/pr-policy.yml
```

Checks a project's recent merged pull requests against a policy, so you can see what a config would have flagged before you turn it on. It reads through the `gh` CLI (must be installed and signed in, otherwise exit code 2), uses the same rules as `check`, and never posts or writes anything to GitHub. The config is `--config` if given, else `.github/pr-policy.yml` in the current directory, else the built-in defaults. The output is signals, not verdicts.

## The GitHub Action

`uses: rodny90/pr-policy@v0` follows the newest 0.x release. Pin an exact tag (`@v0.1.0`) if you would rather approve every change yourself. While this project is pre-1.0, treat the rule set as settled and the configuration schema as still open to change.

### Inputs

| Input | Default | Description |
| --- | --- | --- |
| `config` | conventional locations | Path to `pr-policy.yml`. Looked for in `.github/pr-policy.yml`, `.github/pr-policy.yaml`, `pr-policy.yml` and `pr-policy.yaml`. |
| `base` | the pull request's base branch | Base ref to compare against. Required outside `pull_request` events. |
| `strict` | `"false"` | Fail the job on error findings even if the config does not set `enforce`. |
| `comment` | `"true"` | Post the findings as a sticky comment on the pull request. |
| `python-version` | `"3.12"` | Python version used to run pr-policy. |

### Outputs

| Output | Description |
| --- | --- |
| `exit-code` | `0` when the policy passed or is reporting-only, `1` when enforcement failed, `2` on a bad configuration, a bad revision or a missing base. |
| `findings` | The findings as JSON, the same shape as `pr-policy check --format json`. |

### Notes

- Commit-trailer rules read the branch history, so check out with `fetch-depth: 0`, as in the workflow above.
- Posting the comment needs `pull-requests: write`. If the comment cannot be written, the job does not fail: the action logs a `::warning::` and the job's result still comes only from the check's exit code. This is what happens on pull requests from forks, whose `GITHUB_TOKEN` is read-only. The findings are still in the job log and the `findings` output. To silence the warning, set `comment: "false"` for those runs.
- The action posts its comment only on `pull_request` events. It deliberately does not support `pull_request_target`: that event hands a write token to a job that would have to check out the fork's code, which is the pattern GitHub's Security Lab [warns against](https://securitylab.github.com/resources/github-actions-preventing-pwn-requests/). To get a comment on fork pull requests, split the work: run the action with `comment: "false"` on `pull_request` and upload the `policy-comment.md` it leaves in the workspace as an artifact, then post that file (with a `<!-- pr-policy -->` line appended, so later runs update it) from a second workflow triggered by `workflow_run`, which has a write token and never checks out the fork. No example of that split ships yet.
- If the check cannot run at all (exit code `2`: a bad config or a missing base), nothing is posted, so an earlier good comment is left alone. The step's error is in the job log.
- Examples to copy: [`examples/`](examples/).

## The rules

| Rule | Default | What it checks |
| --- | --- | --- |
| `linked_issue` | off, warn | The body references an issue (`Closes #123`) |
| `size` | **on**, info | The diff is within the project's line and file guidelines |
| `template` | **on**, warn | The description is not empty and the template's `<!-- ... -->` prompts were replaced |
| `attribution` | **on**, warn | AI-assistance rules: agents never add `Signed-off-by:`; tool assistance uses `Assisted-by:` rather than `Co-authored-by:`; optionally that every commit is signed off |
| `disclosure` | off, warn | The AI-disclosure checkbox was answered, with either answer |

`disclosure` and `linked_issue` are off until your documentation says the project wants them, which is what `pr-policy init` works out. It enables a rule only from wording that asks for something ("you must disclose AI tools", "please open an issue first"), not from a sentence that merely mentions the subject. In the pull request template, a checkbox item about the subject, or a heading such as `## Generative AI`, counts as the question being asked.

How `disclosure` decides whether the question was answered:

- A **ticked box** whose label matches one of `checkbox_patterns` passes, whichever answer it is. The default patterns accept any label that mentions AI (`generative ai`, `\bai\b`, `llm`, `copilot`, `chatgpt`, `claude`, `codex`), which covers everything `init` reacts to. Set your own list if your template words the question differently.
- An **unticked** box that matches is reported as not ticked.
- With **no matching box at all**, the rule looks for a heading about AI with something written under it. That is how templates that ask in prose (a "Generative AI" section holding two sentences to choose from) are handled, and all it can verify is that the section was not deleted. Without one, the body is reported as carrying no disclosure statement.

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
    # A ticked box whose label matches any of these (regular expressions) satisfies the rule.
    checkbox_patterns: ['generative ai', '\bai\b', '\b(llm|copilot|chatgpt|claude|codex)\b']
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

You cannot enforce a policy that was never written down. `repo-ready` audits whether the documents exist at all — licence, README, tests, CI, `CONTRIBUTING`, `SECURITY`, and agent instructions such as `AGENTS.md` — and scores them out of 100:

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
