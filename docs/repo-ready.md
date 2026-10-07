# repo-ready

**Score a repository on the things contributors and users look for, and find out what to fix first.**

`repo-ready` ships alongside [`pr-policy`](../README.md) because the two halves belong together: you cannot enforce a policy that was never written down. `repo-ready` checks that the documents exist; `pr-policy` checks that submissions follow them.

It has no dependencies beyond the package itself, makes no network calls, and reads nothing but your files.

```
repo-ready  .

  PASS  Has a LICENSE                    found LICENSE
  PASS  Has a substantial README         found README.md (7214 characters)
  PASS  README covers install and usage  README documents installation and usage
  PASS  Has automated tests              found tests in tests/
  PASS  Runs CI on every push            found 1 GitHub Actions workflow(s)
  FAIL  Has CONTRIBUTING guidance        no CONTRIBUTING file found
  ...

Score: 92/100  (grade A)

Fix these first:
  [ 8 pts] Has CONTRIBUTING guidance
           Add CONTRIBUTING.md describing how to set up the project, run tests and open a pull request.
```

## Usage

```bash
repo-ready                       # audit the current directory
repo-ready ~/code/my-project     # audit somewhere else
repo-ready . --format json       # machine-readable
repo-ready . --format markdown   # a table to paste into a README
```

### As a CI gate

`--min-score` exits `1` below the threshold:

```yaml
- name: Check repository health
  run: pipx run --spec pr-policy repo-ready . --min-score 80
```

### Scripting the score

```bash
repo-ready . --format json | jq '.score'
```

```json
{
  "path": ".",
  "score": 92,
  "grade": "A",
  "checks": [
    { "id": "license", "title": "Has a LICENSE", "passed": true, "weight": 15,
      "detail": "found LICENSE", "fix": "" }
  ]
}
```

## The checks

Scores are weighted, not counted — a missing licence costs far more than a missing issue template.

| Check | Weight | Passes when |
| --- | ---: | --- |
| `license` | 15 | `LICENSE`, `LICENCE` or `COPYING` exists and holds real licence text |
| `readme` | 15 | A `README` exists with at least 300 characters |
| `tests` | 15 | A `tests/` directory or files named by convention (`test_*.py`, `*_test.go`, `*.test.ts`, ...) |
| `ci` | 15 | A GitHub Actions workflow, or GitLab / Travis / CircleCI / Azure config |
| `contributing` | 8 | A `CONTRIBUTING` file exists |
| `security` | 7 | A `SECURITY` file exists |
| `readme-sections` | 5 | The README has both an install and a usage section |
| `manifest` | 5 | A package manifest exists (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, ...) |
| `changelog` | 5 | A `CHANGELOG`, `CHANGES` or `HISTORY` file exists |
| `code-of-conduct` | 5 | A `CODE_OF_CONDUCT` file exists |
| `gitignore` | 3 | A `.gitignore` exists |
| `issue-templates` | 2 | `.github/ISSUE_TEMPLATE/` is present and non-empty |

Grades: **A** ≥ 90, **B** ≥ 75, **C** ≥ 60, **D** ≥ 40, **F** below that.

Files are found case-insensitively and are also looked for in `.github/` and `docs/`, matching where GitHub itself looks. Vendored directories (`node_modules/`, `vendor/`, `third_party/`, build output) are skipped, so a dependency's test suite cannot make your repo look tested.

## Options

| Flag | Effect |
| --- | --- |
| `-f`, `--format {text,json,markdown}` | Output format (default `text`) |
| `--min-score N` | Exit `1` if the score is below `N` |
| `--no-fixes` | Omit the suggested fixes from text output |
| `--version` | Print the version |

Colour is used when stdout is a terminal and is disabled by [`NO_COLOR`](https://no-color.org).

## What it is not

`repo-ready` checks that the scaffolding of a healthy project is *present*. It cannot tell you whether your README is any good, whether your tests are meaningful, or whether your licence suits your goals. It is a pre-flight checklist, not a review.
