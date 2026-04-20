---
phase: 07-distribution-docs
plan: 05
subsystem: release-mechanics
tags: [release, rc1, pypi, ghcr, github-release, operator-runbook]

# Dependency graph
requires:
  - phase: 07-distribution-docs/07-01
    provides: PyPI-valid wheel (timecopilot-timesfm dep, no direct URLs in METADATA)
  - phase: 07-distribution-docs/07-02
    provides: .github/workflows/publish.yml
  - phase: 07-distribution-docs/07-03
    provides: Dockerfile multi-stage targets (runtime-lazy, runtime-bundled)
  - phase: 07-distribution-docs/07-04
    provides: CHANGELOG.md [0.1.0], README.md, docs/*.md

provides:
  - docs/RELEASE.md — maintainer runbook for future releases
  - v0.1.0 shipped across PyPI + GHCR + GitHub Release

status: complete
completed: 2026-04-20
---

# Plan 07-05: Release Procedure & v0.1.0 Tag Cut — SUMMARY

## Objective achieved

Documented the maintainer release procedure and executed the `v0.1.0-rc1` dry-run + `v0.1.0` stable tag cut. Both tags now produce a live, merchant-installable release across all three distribution surfaces.

## Tasks

### Task 1 — `docs/RELEASE.md` maintainer runbook (commit `2c15235`)

228-line operator runbook covering:
- PyPI Trusted Publisher (pending publisher) setup
- GitHub `pypi` environment creation
- Pre-tag wheel smoke test (`uv build` + `twine check` + `git+https` grep)
- rc1 dry-run procedure (tag push → 4 D-20 verification legs)
- v0.1.0 promotion procedure (mutable-tag advancement)
- Post-release GHCR visibility flip
- Yank/rollback procedure

### Task 2 — Prerequisites (operator-completed)

| Step | Resolution |
|------|------------|
| PyPI pending publisher | Registered under owner `mcostigliola321` (real GitHub repo owner; plan had stale `omnialta` reference). Project: `shopify-forecast-mcp`, workflow: `publish.yml`, environment: `pypi`. |
| GitHub `pypi` environment | Created (no reviewers, no protection rules). |
| Local wheel smoke test | `uv build` + `twine check`: PASSED on wheel + sdist. METADATA grep for `git+https`: no direct URLs. `Requires-Dist: timecopilot-timesfm<0.3,>=0.2` present. URLs correctly point to `mcostigliola321`. |
| CHANGELOG date | Already `2026-04-19` (set during 07-04). |

**Mid-task deviation:** Owner mismatch — plan referenced `omnialta` throughout, actual repo is `mcostigliola321/shopify-forecast-mcp`. Swept the rename across 22 files (84 occurrences), preserved `mark@omnialta.com` author email (real domain). Commit `d3cf119`.

### Task 3 — `v0.1.0-rc1` dry-run (tag `v0.1.0-rc1` at commit `d179099`)

**Dry-run iterations: 3 total** — necessary to fix two workflow bugs surfaced by real CI:

1. **First attempt (tag at `d3cf119`):** PyPI upload ✓, Docker builds ✗. Hatchling failed with `OSError: Readme file does not exist: README.md` during `uv sync --no-editable` inside `uv-builder` stage. Root cause: Dockerfile copied `src/` but not the `readme` / `license-files` fields `pyproject.toml` references during wheel metadata validation. Fix: `COPY README.md LICENSE ./` before second sync (commit `4f32276`).

2. **Second attempt (tag at `4f32276`):** Docker builds ✓, PyPI upload ✗. `uv publish --check-url` rejected the sdist because its hash differed from the already-uploaded `0.1.0` sdist (the workflow/Dockerfile commits changed tarball contents). Fix: pre-check step that short-circuits the publish step when the PyPI JSON API returns 200 for the version — true idempotent re-runs (commit `d179099`).

3. **Third attempt (tag at `d179099`):** All six jobs green. 4 legs verified:
   - (a) PyPI: `shopify-forecast-mcp 0.1.0` live (wheel + sdist).
   - (b) GHCR: `:latest-rc`, `:bundled-rc`, `:0.1.0-rc1`, `:0.1.0-rc1-bundled` — all public, multi-arch amd64+arm64 (4 manifests each including OCI attestations).
   - (c) GitHub Release: `v0.1.0-rc1` prerelease with wheel+sdist attached.
   - (d) Clone-to-running stopwatch: `uvx --from shopify-forecast-mcp==0.1.0 shopify-forecast --help` → 30.1s total (5.07s user + 4.43s system + network). Printed all 6 subcommands. Well under 5-min target.

### Task 4 — `v0.1.0` stable tag (tag `v0.1.0` at commit `d179099`)

Pushed at same SHA as rc1 final — workflow reused CI pass, pre-check short-circuited PyPI (0.1.0 already live), Docker multi-arch rebuilt (buildx cache hit on lazy, fresh on bundled). Mutable-tag advancement per D-07: `:latest-rc` → `:latest`, `:bundled-rc` → `:bundled`. GitHub Release flipped from prerelease → stable.

**Stable release verified:**
- PyPI `0.1.0` HTTP 200.
- GHCR `:latest`, `:bundled`, `:0.1.0`, `:0.1.0-bundled` all multi-arch (amd64+arm64).
- GitHub Release `v0.1.0` with `isPrerelease: false`, wheel+sdist attached.

## Commits (this plan)

| Commit | Scope |
|--------|-------|
| `2c15235` | docs(07-05): add docs/RELEASE.md maintainer runbook |
| `d3cf119` | docs(phase-07): rename github owner omnialta → mcostigliola321 |
| `4f32276` | fix(release): dockerfile COPY README/LICENSE + pypi publish idempotent |
| `d179099` | fix(release): skip pypi upload when version already published |

## Deliverables

- **PyPI:** https://pypi.org/project/shopify-forecast-mcp/ (version 0.1.0)
- **GHCR:** https://github.com/mcostigliola321?tab=packages (tags: `:latest`, `:bundled`, `:0.1.0`, `:0.1.0-bundled`, `:latest-rc`, `:bundled-rc`, `:0.1.0-rc1`, `:0.1.0-rc1-bundled`)
- **GitHub Release:** https://github.com/mcostigliola321/shopify-forecast-mcp/releases/tag/v0.1.0
- **Runbook:** `docs/RELEASE.md` (228 lines)

## Deviations from plan

1. **Owner rename (docs-level):** Plan assumed `omnialta` owner; actual is `mcostigliola321`. 84 references swept. Email preserved.
2. **Two workflow bugs surfaced by CI that the plan's Wave 0 tests didn't catch:**
   - Dockerfile missing `README.md` / `LICENSE` copies — the Wave 0 `test_dockerfile_structure.py` verifies the static text of COPY statements but didn't cross-reference them against `pyproject.toml` fields that hatchling requires.
   - PyPI idempotency — `--check-url` alone isn't sufficient when sdist hashes drift across retagged SHAs; needs a pre-check short-circuit.
3. **Three rc1 iterations** instead of the single "happy path" the plan assumed. Caught and fixed in-flight; final release shipped successfully.

## Requirements satisfied

- R12.1 — `uvx`-installable (PyPI)
- R12.2 — multi-arch Docker images on GHCR (amd64+arm64)
- R12.3 — `:bundled` variant with weights baked in (offline-capable)
- R12.4 — PyPI Trusted Publisher (no static tokens)
- R12.5 — Maintainer runbook (`docs/RELEASE.md`)

## Notes for future releases

- `docs/RELEASE.md` reflects the final fixed pipeline (post-bug-fixes). Future maintainers should not re-hit the Dockerfile README bug or the PyPI idempotency issue.
- The Wave 0 test suite (48 `def test_*` functions) catches workflow/CHANGELOG/README structural regressions sub-60s. Run it during rc prep.
- For each version bump: update `CHANGELOG.md` [Unreleased] → [X.Y.Z] with date, bump `version` in `pyproject.toml`, then follow `docs/RELEASE.md`.
