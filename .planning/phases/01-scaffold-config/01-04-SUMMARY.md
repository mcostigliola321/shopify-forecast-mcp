---
phase: 01-scaffold-config
plan: 04
subsystem: scaffold
tags: [ci, github-actions, hygiene, gitignore]
requires: [01-03]
provides: [ci-pipeline, repo-hygiene]
affects: [.gitignore, .python-version, .github/workflows/ci.yml]
tech-stack:
  added: [github-actions, astral-sh/setup-uv@v3, actions/upload-artifact@v4]
  patterns: [matrix-os, frozen-lockfile-ci, smoke-test-on-import]
key-files:
  created:
    - .gitignore
    - .python-version
    - .github/workflows/ci.yml
  modified: []
decisions:
  - "Matrix on os only (ubuntu-latest, macos-latest); single Python 3.11 (requires-python pin)"
  - "uv sync --frozen to enforce lockfile discipline"
  - "Settings(_env_file=None) in smoke test so CI env vars are the sole source"
  - "upload-artifact name suffixed with matrix.os to avoid v4 duplicate-name conflict"
metrics:
  duration: ~5min
  completed: 2026-04-13
  tasks_committed: 2
  checkpoints_pending: 1
---

# Phase 1 Plan 4: CI & Repo Hygiene Summary

Stand up `.gitignore`, `.python-version`, and a GitHub Actions CI workflow that exercises the full Phase 1 contract (uv sync → uv build → import smoke → pytest) on Linux and macOS.

## Files Created

| Path | Purpose |
|---|---|
| `.gitignore` | Python + uv + venv + .env + HF cache + IDE excludes. Does NOT ignore `.env.example` or `uv.lock`. |
| `.python-version` | Single line `3.11` — lets uv/pyenv pick latest 3.11 patch. |
| `.github/workflows/ci.yml` | Matrix CI (ubuntu-latest + macos-latest) running checkout → setup-uv → `uv python install 3.11` → `uv sync --frozen` → `uv build` → import smoke test → `pytest -x -q` → upload dist artifact. |

## Local Verification

- `uv run pytest -x -q` → **7 passed in 0.05s** (after writing the workflow, with `SHOPIFY_FORECAST_SHOP` / `SHOPIFY_FORECAST_ACCESS_TOKEN` set).
- YAML parsed cleanly via `uv run python -c "import yaml; yaml.safe_load(...)"`.
- All `<verify>` automated checks for Tasks 1 and 2 passed.

## Commits

| Task | Hash | Message |
|---|---|---|
| 1 | `6a177e1` | chore(01-04): add .gitignore and .python-version hygiene files |
| 2 | `969866a` | ci(01-04): add GitHub Actions matrix workflow with install, build, and config smoke test |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] upload-artifact v4 duplicate-name conflict**
- **Found during:** Task 2 review
- **Issue:** `actions/upload-artifact@v4` (unlike v3) errors out if two matrix legs upload artifacts with the same `name`. The plan's literal YAML used `name: dist` for both `ubuntu-latest` and `macos-latest` legs, which would have failed CI on the second leg with `Failed to CreateArtifact: an artifact with this name already exists`.
- **Fix:** Changed `name: dist` → `name: dist-${{ matrix.os }}` so each leg uploads to a distinct artifact bucket. Both wheels/sdists are still inspectable in the GH UI.
- **Files modified:** `.github/workflows/ci.yml`
- **Commit:** `969866a`

No other deviations.

## Task 3: Awaiting Human Verification (BLOCKING)

**Task 3** is a `checkpoint:human-verify` gate. It is **not** code — it is the requirement that CI actually run green on a real GitHub remote before Phase 1 can be declared done.

**What the user needs to do:**
1. Add a git remote pointing at the GitHub repo (e.g. `github.com/omnialta/shopify-forecast-mcp`) if one doesn't exist.
2. Push the current branch (or push to a feature branch and open a PR).
3. Watch the `CI / Smoke (Python 3.11, ubuntu-latest)` and `CI / Smoke (Python 3.11, macos-latest)` jobs in the Actions tab.
4. Expect: all 8 steps green on both legs. Smoke step prints `ok 2026-04`. Pytest shows 7 passing. `dist-ubuntu-latest` and `dist-macos-latest` artifacts each contain a `.whl` + `.tar.gz`.

**Until CI is green on a remote, Phase 1 is not closed.** The orchestrator should hand this back to the user for the push + verification step.

Common failure modes to watch for (from the plan):
- Frozen-lock mismatch → `uv lock` locally, recommit, repush.
- TimesFM git dep fails → stale SHA, rerun Plan 02 Task 1 with fresher SHA.
- Torch CPU index 404 → `[[tool.uv.index]]` name must match `[tool.uv.sources]` reference.
- Smoke `ImportError` → src layout / wheel target path issue.

## Phase 1 Status

All Phase 1 code artifacts are in place: `pyproject.toml` + locked deps, `src/shopify_forecast_mcp/config.py` Settings module, `.env.example`, LICENSE, README, `.gitignore`, `.python-version`, and `.github/workflows/ci.yml`. Local pytest is green. The only remaining gate is **CI green on a real push** — once that lands, Phase 1 is fully complete and Phase 2 (Shopify Client) can begin.

## Self-Check: PASSED

- `.gitignore` — FOUND
- `.python-version` — FOUND
- `.github/workflows/ci.yml` — FOUND
- commit `6a177e1` — FOUND
- commit `969866a` — FOUND
