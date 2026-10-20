# Releasing

Versioning follows [SemVer](https://semver.org/) (before 1.0, a minor version may break). Maintainers only; contributors just keep `CHANGELOG.md` up to date (see below).

## What a release publishes

Pushing a tag `vX.Y.Z` runs [`.github/workflows/release.yml`](../.github/workflows/release.yml), which builds and pushes the image to GHCR for **linux/amd64 and linux/arm64**:

- `ghcr.io/ecg-rudy-glt/coach:X.Y.Z`
- `ghcr.io/ecg-rudy-glt/coach:X.Y` (moves with each patch release)
- `ghcr.io/ecg-rudy-glt/coach:latest`

The workflow can also be started by hand (`workflow_dispatch`) to rebuild an image. The GitHub release page and its notes are written by hand in step 5; the workflow does not create them.

## Steps

1. **Pick the version.** Breaking change to the API, the database or the configuration: bump the minor (or major after 1.0). Otherwise bump the patch.
2. **Prepare it in a pull request** (`main` is protected):
   - set `VERSION` in [`app/config.py`](../app/config.py);
   - in `CHANGELOG.md`, rename `## [Unreleased]` to `## [X.Y.Z] — YYYY-MM-DD` and add a fresh empty `## [Unreleased]` above it. A test (`tests/test_version.py`) fails if the top release and `VERSION` differ;
   - if the release changes configuration or migrations, say so at the top of the changelog entry (migrations are forward-only, see `db/migrations/`);
   - check that the image tag in `README.md` and `docker-compose.yml` still makes sense.
3. **Merge** once CI is green (squash).
4. **Tag the merge commit** and push the tag:
   ```sh
   git checkout main && git pull
   git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin vX.Y.Z
   ```
5. **Check the workflow** (Actions tab), then pull the image on both architectures if you can, and create the GitHub release from the tag with the changelog entry as notes (`gh release create vX.Y.Z --notes-file …`).

## Changelog rules

- Every pull request that changes code, migrations, questions or rule data adds a line under `## [Unreleased]` (`Added`, `Changed`, `Fixed`, `Security`, `Removed`).
- CI enforces it: the *Changelog entry* check fails a pull request that touches those paths without touching `CHANGELOG.md`. Dependency-bot pull requests and pull requests labelled `skip-changelog` are exempt (add the label, then re-run the check).
- Write for users, not for reviewers: what changes for someone running the app.

## If a release is wrong

Do not move or delete a published tag. Fix forward with a patch release; if an image is broken, publish the patch and let `latest` and `X.Y` follow it.
