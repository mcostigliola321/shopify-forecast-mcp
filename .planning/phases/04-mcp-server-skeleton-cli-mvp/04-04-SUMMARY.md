---
phase: 04-mcp-server-skeleton-cli-mvp
plan: 04
subsystem: cli
tags: [argparse, cli, revenue, demand, json-output, markdown-output]
dependency_graph:
  requires: [04-03]
  provides: [shopify-forecast CLI with revenue and demand subcommands]
  affects: [cli.py]
tech_stack:
  added: []
  patterns: [argparse subcommands, async-with context manager, capsys test capture]
key_files:
  created: [tests/test_cli.py]
  modified: [src/shopify_forecast_mcp/cli.py]
decisions:
  - Used argparse (not click) per R9.3 minimal deps directive
  - CLI calls core library directly, no MCP imports (R9.3 enforced via AST test)
  - main() is sync, wraps asyncio.run() for async core calls
metrics:
  duration: 142s
  completed: 2026-04-16T16:58:00Z
  tasks_completed: 2
  tasks_total: 2
  test_count: 17
  full_suite_count: 155
---

# Phase 4 Plan 4: CLI Subcommands Summary

Replaced CLI stub with real argparse-based revenue and demand subcommands sharing the core forecasting library without MCP dependency.

## What Was Built

- **`shopify-forecast revenue`** -- Fetches orders via ShopifyClient, builds daily series, runs ForecastEngine, outputs markdown summary + table (or JSON with `--json`)
- **`shopify-forecast demand`** -- Groups orders by product/collection/SKU, forecasts each group, outputs markdown comparison table (or JSON)
- **Flags:** `--horizon`, `--context`, `--frequency`, `--json` (revenue); `--group-by`, `--group-value`, `--metric`, `--horizon`, `--top-n`, `--json` (demand)
- **Error handling:** Empty orders returns exit code 1 with stderr message; missing group value returns exit code 1

## Test Coverage

17 tests in `tests/test_cli.py`:
- 7 parser tests (defaults, overrides, choices)
- 1 AST no-MCP-import enforcement test
- 1 main() entry point test (no args returns 0)
- 3 revenue integration tests (markdown, JSON, empty orders)
- 5 demand integration tests (markdown, JSON, specific group, missing group, empty orders)

Full fast suite: 155 passed, 11 deselected.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | `65f6b83` | Replace CLI stub with argparse subcommands |
| 2 | `47cad8e` | Add CLI integration tests |

## Deviations from Plan

None -- plan executed exactly as written.

## Self-Check: PASSED
