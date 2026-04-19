---
phase: 07-distribution-docs
plan: 02
subsystem: ci-cd
tags:
  - ci-cd
  - publishing
  - security
  - docker
  - pypi
  - github-actions
requires:
  - 07-01   # depends on D-23 dep swap landing + Wave 0 structural tests
provides:
  - publish-workflow
  - pypi-oidc-pipeline
  - ghcr-multiarch-push
  - github-release-pipeline
affects:
  - .github/workflows/publish.yml
tech-stack-added:
  - uv publish (Trusted Publisher OIDC)
  - docker/build-push-action@v7
  - docker/metadata-action@v6
  - docker/setup-buildx-action@v4
  - docker/setup-qemu-action@v4
  - docker/login-action@v4
  - lewagon/wait-on-check-action@v1.4.0
  - ffurrer2/extract-release-notes@v3
  - softprops/action-gh-release@v2
patterns:
  - "Cross-workflow gating via Checks API polling (not workflow_run, because ci.yml does not trigger on tag push)"
  - "OIDC-only PyPI publishing (no static token, PEP 740 Trusted Publisher)"
  - "rc-tag discrimination via conditional enable= raw tag rules (Pitfall 5 mitigation)"
  - "Per-variant GHA cache scoping to isolate lazy vs bundled Docker caches"
  - "Matrix job over Dockerfile build targets (runtime-lazy, runtime-bundled)"
key-files-created:
  - .github/workflows/publish.yml
key-files-modified: []
decisions-implemented:
  - D-01  # tag trigger
  - D-02  # direct-to-PyPI incl. pre-releases
  - D-03  # gate on ci.yml, no duplication
  - D-04  # PyPI + GitHub Release with artifacts
  - D-05  # OIDC only, no static tokens
  - D-07  # multi-arch Docker
requirements-completed:
  - R12.1
  - R12.2
  - R12.3
  - R12.4
metrics:
  duration-seconds: 119
  tasks-completed: 2
  files-created: 1
  files-modified: 0
  lines-added: 227
  completed-date: 2026-04-19
---

# Phase 07 Plan 02: Tag-triggered Release Pipeline Summary

**One-liner:** End-to-end `v*`-tag-triggered `.github/workflows/publish.yml` with CI gating, OIDC PyPI upload, multi-arch GHCR push, and GitHub Release creation — executes all of D-20's rc1 dry-run legs without static tokens.

## What Was Built

A single 227-line `.github/workflows/publish.yml` with 5 jobs implementing the complete release pipeline for v0.1.0 and beyond:

### Job Graph

```
                    tag push (v*)
                          │
                          ▼
                   [wait-for-ci]          ── gates on ci.yml smoke matrix (ubuntu + macos) for same SHA
                          │
                          ▼
                      [build]             ── uv build → twine check → D-23 METADATA gate → upload dist/
                      ╱     ╲
                     ╱       ╲
                    ▼         ▼
           [publish-pypi]  [publish-docker]  ── matrix: [lazy, bundled] × [linux/amd64, linux/arm64]
                    ╲         ╱
                     ╲       ╱
                      ╲     ╱
                       ▼   ▼
                  [create-release]         ── softprops/action-gh-release@v2 + CHANGELOG extract + dist/* attached
```

### Job Breakdown

| Job | Purpose | Key Permissions | Timeout |
|-----|---------|-----------------|---------|
| `wait-for-ci` | Poll Checks API for both `Smoke (Python 3.11, ubuntu-latest)` and `Smoke (Python 3.11, macos-latest)` on the tag's SHA | `checks: read`, `actions: read` | 30 min |
| `build` | `uv build` wheel + sdist; `twine check`; D-23 belt-and-braces scan for `git+https` in METADATA; upload `dist/` artifact | `contents: read` | 15 min |
| `publish-pypi` | `uv publish` with Trusted Publisher OIDC; scoped to `environment: pypi` | `id-token: write`, `contents: read` | 15 min |
| `publish-docker` | Matrix over `[lazy, bundled]`; multi-arch buildx to GHCR; rc-aware tag rules | `packages: write`, `contents: read` | 60 min |
| `create-release` | Extract CHANGELOG body via `ffurrer2/extract-release-notes@v3`; create GitHub Release with `dist/*.whl` + `dist/*.tar.gz` attached; auto-flag prerelease for `rc`/`alpha`/`beta` | `contents: write` | 10 min |

### Action Versions Pinned (Audit Record)

| Action | Version | Purpose |
|--------|---------|---------|
| `actions/checkout` | `@v5` | Repo checkout |
| `astral-sh/setup-uv` | `@v6` | uv installation |
| `actions/upload-artifact` | `@v4` | dist/ sharing between jobs |
| `actions/download-artifact` | `@v4` | dist/ retrieval |
| `lewagon/wait-on-check-action` | `@v1.4.0` | Cross-workflow CI gate |
| `docker/setup-qemu-action` | `@v4` | arm64 emulation for multi-arch |
| `docker/setup-buildx-action` | `@v4` | Buildx driver init |
| `docker/login-action` | `@v4` | GHCR auth via `GITHUB_TOKEN` |
| `docker/metadata-action` | `@v6` | Conditional tag rules with `enable=` |
| `docker/build-push-action` | `@v7` | Multi-arch build + push |
| `ffurrer2/extract-release-notes` | `@v3` | Parse `## [X.Y.Z]` blocks from CHANGELOG.md |
| `softprops/action-gh-release` | `@v2` | GitHub Release creation with asset attachment |

All actions pinned to stable major version tags. SHA-pinning deferred to v0.2 supply-chain hardening (RESEARCH Security Domain, T-07-10 accepted residual).

### Conditional Tag Rule Matrix

Four `enable=${{ ... }}` guards on `docker/metadata-action@v6` raw tags — rigorously prevents rc tags from advancing the mutable stable pointers (Pitfall 5 mitigation):

| Tag | Enable condition | Pushed on |
|-----|------------------|-----------|
| `latest` | `!contains(ref_name, 'rc') && !contains('alpha') && !contains('beta')` | stable only |
| `latest-rc` | `contains(ref_name, 'rc')` | rc only |
| `bundled` | `!contains(ref_name, 'rc') && !contains('alpha') && !contains('beta')` | stable only |
| `bundled-rc` | `contains(ref_name, 'rc')` | rc only |

Count: 4 `enable=` rules (verified by acceptance criterion `grep -c ... >= 4`).

### Tag Output Matrix (rc1 Dry-Run Expectation)

| Ref pushed | Lazy image tags | Bundled image tags |
|------------|-----------------|--------------------|
| `v0.1.0-rc1` | `:0.1.0-rc1`, `:latest-rc` | `:0.1.0-rc1-bundled`, `:bundled-rc` |
| `v0.1.0` | `:0.1.0`, `:latest` | `:0.1.0-bundled`, `:bundled` |
| `v0.2.0` | `:0.2.0`, `:latest` | `:0.2.0-bundled`, `:bundled` |

This is exactly the behavior D-20 leg (d) expects for the rc1 Plan 5 dry-run.

### Security Posture

- **Zero static PyPI tokens.** No `PYPI_TOKEN`, `PYPI_API_TOKEN`, or `TWINE_PASSWORD` references anywhere in the workflow (D-05). `uv publish` uses `ACTIONS_ID_TOKEN_REQUEST_TOKEN` + the PyPI-side Trusted Publisher config.
- **`id-token: write` scoped to one job only.** Grep confirms `id-token: write` appears exactly once — on `publish-pypi` — satisfying T-07-02 (spoofing mitigation).
- **Environment-scoped OIDC.** `environment: pypi` adds a second-layer check: PyPI Trusted Publisher config can additionally lock to environment name.
- **`packages: write` scoped to `publish-docker` only** — `GITHUB_TOKEN` for GHCR push cannot leak into release or PyPI jobs.
- **`contents: write` scoped to `create-release` only** — release creation has just enough permission.
- **D-23 regression gate.** `build` job scans unpacked wheel METADATA for `git+https` references; fails loudly before hitting the PyPI endpoint if `pyproject.toml` ever drifts back to a VCS dep.

## Tasks Executed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Create publish.yml with wait-for-ci + build + publish-pypi jobs | `988c6b7` | `.github/workflows/publish.yml` (created, 124 lines) |
| 2 | Add publish-docker (matrix) + create-release jobs | `7536c3e` | `.github/workflows/publish.yml` (extended, +103 lines) |

## Verification Evidence

All 9 Wave-0 structural tests from `tests/test_workflow_structure.py` pass with no skips:

```
tests/test_workflow_structure.py .........      [100%]
9 passed in 0.01s
```

Tests covered:

1. `test_publish_workflow_exists` — file created
2. `test_publish_workflow_triggers_on_version_tag` — `'v*'` trigger
3. `test_publish_workflow_has_oidc_permission` — `id-token: write`
4. `test_publish_workflow_has_ghcr_write_permission` — `packages: write`
5. `test_publish_workflow_uses_pypi_environment` — `environment: pypi`
6. `test_publish_workflow_waits_for_ci` — `lewagon/wait-on-check-action`
7. `test_publish_workflow_has_no_static_pypi_token` — forbidden-token absence
8. `test_publish_workflow_has_docker_multi_arch` — `linux/amd64` + `linux/arm64`
9. `test_publish_workflow_has_release_creation` — `softprops/action-gh-release`

Plus all explicit acceptance-grep probes from the plan (tag trigger, check-names verbatim, rc-enable count >= 4, build-push-action@v7, metadata-action@v6 x2, extract-release-notes@v3, target runtime-variant, per-variant cache scoping, wait-on-check count = 2, metadata-action count = 2).

## Deviations from Plan

**None.** This task was templated verbatim from RESEARCH patterns. The workflow content was copied as specified, tests pass without modification, and no deviation rules (Rules 1-4) triggered during execution.

Notes on benign style output:

- **yamllint warnings** (line-length, `on:` truthy, document-start) are style-only and were flagged as "optional" in the plan's verification section. They do not affect GitHub Actions parsing or execution. The `on:` truthy warning is a known yamllint false-positive for GitHub Actions (YAML 1.1 interprets `on` as boolean `true`; GitHub Actions requires the literal key `on`). Deferred to v0.2 CI polish if yamllint is added as a CI gate.

## Authentication Gates

None hit during plan-author time. Workflow-run-time gates (already documented in plan):

- **PyPI Trusted Publisher registration** — must be configured manually on pypi.org before the first tag push. Plan 5 rc1 checklist covers this.
- **GHCR image visibility flip** — GHCR images default to PRIVATE on first push; must be manually flipped to PUBLIC. Plan 5 rc1 checklist covers this.

## Plan 5 rc1 Dry-Run Must Verify

Per the plan's `<output>` section, the following legs of D-20 must be exercised by Plan 5's rc1 tag push (`v0.1.0-rc1`):

- [ ] (a) Tag push triggers the workflow (visible in GitHub Actions UI with name "Release").
- [ ] (b) `wait-for-ci` gates correctly — both smoke check-names satisfied on the tag's SHA before `build` starts.
- [ ] (c) PyPI upload succeeds via OIDC — no leaked token in workflow logs; `shopify-forecast-mcp==0.1.0rc1` visible on pypi.org/project/shopify-forecast-mcp/ as a pre-release.
- [ ] (d) GHCR shows 4 manifests under `ghcr.io/omnialta/shopify-forecast-mcp`: amd64+arm64 × lazy+bundled; tags `:0.1.0-rc1`, `:latest-rc`, `:0.1.0-rc1-bundled`, `:bundled-rc` present; `:latest` and `:bundled` NOT advanced (Pitfall 5 verification).
- [ ] (e) GitHub Release `v0.1.0-rc1` shows up with `dist/*.whl` + `dist/*.tar.gz` attached and `prerelease: true` flag set.

## Known Stubs

None. The workflow is feature-complete and self-contained. It references `Dockerfile` (Plan 3 deliverable) and `CHANGELOG.md` (Plan 4 deliverable) at workflow-run time only — author-time ordering is irrelevant per the plan's `<objective>` explicit note.

## Threat Flags

None. All new surface (cross-workflow API polling, OIDC exchange, GHCR push, Release creation) is covered by the plan's `<threat_model>` STRIDE register (T-07-02, T-07-04, T-07-05, T-07-08, T-07-09, T-07-10).

## Decisions Made

- **Use `lewagon/wait-on-check-action@v1.4.0` over `workflow_run`** — `workflow_run` fires only after the upstream workflow completes, but `ci.yml` does not trigger on tag push (D-03 locks us out of modifying ci.yml), so there is no `workflow_run` to chain onto. Polling the Checks API for the tag's SHA is the clean cross-workflow gate. Documented as RESEARCH Pattern 6.
- **Two `docker/metadata-action@v6` invocations inside one matrix job, guarded by `if: matrix.variant == 'lazy' / 'bundled'`** — alternative (single metadata step with conditional tags) was considered but rejected: cleaner isolation of tag patterns per variant, each step's `id:` can be referenced independently, and the ternary `${{ matrix.variant == 'lazy' && steps.meta-lazy.outputs.tags || steps.meta-bundled.outputs.tags }}` in `build-push-action` step reads cleanly.
- **Per-variant cache scope (`scope=${{ matrix.variant }}`)** — prevents the 450MB model weights in the bundled variant from invalidating the lazy variant's cache, per RESEARCH Pattern 3.

## Self-Check: PASSED

Verified by:

```
$ git log --oneline 4d92b3b..HEAD
7536c3e feat(07-02): add publish-docker matrix + create-release jobs
988c6b7 feat(07-02): add publish.yml with wait-for-ci, build, publish-pypi jobs

$ [ -f .github/workflows/publish.yml ] && echo FOUND
FOUND

$ uv run pytest -x -q tests/test_workflow_structure.py
9 passed in 0.01s
```

- [x] `.github/workflows/publish.yml` exists (227 lines)
- [x] Commit `988c6b7` exists
- [x] Commit `7536c3e` exists
- [x] All 5 jobs present (`wait-for-ci`, `build`, `publish-pypi`, `publish-docker`, `create-release`)
- [x] All 9 Wave-0 structural tests pass
- [x] All acceptance-grep probes from both tasks satisfied
