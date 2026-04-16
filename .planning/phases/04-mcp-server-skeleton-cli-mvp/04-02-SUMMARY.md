---
phase: 04-mcp-server-skeleton-cli-mvp
plan: 02
subsystem: mcp
tags: [fastmcp, pydantic, timesfm, forecast, mcp-tool]

# Dependency graph
requires:
  - phase: 04-01
    provides: FastMCP server instance with AppContext lifespan
  - phase: 03
    provides: timeseries aggregation, ForecastEngine, ForecastResult
  - phase: 02
    provides: ShopifyClient.fetch_orders()
provides:
  - forecast_revenue MCP tool with Pydantic input schema
  - Full pipeline: fetch orders -> daily series -> resample -> clean -> forecast -> markdown
affects: [04-03, 04-04, 05, 06]

# Tech tracking
tech-stack:
  added: []
  patterns: [mcp-tool-registration-via-import, pydantic-params-with-literal-frequency, friendly-markdown-error-returns]

key-files:
  created:
    - src/shopify_forecast_mcp/mcp/tools.py
    - tests/test_mcp_tools_revenue.py
  modified:
    - src/shopify_forecast_mcp/mcp/server.py

key-decisions:
  - "User-facing frequency names (daily/weekly/monthly) mapped to pandas codes via FREQ_MAP"
  - "Errors caught and returned as markdown strings, never raised to MCP runtime"
  - "Tool auto-registers via import at bottom of server.py"

patterns-established:
  - "MCP tool pattern: Pydantic params + async handler + ctx.info() progress + try/except markdown errors"
  - "MockCtx class for testing MCP tool handlers without real MCP runtime"

requirements-completed: [R7.4, R7.6, R7.7, R7.10, R8.1]

# Metrics
duration: 2min
completed: 2026-04-16
---

# Phase 4 Plan 2: forecast_revenue Tool Summary

**forecast_revenue MCP tool with Pydantic input validation, full Shopify-to-TimesFM pipeline, and markdown output**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-16T16:47:54Z
- **Completed:** 2026-04-16T16:49:40Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- ForecastRevenueParams Pydantic model with bounded validation (horizon 1-365, context 30-1095, Literal frequency)
- @mcp.tool() decorated async handler implementing full pipeline: fetch_orders -> orders_to_daily_series -> resample_series -> clean_series -> forecast -> ForecastResult -> markdown
- Error handling returns friendly markdown with type + message, traceback only to stderr logs
- 11 tests covering Pydantic validation, happy path, empty orders, error handling, chart data, and ctx.info() calls

## Task Commits

Each task was committed atomically:

1. **Task 1: Failing tests for forecast_revenue** - `f2c89c3` (test) - TDD RED
2. **Task 1+2: Implement forecast_revenue tool + server import** - `b285df0` (feat) - TDD GREEN

_TDD approach: tests written first (RED), then implementation to pass all 11 tests (GREEN)._

## Files Created/Modified
- `src/shopify_forecast_mcp/mcp/tools.py` - ForecastRevenueParams model and forecast_revenue tool handler
- `src/shopify_forecast_mcp/mcp/server.py` - Added tools import for auto-registration
- `tests/test_mcp_tools_revenue.py` - 11 tests with MockCtx, mocked Shopify + forecaster

## Decisions Made
- Used Literal["daily", "weekly", "monthly"] for user-friendly frequency input, mapped to pandas codes via FREQ_MAP dict
- Errors caught at handler level and returned as markdown strings (never raised to MCP runtime) per R7.7
- Tool registers via `import shopify_forecast_mcp.mcp.tools` at bottom of server.py (cleanest pattern for FastMCP)
- MockCtx class created for testing tool handlers without constructing real MCP Context objects

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Test Results

```
123 passed, 11 deselected in 1.68s
```

Full non-slow test suite passes.

## Next Phase Readiness
- forecast_revenue tool ready for integration with Claude Desktop
- Pattern established for additional tools (04-03 will add more tools)
- MockCtx pattern reusable for all future tool tests

---
*Phase: 04-mcp-server-skeleton-cli-mvp*
*Completed: 2026-04-16*
