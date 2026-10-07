# Contributing to pr-policy

Thanks for taking the time. Bug reports, new checks and documentation fixes are all welcome.

## Getting set up

```bash
git clone https://github.com/rodny90/pr-policy
cd pr-policy
python -m pip install -e ".[dev]"
```

## Running the checks locally

```bash
pytest                          # the test suite
ruff check .                    # lint
ruff format --check .
repo-ready . --min-score 100    # repo-ready audits this repository
pr-policy check --base origin/main   # pr-policy checks your own branch
```

CI runs exactly these four commands, so a clean local run means a green pull request.

## Adding a rule to pr-policy

Rules live in `src/pr_policy/rules.py`. Each is a function taking a `PullRequest`
and a `RuleConfig` and yielding `Finding` objects.

1. Write the function, then register it in `RULES` and add its defaults to
   `DEFAULTS` in `src/pr_policy/config.py`.
2. If the rule reads the pull request title or body, add it to `NEEDS_METADATA`
   so it is skipped rather than failed when no body is available.
3. **Keep it deterministic.** A rule may check whether a trailer exists, whether a
   box is ticked, whether a reference resolves. A rule may never try to infer
   whether a human or a model wrote something. That boundary is the project.
4. Default new rules to `warn`, and default anything project-specific to
   `enabled: false` until `pr-policy init` can infer it from documentation.
5. Add tests for the passing and the failing case, and a row to the rules table
   in `README.md`.

## Adding a check to repo-ready

Checks live in `src/repo_ready/checks.py`. Each one is a function taking a `Repo` and returning `(passed, detail)`, registered as a `Check` in the `CHECKS` tuple.

1. Write the function. Keep it filesystem-only — `repo-ready` makes no network calls and has no dependencies, and both of those are deliberate.
2. Add a `Check(...)` entry with an `id`, a `title`, a `weight` and a `fix`. The `fix` is what the user reads when the check fails, so make it a concrete instruction rather than a restatement of the problem.
3. **Weights must still total 100.** Adjust the existing weights in the same pull request and say why in the description; `test_weights_sum_to_one_hundred` will fail otherwise.
4. Add tests for both the passing and the failing case.
5. Add a row to the check table in `README.md`, and a line to `CHANGELOG.md`.

A check should earn its weight. Ask whether a maintainer who fails it is meaningfully worse off — if not, it is probably a lint rule rather than a readiness check.

## AI-assisted contributions

You may use AI tools here. We ask two things, both of which this project's own
tooling checks:

1. **Disclose it.** The pull request template has a checkbox. Tick whichever
   option is true — either answer is accepted, the box only needs an answer.
2. **Attribute it correctly.** Record tool assistance with an `Assisted-by:`
   trailer, following the [Linux kernel's
   convention](https://docs.kernel.org/process/coding-assistants.html):

   ```
   Assisted-by: Claude:claude-opus-5
   ```

   An agent must never add a `Signed-off-by:` trailer. Only a human can certify
   the Developer Certificate of Origin, and only a human can take
   responsibility for a change.

Whoever opens the pull request is responsible for the code in it, however it
was written.

## Pull requests

- One logical change per pull request.
- Keep the public output formats stable: the JSON shape is something people script against, so a change to it needs a note in `CHANGELOG.md` under a new version.
- Describe the behaviour change, not the diff.

## Reporting bugs

Open an issue using the bug report template. A repository that reproduces the wrong result is worth more than a description of it — even a three-file example is enough.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).
