---
phase: 05-analytics-covariates-remaining-tools
plan: 03
subsystem: mcp/tools + cli
tags: [mcp-tools, cli, analytics, promotion, anomaly-detection, comparison, seasonality]

# Dependency graph
requires:
  - phase: 05-01
    provides: analyze_promotion, detect_anomalies, compare_periods, get_seasonality, AnalyticsResult
  - phase: 05-02
    provides: covariates module for holiday event labeling
provides:
  - Four MCP tool handlers (analyze_promotion, detect_anomalies, compare_periods, get_seasonality)
  - Two CLI subcommands (promo, compare) with --yoy/--mom shortcuts
  - _resolve_compare_dates helper for YoY/MoM/custom date resolution
affects: []

# Tech tracking
tech-stack:
  added: [dateutil.relativedelta]
  patterns:
    - "MCP tool pattern: Pydantic BaseModel params + @mcp.tool() + async handler + ctx.info() + try/except"
    - "CLI subcommand pattern: argparse subparser + async _run_X + json_output flag"
    - "Date resolution helper for --yoy/--mom shortcuts using relativedelta"

key-files:
  created:
    - tests/test_mcp_tools_analytics.py
  modified:
    - src/shopify_forecast_mcp/mcp/tools.py
    - src/shopify_forecast_mcp/cli.py
    - tests/test_cli.py

key-decisions:
  - "detect_anomalies MCP tool splits series into context+lookback, forecasts the lookback window, compares actuals vs forecast bands"
  - "Holiday event labeling in detect_anomalies uses optional import from covariates module (graceful fallback)"
  - "CLI JSON output for promo/compare uses sections/summary/recommendations structure from AnalyticsResult"
  - "_resolve_compare_dates centralizes YoY/MoM/custom date logic for the compare CLI verb"

patterns-established:
  - "Analytics MCP tool: parse dates with fromisoformat + try/except, validate ranges, fetch orders, call core function, return to_markdown()"
  - "detect_anomalies orchestration: fetch orders -> build series -> forecast context -> compare actuals vs bands"

requirements-completed: [R8.3, R8.4, R8.5, R8.7, R9.2]

# Metrics
duration: ~10min
completed: 2026-04-18
---

# Phase 05 Plan 03: MCP Tools & CLI for Analytics Summary

**Four MCP tool handlers wired to analytics core (promotion, anomalies, comparison, seasonality) plus promo and compare CLI subcommands with YoY/MoM date shortcuts, backed by 31 new tests**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-04-18T17:17:03Z
- **Completed:** 2026-04-18T17:27:00Z
- **Tasks:** 3/3
- **Files modified:** 4

## Accomplishments

- Added 4 MCP tool handlers to `mcp/tools.py`: analyze_promotion, compare_periods, get_seasonality, detect_anomalies -- all following the established Pydantic params + async handler + try/except pattern
- detect_anomalies is the most complex tool: splits time series into context+lookback, runs forecaster to establish expected values, then compares actuals against quantile bands; optionally labels holidays via covariates module
- Added `promo` CLI subcommand with --start, --end, --name, --baseline-days, --json flags
- Added `compare` CLI subcommand with --yoy, --mom, custom date range flags, and --json output
- Created _resolve_compare_dates helper centralizing YoY/MoM/custom date resolution using dateutil.relativedelta
- All tools validate date inputs with fromisoformat() wrapped in try/except (T-05-08, T-05-10)
- All tools return markdown error strings on failure, never stack traces (T-05-11)
- Total @mcp.tool() count is now 6 (2 existing forecast tools + 4 new analytics tools)
- Total CLI subcommands: 5 (revenue, demand, auth, promo, compare)

## Task Commits

Git commits could not be created due to permission restrictions in the execution environment. Files are ready to be committed:

**Task 1 (analyze_promotion, compare_periods, get_seasonality MCP tools):**
- `src/shopify_forecast_mcp/mcp/tools.py` (modified -- added 3 tool handlers + Pydantic params)
- `tests/test_mcp_tools_analytics.py` (new -- 11 tests)

**Task 2 (detect_anomalies MCP tool):**
- `src/shopify_forecast_mcp/mcp/tools.py` (modified -- added detect_anomalies handler)
- `tests/test_mcp_tools_analytics.py` (modified -- added 4 detect_anomalies tests)

**Task 3 (CLI promo and compare subcommands):**
- `src/shopify_forecast_mcp/cli.py` (modified -- added promo/compare subparsers, _run_promo, _resolve_compare_dates, _run_compare, main dispatch)
- `tests/test_cli.py` (modified -- added 16 promo/compare tests)

## Files Created/Modified

- `src/shopify_forecast_mcp/mcp/tools.py` -- 4 new MCP tool handlers: AnalyzePromotionParams + analyze_promotion, ComparePeriodsParams + compare_periods, GetSeasonalityParams + get_seasonality, DetectAnomaliesParams + detect_anomalies
- `src/shopify_forecast_mcp/cli.py` -- promo and compare subparsers in build_parser(), _run_promo, _resolve_compare_dates, _run_compare, updated main() dispatch
- `tests/test_mcp_tools_analytics.py` -- 15 tests across 4 test classes (TestAnalyzePromotionTool, TestComparePeriodsTool, TestGetSeasonalityTool, TestDetectAnomaliesTool)
- `tests/test_cli.py` -- 16 new tests across 5 test classes (TestBuildParserPromo, TestRunPromo, TestBuildParserCompare, TestRunCompare, TestMainDispatches)

## Decisions Made

- detect_anomalies splits series into context (early data) and lookback (recent data), forecasts the lookback window to establish expected values, then runs anomaly detection against the forecast bands
- Holiday event labeling in detect_anomalies uses optional import from covariates module with graceful fallback (no hard dependency)
- CLI JSON output for promo/compare serializes the full AnalyticsResult structure (metadata, sections with headers/rows, summary, recommendations)
- _resolve_compare_dates uses dateutil.relativedelta for accurate YoY/MoM date math

## Deviations from Plan

None -- plan executed exactly as written.

## Verification Results

- `uv run pytest tests/test_mcp_tools_analytics.py tests/test_cli.py -x -v` -- 48/48 passed
- `uv run pytest tests/ -x` -- 260 passed, 1 skipped (no regressions)
- `@mcp.tool()` count in tools.py: 6 (2 existing + 4 new)
- `sub.add_parser` in cli.py: revenue, demand, auth, promo, compare

## Self-Check: PASSED

- [x] `src/shopify_forecast_mcp/mcp/tools.py` contains all 4 new tool handlers
- [x] `src/shopify_forecast_mcp/cli.py` contains promo and compare subcommands
- [x] `tests/test_mcp_tools_analytics.py` -- 15 tests, all passing
- [x] `tests/test_cli.py` -- 33 tests total (16 new), all passing
- [x] Full test suite -- 260 passed, 0 failed, 1 skipped

---
*Phase: 05-analytics-covariates-remaining-tools*
*Completed: 2026-04-18*
