# Release Procedure

Maintainer runbook for cutting `shopify-forecast-mcp` releases. Not a user-facing doc — consumers should read [README.md](../README.md) and [SETUP.md](SETUP.md).

## Contents

- [One-time prerequisites](#one-time-prerequisites)
- [Per-release: RC dry-run (v0.1.0-rc1 pattern)](#per-release-rc-dry-run)
- [Per-release: Final tag cut](#per-release-final-tag-cut)
- [Post-release verification](#post-release-verification)
- [Rollback](#rollback)

***

## One-time prerequisites

These three setup steps happen ONCE before the first tag push. Skipping any of them causes `v0.1.0-rc1` to fail.

### 1. PyPI Trusted Publisher registration (pending publisher)

1. Log in to https://pypi.org/manage/account/publishing/ with the maintainer account.
2. Click **Add a new pending publisher**.
3. Fill in:
   - **PyPI Project Name:** `shopify-forecast-mcp`
   - **Owner:** `mcostigliola321`
   - **Repository name:** `shopify-forecast-mcp`
   - **Workflow name:** `publish.yml`
   - **Environment name:** `pypi`
4. Click **Add**.

> "Pending publisher" status means the PyPI project will be created on first successful upload. No manual project creation needed.

### 2. GitHub Environment: `pypi`

Create the pypi environment in the repo so the `publish-pypi` job can attach to it during the OIDC exchange:

1. In the repo, navigate to **Settings → Environments**.
2. Click **New environment**, name it `pypi`.
3. Leave deployment protection rules empty for v0.1.0 (solo maintainer, no reviewers).
4. Save.

This environment name must match `environment: pypi` in `.github/workflows/publish.yml` job `publish-pypi`. PyPI checks the pypi environment name during the OIDC exchange.

### 3. (Deferred to first push) GHCR visibility

GHCR packages default to PRIVATE on first push. After the first successful Docker job (during rc1), you'll flip visibility — see the rc1 checklist below.

***

## Per-release: RC dry-run

Every release starts with an rc (release candidate) tag to exercise the full pipeline. Per D-20, four legs must go green before cutting the stable tag.

### Preparation

1. Confirm `main` branch is green in CI:
   ```bash
   gh run list --workflow=ci.yml --branch=main --limit=1
   ```
2. Confirm CHANGELOG.md is up to date and the date in the `[0.1.0]` heading matches the intended release date:
   ```bash
   head -20 CHANGELOG.md
   ```
   If the date needs updating, commit that first:
   ```bash
   # Update CHANGELOG.md: replace "## [0.1.0] - 2026-04-19" with today's date.
   git commit -am "docs(changelog): set [0.1.0] release date"
   git push origin main
   ```
3. Confirm the local `uv build` produces a PyPI-valid wheel (D-23 safety check):
   ```bash
   rm -rf dist/
   uv build
   uvx --from twine twine check dist/*
   unzip -p dist/*.whl '*/METADATA' | grep Requires-Dist | grep -v git+https  # expect all matches; none should contain git+https
   ```

### Tag the rc

```bash
# Use a lightweight annotated tag with a brief message.
git tag -a v0.1.0-rc1 -m "Release candidate 1 for v0.1.0"
git push origin v0.1.0-rc1
```

This triggers `.github/workflows/publish.yml`. Watch it:

```bash
gh run watch $(gh run list --workflow=publish.yml --limit=1 --json databaseId --jq '.[0].databaseId')
```

### 4-leg verification (D-20)

Verify each leg independently. All 4 must pass before proceeding to v0.1.0.

#### Leg (a): CI green on tag SHA

- `gh run list --workflow=ci.yml --commit=$(git rev-parse v0.1.0-rc1)` shows a green run.
- If red: fix the underlying bug, re-push main, re-tag.

#### Leg (b): PyPI pre-release upload

- `gh run view <publish-run-id> --log | grep -A5 "Publish to PyPI"` shows `uv publish` succeeding.
- Visit https://pypi.org/project/shopify-forecast-mcp/ — `0.1.0rc1` appears with a "Pre-release" badge.
- The page MUST render correctly (README renders; mermaid blocks render as code since PyPI doesn't execute mermaid — that's expected per RESEARCH Pitfall 7).
- Metadata check: `curl -s https://pypi.org/pypi/shopify-forecast-mcp/0.1.0rc1/json | jq '.info.requires_dist'` — no `git+https` URLs.

#### Leg (c): `uvx --prerelease=allow` on fresh machine

Spin up a clean container:

```bash
docker run --rm -it python:3.11-slim bash
# Inside the container:
apt-get update && apt-get install -y curl
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env
uvx --prerelease=allow shopify-forecast-mcp@0.1.0rc1 --help
# Expect: CLI help output, exit 0.
```

Also verify the server starts (stdio) without accessing Shopify (expected to error without env vars, but SHOULD start cleanly):

```bash
uvx --prerelease=allow shopify-forecast-mcp@0.1.0rc1 < /dev/null
# Expect: startup log to stderr, quick exit because stdin closed.
```

#### Leg (d): GHCR images publish + run

**Visibility flip (ONE-TIME, do now):**

1. Visit https://github.com/mcostigliola321/shopify-forecast-mcp/packages (or wherever the owner is).
2. Click the `shopify-forecast-mcp` container package.
3. **Package settings → Change visibility → Public → confirm**.

Then verify both tags pull + run:

```bash
docker pull ghcr.io/mcostigliola321/shopify-forecast-mcp:latest-rc
docker pull ghcr.io/mcostigliola321/shopify-forecast-mcp:bundled-rc

# Lazy variant: needs network for first model download
docker run --rm ghcr.io/mcostigliola321/shopify-forecast-mcp:latest-rc --help
# Expect: CLI help output.

# Bundled variant: works offline
docker run --rm --network=none ghcr.io/mcostigliola321/shopify-forecast-mcp:bundled-rc --help
# Expect: CLI help output, no network errors.

# Multi-arch manifest check
docker buildx imagetools inspect ghcr.io/mcostigliola321/shopify-forecast-mcp:latest-rc
# Expect: Manifests for linux/amd64 AND linux/arm64.
```

#### Clone-to-running stopwatch (Phase 7 success criterion 1)

On a different fresh machine (not the rc1 container above):

1. Start timer.
2. `curl -LsSf https://astral.sh/uv/install.sh | sh`
3. Add the Claude Desktop config snippet from README Quick start (substitute real `SHOPIFY_FORECAST_SHOP` + `SHOPIFY_FORECAST_ACCESS_TOKEN`).
4. Restart Claude Desktop.
5. Ask "What does next month look like?" in a new conversation.
6. Receive a markdown revenue forecast table.
7. Stop timer.

**Target:** ≤ 5:00. Record the time in the rc1 GitHub issue.

### Record rc1 outcome

Open a GitHub issue titled **"v0.1.0-rc1 validation"** and fill in all 4 legs plus the stopwatch time. Close when all pass.

***

## Per-release: Final tag cut

Only proceed once all 4 rc1 legs are green.

1. Update `CHANGELOG.md` — move any new entries from `[Unreleased]` into the `[0.1.0]` section if applicable (for v0.1.0 there shouldn't be any; Plan 04 seeded the whole set).
2. Update the `[0.1.0]` date to today if it drifted.
3. Commit any doc nits discovered during rc1 verification.
4. Tag:

```bash
git tag -a v0.1.0 -m "v0.1.0 — first public alpha"
git push origin v0.1.0
```

5. Watch:

```bash
gh run watch $(gh run list --workflow=publish.yml --limit=1 --json databaseId --jq '.[0].databaseId')
```

6. Expected outputs:
   - PyPI: `shopify-forecast-mcp 0.1.0` appears (NO pre-release badge).
   - GHCR: `:0.1.0`, `:latest`, `:0.1.0-bundled`, `:bundled` tags pushed (stable mutable tags advance; rc tags unchanged per Pitfall 5 mitigation).
   - GitHub Releases: `v0.1.0` release appears, body from `CHANGELOG.md [0.1.0]` section, `dist/*.whl` + `dist/*.tar.gz` attached, NOT marked pre-release.

***

## Post-release verification

1. `uvx shopify-forecast-mcp --help` (without `--prerelease=allow`) resolves cleanly on a fresh machine.
2. `docker pull ghcr.io/mcostigliola321/shopify-forecast-mcp:latest` succeeds (public package).
3. `docker run --rm --network=none ghcr.io/mcostigliola321/shopify-forecast-mcp:bundled --help` works.
4. README banner still reads "⚠️ v0.1.0 Alpha" (don't bump to beta yet — D-19 locks Alpha classifier).
5. Open a pinned GitHub Issue: **"v0.1.0 feedback wanted"** linking to the Release. This + README banner constitute the full announce surface per D-22 (repo-only, no external socials for v0.1.0).

***

## Rollback

If a v0.1.0 tag ships a broken release, do NOT yank or force-push — PyPI and GHCR both keep historical tags regardless, and yanking breaks downstream pins. Use the patch-release playbook below.

### Patch-release procedure

1. **Cannot yank from PyPI** without breaking downstream pins. Instead, cut a `v0.1.1` patch release with the fix.
2. Delete GHCR tags for the bad version: `gh api --method DELETE /orgs/mcostigliola321/packages/container/shopify-forecast-mcp/versions/<version-id>`.
3. Mark the GitHub Release as "pre-release" (flag it in the UI) + add a warning note to the description.
4. In README banner, link to the new patch release's Release notes.

### What NOT to do

- Do **not** force-push the `v0.1.0` tag — PyPI rejects re-uploads for the same version, and most consumers pin by version so they'll see nothing change.
- Do **not** yank the PyPI release unless it's an active security incident — downstream `uv.lock` entries with the yanked version will start failing resolution.
- Do **not** delete the `v0.1.0` git tag — Release provenance (see threat T-07-22) depends on the tag SHA staying stable.
