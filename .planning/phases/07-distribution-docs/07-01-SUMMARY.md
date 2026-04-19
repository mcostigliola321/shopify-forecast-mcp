---
phase: 07-distribution-docs
plan: 01
subsystem: packaging
tags: [pypi, twine, uv, timesfm, pytest, pydantic]

# Dependency graph
requires:
  - phase: 01-scaffold-config
    provides: pyproject.toml, uv.lock, [project.dependencies] array
  - phase: 04-mcp-server-cli-mvp
    provides: src/shopify_forecast_mcp/mcp/tools.py (7 Pydantic ParamsModels)
  - phase: 06-advanced-tools
    provides: CompareScenariosParams (7th tool) in mcp/tools.py
provides:
  - PyPI-uploadable wheel + sdist (Requires-Dist contains no git+https)
  - timecopilot-timesfm PyPI fork wired as TimesFM source (D-23 satisfied)
  - huggingface-hub<1.0 compatibility pin (discovered during validation)
  - 5 Wave 0 structural test files (pytest-skips pre-artifact, asserts post-artifact)
  - scripts/gen_tools_doc.py — Pydantic ParamsModel -> markdown renderer
affects: [07-02 publish-pipeline, 07-03 docker, 07-04 docs, 07-05 release-cut]

# Tech tracking
tech-stack:
  added:
    - timecopilot-timesfm (PyPI fork of google-research/timesfm)
    - huggingface-hub pinned <1.0 (transitive compat)
  patterns:
    - Wave 0 test infrastructure — skip-gracefully-pre-artifact, assert-post-artifact
    - Introspection-based doc generation (Pydantic v2 model_json_schema)

key-files:
  created:
    - tests/test_workflow_structure.py
    - tests/test_changelog_structure.py
    - tests/test_dockerfile_structure.py
    - tests/test_docs_completeness.py
    - tests/test_claude_desktop_snippet.py
    - scripts/gen_tools_doc.py
  modified:
    - pyproject.toml (TimesFM dep swap + huggingface-hub pin)
    - uv.lock (regenerated atomically)

key-decisions:
  - "D-23 satisfied: replaced 'timesfm @ git+https://...' with 'timecopilot-timesfm>=0.2,<0.3'. PyPI rejects direct-URL Requires-Dist (HTTP 400)."
  - "Added huggingface-hub>=0.34,<1.0 pin. timecopilot-timesfm 0.2.1's _from_pretrained declares proxies+resume_download as required kwargs; huggingface_hub>=1.0 stopped passing them."
  - "Wave 0 test files use pytest.skip when downstream artifacts absent, so they're non-blocking for this plan but strictly assertive once Plans 2-4 land."
  - "gen_tools_doc.py is dev-time only (committed TOOLS.md is shipped artifact) — runtime schema introspection would add useless latency."

patterns-established:
  - "Dep swap + lock regen as single atomic commit — prevents dep/lock drift."
  - "Skip-pre-artifact test idiom: every structural test has a pytest.skip guard on its target file so Wave 0 is non-blocking."
  - "Pydantic v2 model_json_schema() as single source of truth for tool parameter docs — eliminates drift between code and docs."

requirements-completed: [R11.1, R11.2, R11.3, R11.4, R12.1, R12.2, R12.3, R12.4]

# Metrics
duration: ~30min
completed: 2026-04-19
---

# Phase 07 Plan 01: Dep Swap & Wave 0 Test Infrastructure Summary

**Swapped TimesFM dep from git+https direct URL to `timecopilot-timesfm` PyPI fork, pinned huggingface-hub<1.0 for fork-compat, added 5 structural test files and a Pydantic->markdown doc generator — unblocking the entire Phase 7 release pipeline.**

## Performance

- **Duration:** ~30 min (including throwaway-venv validation, fork incompatibility discovery, and lock regen)
- **Started:** 2026-04-19T17:16:00Z (approx)
- **Completed:** 2026-04-19T17:46:00Z
- **Tasks:** 3/3 completed
- **Files modified:** 8 (6 created + 2 modified)

## Accomplishments

- **D-23 satisfied** — `pyproject.toml` dep now reads `timecopilot-timesfm>=0.2,<0.3`; wheel METADATA verified to contain no `git+https://` and to include `Requires-Dist: timecopilot-timesfm<0.3,>=0.2`. `uv publish` will no longer be rejected by warehouse at upload.
- **Fork-compat pin discovered + applied** — `huggingface-hub>=0.34,<1.0` prevents `TypeError: _from_pretrained() missing 2 required keyword-only arguments: 'proxies' and 'resume_download'` (see Deviations §Rule 3).
- **Full test suite green** — 318 passed, 48 skipped (47 Wave 0 pre-artifact skips + 1 `SHOPIFY_FORECAST_SHOP` integration skip). Zero regressions against the TimesFM replacement.
- **`twine check dist/*` PASSED** for both wheel (`shopify_forecast_mcp-0.1.0-py3-none-any.whl`) and sdist (`shopify_forecast_mcp-0.1.0.tar.gz`).
- **5 Wave 0 test files** committed — 48 individual `def test_*` functions total, all skip gracefully when their downstream artifacts don't exist yet and will hard-assert once Plans 2-4 land.
- **`scripts/gen_tools_doc.py`** renders valid markdown with exactly 7 tool sections, one per MCP tool, via Pydantic v2 `model_json_schema()` introspection. No new runtime deps.

## Task Commits

Each task was committed atomically:

1. **Task 1: Swap TimesFM dep to timecopilot-timesfm and regenerate lock (D-23)** — `6390197` (chore)
2. **Task 2: Create Wave 0 structural test infrastructure (5 test files)** — `862f3b7` (test)
3. **Task 3: Create scripts/gen_tools_doc.py Pydantic-to-markdown generator** — `779d7e9` (feat)

## Files Created/Modified

- `pyproject.toml` — Replaced `timesfm @ git+https://...` with `timecopilot-timesfm>=0.2,<0.3`; added `huggingface-hub>=0.34,<1.0` pin with inline comment explaining the transitive compat constraint.
- `uv.lock` — Regenerated: removed `timesfm v2.0.0 (f085b907)`, added `timecopilot-timesfm v0.2.1`, pinned `huggingface-hub v0.36.2` (the latest `<1.0`), plus transitive deps (safetensors, scikit-learn, scipy, wandb, gitpython, etc.). Pre-change SHA256: `7d9bf6d29650f5c7614843b243c7b9efb73e9bfb3909a2ce0f5411dcf92c883a`. Post-change SHA256: `8dbc0c0ea2ae1dad5cef90003511912ce5d87840fbdb07d1374606d7948180fd`.
- `tests/test_workflow_structure.py` — 9 tests asserting `.github/workflows/publish.yml` structure (OIDC, GHCR perms, env=pypi, wait-for-ci, no static tokens, multi-arch, release creation).
- `tests/test_changelog_structure.py` — 8 tests asserting `CHANGELOG.md` Keep-a-Changelog format, `[Unreleased]`/`[0.1.0]` sections, ≥3 MCP tool names in `[0.1.0]` Added.
- `tests/test_dockerfile_structure.py` — 12 tests asserting `Dockerfile`/`docker-entrypoint.sh`/`.dockerignore` structure (python:3.11-slim base, uv from official image, multistage runtime-lazy + runtime-bundled, HF_HOME=/opt/hf-cache, JSON-array ENTRYPOINT, USER app, verb dispatch, exec for signals, dockerignore excludes).
- `tests/test_docs_completeness.py` — 17 tests asserting `README.md`/`docs/SETUP.md`/`docs/TOOLS.md`/`docs/ARCHITECTURE.md` completeness (README size+sections+uvx+snippet, SETUP scopes+env vars, TOOLS per-tool sections + anchors, ARCHITECTURE ≥3 mermaid + dual-backend, no placeholder rot).
- `tests/test_claude_desktop_snippet.py` — 2 tests (one parametrized x2) extracting the first ```json fenced block and validating `mcpServers` shape + `uvx` command.
- `scripts/gen_tools_doc.py` — Standalone dev-time CLI; introspects the 7 ParamsModel classes via `model_json_schema()` and emits markdown with anchor-linked index + per-tool parameter tables. Stdlib + `shopify_forecast_mcp.mcp.tools` only. Executable (chmod +x) with `#!/usr/bin/env python3` shebang.

## Decisions Made

- **Kept `[tool.hatch.metadata] allow-direct-references = true` in pyproject.toml.** It becomes vestigial after the dep swap, but removing it is out-of-scope per plan instruction — avoids noise and allows future dev-mode git sources without a config flip.
- **Pinned `huggingface-hub>=0.34,<1.0`** (not just `<1.0`). Floor chosen to match what `transformers` and the TimesFM model ecosystem commonly require in practice (0.34+ has `hf_hub_download` + standard cache behavior). Upper bound must stay `<1.0` until upstream `timecopilot-timesfm>=0.3` relaxes `_from_pretrained` to accept `**kwargs` — inline comment in `pyproject.toml` calls this out.
- **Wave 0 `test_*_exists` style:** rather than hard-assert existence, each uses `pytest.skip(...)` pre-artifact. Matches the plan's explicit acceptance criterion that these tests "run to completion (skipping downstream artifacts cleanly)." A subsequent executor for Plans 2-4 will see the skipped tests move to passing as artifacts land — acting as a passive progress bar.
- **gen_tools_doc.py design:** Dev-time CLI that emits stdout by default, `-o` flag for file output. Script order of tools matches README Tools table order (forecast_revenue → forecast_demand → analyze_promotion → detect_anomalies → compare_periods → compare_scenarios → get_seasonality). Anchor slugs use hyphens (`forecast-revenue`) for GitHub markdown anchor compatibility.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added `huggingface-hub<1.0` compatibility pin**

- **Found during:** Task 1, Step 5 (full pytest run against the new dep graph)
- **Issue:** `tests/test_forecaster.py::TestFirstRunLog::test_first_run_log_message` failed with `TypeError: TimesFM_2p5_200M_torch._from_pretrained() missing 2 required keyword-only arguments: 'proxies' and 'resume_download'`. Investigation showed `timecopilot-timesfm` 0.2.1's `_from_pretrained` classmethod still declares `proxies` and `resume_download` as required keyword-only args, but `huggingface_hub>=1.0.0` removed them from the `ModelHubMixin.from_pretrained()` call site. A throwaway-venv check confirmed the fork works fine against `huggingface-hub<1.0`.
- **Fix:** Added `"huggingface-hub>=0.34,<1.0"` to `[project.dependencies]` in `pyproject.toml` with an inline comment explaining the constraint. Regenerated `uv.lock` — resolver picked `huggingface-hub 0.36.2`.
- **Files modified:** `pyproject.toml`, `uv.lock`
- **Verification:** `uv run pytest -x -q` → 318 passed, 48 skipped. `uv build` still produces PyPI-valid METADATA (now also includes `Requires-Dist: huggingface-hub<1.0,>=0.34`). `twine check` still passes.
- **Committed in:** `6390197` (folded into the atomic dep-swap commit per plan's Step 3 guidance)

**2. [Rule 1 - Bug] Fixed Wave 0 `test_*_exists` tests to skip pre-artifact instead of hard-failing**

- **Found during:** Task 2 (initial pytest run of Wave 0 files)
- **Issue:** The plan's literal test code for `test_publish_workflow_exists`, `test_changelog_exists`, `test_dockerfile_exists`, `test_entrypoint_script_exists`, `test_dockerignore_exists`, and four docs `test_*_md_exists` used bare `assert X.exists(), ...` which hard-fails pre-artifact — contradicting the plan's own acceptance criterion that Wave 0 tests "run to completion (skipping downstream artifacts cleanly)" and the `<done>` line "skip gracefully pre-artifact". Follow-on tests that read text via `WORKFLOW.read_text()` directly (rather than going through `_load()`) had the same flaw.
- **Fix:** Added `pytest.skip(...)` guards to every existence test and introduced a `_read_text()` helper in `test_workflow_structure.py` that's used by all text-reading tests. For `test_readme_not_placeholder`, added a `_read_substantial_readme()` helper that skips while README.md is still the 337-byte scaffold placeholder, so the 5 downstream README tests also skip cleanly pre-rewrite.
- **Files modified:** `tests/test_workflow_structure.py`, `tests/test_changelog_structure.py`, `tests/test_dockerfile_structure.py`, `tests/test_docs_completeness.py`
- **Verification:** `uv run pytest -q tests/test_*_structure.py tests/test_docs_completeness.py tests/test_claude_desktop_snippet.py` → 2 passed, 47 skipped, 0 failed.
- **Committed in:** `862f3b7`

---

**Total deviations:** 2 auto-fixed (1 Rule 3 blocking, 1 Rule 1 bug)
**Impact on plan:** Both auto-fixes were necessary for correctness — Rule 3 was a transitive-dep ABI break that would have broken the full suite; Rule 1 fixed internal contradiction between plan acceptance criteria and literal test code. No scope creep; plan intent preserved.

## Issues Encountered

- **TimesFM fork transitive-dep drift** — timecopilot-timesfm 0.2.1 hasn't been updated to match huggingface_hub 1.x's `from_pretrained` contract change. Fix is the <1.0 pin above. Action item for a future plan: watch for timecopilot-timesfm>=0.3 (which should relax the signature to `**kwargs`); when it lands, the hub pin can be lifted. Documented via inline comment in `pyproject.toml`.

## D-23 Satisfaction Evidence

```
$ unzip -p dist/*.whl '*/METADATA' | grep -E '^Requires-Dist:'
Requires-Dist: holidays>=0.50
Requires-Dist: httpx>=0.27
Requires-Dist: huggingface-hub<1.0,>=0.34
Requires-Dist: mcp<2.0,>=1.27
Requires-Dist: numpy<3,>=1.26
Requires-Dist: pandas>=2.2
Requires-Dist: pydantic-settings>=2.3
Requires-Dist: pydantic>=2.7
Requires-Dist: python-dateutil>=2.9
Requires-Dist: timecopilot-timesfm<0.3,>=0.2
Requires-Dist: torch>=2.4
<no git+https:// lines>
```

```
$ uvx --from twine twine check dist/*
Checking dist/shopify_forecast_mcp-0.1.0-py3-none-any.whl: PASSED
Checking dist/shopify_forecast_mcp-0.1.0.tar.gz: PASSED
```

## Fork-Validation Surprises

- **No import issues** — `from timesfm import TimesFM_2p5_200M_torch` works identically against the fork (the fork ships under the `timesfm` top-level package name).
- **One ABI surprise** — the `_from_pretrained` signature mismatch documented under Deviations §Rule 3. Resolved via the hub pin; did not require any changes to `src/` code.
- **No version conflicts during resolution** — `uv lock` added 15 packages and removed 1 (the git+https timesfm). Resolution converged in 370ms.

## Wave 0 Test Inventory

| File | Tests | Skipped (pre-artifact) | Covers |
|---|---|---|---|
| `tests/test_workflow_structure.py` | 9 | 9 | R12.1, R12.4, D-01, D-03, D-04, D-05, D-07 |
| `tests/test_changelog_structure.py` | 8 | 8 | D-21 |
| `tests/test_dockerfile_structure.py` | 12 | 12 | R12.2, R12.3, D-06, D-08, D-10, RESEARCH Pitfalls 3/8 |
| `tests/test_docs_completeness.py` | 17 | 16 (test_readme_exists passes — scaffold exists) | R11.1, R11.2, R11.3, R11.4, R11.5, D-13..D-18 |
| `tests/test_claude_desktop_snippet.py` | 2 (parametrized to 3 cases) | 3 | R11.5, D-13 |

Total `def test_*` functions: 48. All 48 ran in <60s; combined with the plan-mandated `<automated>` verify commands for each task, every downstream plan has sub-minute structural feedback available.

## Next Phase Readiness

- **Plan 07-02 (publish pipeline) unblocked** — when it creates `.github/workflows/publish.yml`, the 9 tests in `test_workflow_structure.py` will flip from skipped to asserting. OIDC + GHCR + wait-for-ci + no-static-token requirements are pre-locked.
- **Plan 07-03 (Docker) unblocked** — 12 tests in `test_dockerfile_structure.py` will assert python:3.11-slim base, multistage runtime-lazy/bundled, HF_HOME cache, JSON-array ENTRYPOINT, non-root user, entrypoint verb dispatch, and dockerignore hygiene.
- **Plan 07-04 (docs) unblocked** — 17 tests in `test_docs_completeness.py` + 2 in `test_claude_desktop_snippet.py` + 8 in `test_changelog_structure.py` will assert README/SETUP/TOOLS/ARCHITECTURE completeness. `scripts/gen_tools_doc.py` can be invoked to seed `docs/TOOLS.md`.
- **Plan 07-05 (release cut)** can now safely attempt `v0.1.0-rc1` via `uv publish` — METADATA is PyPI-valid.
- **No open blockers.** The `huggingface-hub<1.0` pin is tracked as a follow-up to lift once timecopilot-timesfm>=0.3 ships.

## Self-Check: PASSED

File existence:
- `tests/test_workflow_structure.py` — FOUND
- `tests/test_changelog_structure.py` — FOUND
- `tests/test_dockerfile_structure.py` — FOUND
- `tests/test_docs_completeness.py` — FOUND
- `tests/test_claude_desktop_snippet.py` — FOUND
- `scripts/gen_tools_doc.py` — FOUND (executable)
- `pyproject.toml` (modified) — FOUND
- `uv.lock` (modified) — FOUND

Commits exist:
- `6390197` — FOUND (chore(07-01): swap TimesFM dep to timecopilot-timesfm (D-23))
- `862f3b7` — FOUND (test(07-01): add 5 Wave 0 structural test files for downstream plans)
- `779d7e9` — FOUND (feat(07-01): add scripts/gen_tools_doc.py Pydantic->markdown generator)

All success criteria in plan met:
- [x] `pyproject.toml` uses `timecopilot-timesfm>=0.2,<0.3`
- [x] `uv.lock` regenerated atomically
- [x] `uv build` produces wheel + sdist with no direct-URL Requires-Dist
- [x] `twine check dist/*` passes
- [x] Full pytest green (318 passed against new TimesFM source)
- [x] 5 Wave 0 test files exist and run cleanly (skip gracefully pre-artifact)
- [x] `scripts/gen_tools_doc.py` renders valid markdown with all 7 tool sections

---
*Phase: 07-distribution-docs*
*Completed: 2026-04-19*
