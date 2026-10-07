# Releasing

Releases are tag-driven. Pushing a `vX.Y.Z` tag builds, tests, publishes to PyPI,
creates the GitHub release, and moves the `vX` tag so
`uses: rodny90/pr-policy@v0` follows the newest release in that major version.

## One-time setup

Publishing uses [PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/),
so no API token is ever stored in this repository. It has to be authorised once,
on PyPI's side:

1. Sign in at [pypi.org](https://pypi.org) and go to **Your projects → Publishing**
   (for a name that has never been published, use **Add a pending publisher**).
2. Register a GitHub publisher with:

   | Field | Value |
   | --- | --- |
   | Owner | `rodny90` |
   | Repository | `pr-policy` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

3. In this repository, create the environment under
   **Settings → Environments → New environment**, named `pypi`. Adding required
   reviewers there is worth doing: it turns every publish into something you
   approve by hand.

Until that is done the `publish` job fails and nothing reaches PyPI. The build
and test jobs still run, so a tag pushed early is not destructive.

## Cutting a release

1. Move everything under `## [Unreleased]` in `CHANGELOG.md` into a new version
   heading, and update the comparison links at the bottom.
2. Bump `version` in `pyproject.toml`. The release workflow refuses to publish
   when the tag and the packaged version disagree, so these cannot drift.
3. Commit, then tag and push:

   ```bash
   git tag -a v0.2.0 -m "v0.2.0"
   git push origin v0.2.0
   ```

The workflow takes it from there. It runs the full suite, `ruff check`, and
`repo-ready . --min-score 100` before building, so a release cannot ship a red
test suite.

## The major version tag

Action users pin to a major version rather than a patch:

```yaml
- uses: rodny90/pr-policy@v0
```

The `major-tag` job force-updates `v0` to each new `v0.x.y` release, and will do the
same for `v1` once this reaches 1.0. That is the convention published actions
follow, and it means a bug fix reaches users without them editing a workflow.
When `v1` ships, `v0` stops moving.

## Checklist

- [ ] `CHANGELOG.md` has a dated heading for the version
- [ ] `pyproject.toml` version matches the tag
- [ ] `pytest`, `ruff check .`, `ruff format --check .` pass locally
- [ ] `repo-ready . --min-score 100` passes
- [ ] The `pypi` environment exists and the trusted publisher is registered
