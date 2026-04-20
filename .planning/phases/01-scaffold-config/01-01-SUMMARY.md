---
phase: 01-scaffold-config
plan: 01
subsystem: packaging
tags: [scaffold, uv, hatchling, pep639]
requires: []
provides:
  - importable_package: shopify_forecast_mcp
  - entry_point: shopify-forecast (cli stub)
  - entry_point: shopify-forecast-mcp (server stub)
  - build_backend: hatchling
affects: []
tech_added:
  - hatchling (build backend)
key_files:
  created:
    - pyproject.toml
    - LICENSE
    - README.md
    - src/shopify_forecast_mcp/__init__.py
    - src/shopify_forecast_mcp/__main__.py
    - src/shopify_forecast_mcp/cli.py
    - src/shopify_forecast_mcp/core/__init__.py
    - src/shopify_forecast_mcp/mcp/__init__.py
    - src/shopify_forecast_mcp/mcp/server.py
  modified: []
decisions:
  - Wrote pyproject.toml manually instead of `uv init --package` (directory non-empty due to PRD file)
  - dependencies = [] left empty; Plan 02 owns dependency resolution
  - Both stubs print exclusively to stderr to encode R7.8 (stdio MCP framing on stdout) from day one
metrics:
  tasks_completed: 2
  files_created: 9
  commits: 2
  completed_date: 2026-04-13
---

# Phase 01 Plan 01: Scaffold Package Skeleton Summary

One-liner: uv-managed `shopify_forecast_mcp` package scaffolded with hatchling backend, PEP 639 SPDX MIT license, Python `>=3.11,<3.12` pin, and two stub console-script entry points (cli + mcp server) printing to stderr.

## What Was Built

**Task 1 — Package skeleton (commit `436bd7e`)**
- `pyproject.toml` written manually (uv init skipped — non-empty directory). Contains: hatchling build backend, name `shopify-forecast-mcp`, version `0.1.0`, `requires-python = ">=3.11,<3.12"`, PEP 639 `license = "MIT"` + `license-files = ["LICENSE"]`, MIT trove classifier, `dependencies = []`, both `[project.scripts]` entries, `[project.urls]`, and `[tool.hatch.build.targets.wheel] packages = ["src/shopify_forecast_mcp"]`.
- Source tree: `src/shopify_forecast_mcp/__init__.py` (`__version__ = "0.1.0"`), `__main__.py` (delegates to `cli.main`), `core/__init__.py` (empty marker), `mcp/__init__.py` (empty marker).
- `LICENSE` — canonical MIT text with `Copyright (c) 2026 OmniAlta LLC`.
- `README.md` — WIP placeholder referencing `.planning/PROJECT.md`.

**Task 2 — Entry-point stubs (commit `d94a463`)**
- `src/shopify_forecast_mcp/cli.py` — sync `main() -> int` returning 0, prints `"shopify-forecast: not implemented (Phase 4)"` to **stderr**.
- `src/shopify_forecast_mcp/mcp/server.py` — sync `main() -> int` returning 0, prints `"shopify-forecast-mcp: not implemented (Phase 4)"` to **stderr**, with R7.8 docstring warning.

## Success Criteria Verification

- [x] `pyproject.toml` exists with hatchling, PEP 639 license, Python 3.11 pin, two console scripts (`shopify_forecast_mcp.cli:main` + `shopify_forecast_mcp.mcp.server:main`).
- [x] Source tree has all 6 required files under `src/shopify_forecast_mcp/`.
- [x] Both stubs expose `main()` and print to stderr (verified with grep).
- [x] No deps added (`dependencies = []`).
- [x] LICENSE + README.md exist with required markers (`Copyright (c) 2026 OmniAlta LLC`, `WIP`).
- [x] Both stub modules parse as valid Python (verified via `ast.parse`).
- [x] All Task 1 verification commands passed.

Note: `uv build` and `uv sync` validation are deferred to Plan 02 (which owns dependencies and the first sync). Plan 01 produces only the static files.

## Deviations from Plan

None functionally. Minor procedural note: `uv init --package` was not attempted because the project root contains the PRD file (non-empty directory) — fell back to manually writing `pyproject.toml` from the canonical skeleton in `.planning/research/packaging.md`, which the plan explicitly authorized.

## Self-Check: PASSED

- Files: all 9 created files exist on disk.
- Commits: `436bd7e` and `d94a463` present in git history.
