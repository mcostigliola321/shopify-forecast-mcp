---
phase: "04-mcp-server-skeleton-cli-mvp"
plan: "01"
subsystem: "mcp-server"
tags: [mcp, fastmcp, lifespan, server, stdio]
dependency_graph:
  requires: [config, shopify-client, forecaster]
  provides: [mcp-server-instance, app-context, main-entry-point]
  affects: [mcp-tools, cli-entry-point]
tech_stack:
  added: [mcp.server.fastmcp.FastMCP, mcp.server.fastmcp.Context]
  patterns: [lifespan-context-manager, dataclass-app-context, stderr-only-logging]
key_files:
  created:
    - tests/test_mcp_server.py
  modified:
    - src/shopify_forecast_mcp/mcp/server.py
    - src/shopify_forecast_mcp/mcp/__init__.py
decisions:
  - "Used get_settings() factory instead of direct Settings() construction for consistency"
  - "ShopifyClient constructed with full Settings object (matches existing constructor)"
  - "ForecastEngine loaded via get_engine() singleton accessor then .load()"
  - "Log level overridden from Settings.log_level at lifespan entry"
metrics:
  duration: "2 minutes"
  completed: "2026-04-16"
  tasks_completed: 2
  tasks_total: 2
  test_count: 6
  test_pass: 6
---

# Phase 4 Plan 01: FastMCP Server Skeleton Summary

FastMCP server with lifespan-managed AppContext injecting ShopifyClient and ForecastEngine, stderr-only logging, stdio transport entry point.

## What Was Built

Replaced the stub `mcp/server.py` with a production FastMCP server skeleton:

1. **AppContext dataclass** -- holds `shopify: ShopifyClient` and `forecaster: ForecastEngine`, yielded by lifespan for tool injection via `ctx.request_context.lifespan_context`.

2. **Lifespan context manager** -- initializes settings, constructs ShopifyClient, loads ForecastEngine singleton, yields AppContext, and closes the HTTP client on shutdown.

3. **FastMCP instance** -- `mcp = FastMCP("shopify-forecast-mcp", lifespan=lifespan)` ready for tool registration in Plans 02-03.

4. **Sync main() entry point** -- calls `mcp.run(transport="stdio")`, compatible with pyproject.toml console_scripts.

5. **stderr-only logging** -- `logging.basicConfig(stream=sys.stderr)` with format string. Zero print() calls (verified by AST test).

## Task Completion

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Replace server.py stub with FastMCP server + AppContext lifespan | d49811c | server.py, __init__.py |
| 2 | Write server instantiation and stdout-silence tests | 27781cd | test_mcp_server.py |

## Test Results

```
112 passed, 11 deselected in 4.44s
```

6 new tests in `test_mcp_server.py`:
- `test_mcp_instance` -- FastMCP type and name
- `test_app_context_fields` -- dataclass field introspection
- `test_no_print_in_server` -- AST-level print() check
- `test_stderr_logging` -- logging.basicConfig with sys.stderr
- `test_main_callable` -- main() is callable
- `test_lifespan_context_manager` -- mocked lifespan yields AppContext, close called

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

None -- all functionality specified in the plan is fully wired.

## Self-Check: PASSED

All 3 files exist. Both commits (d49811c, 27781cd) verified in git log.
