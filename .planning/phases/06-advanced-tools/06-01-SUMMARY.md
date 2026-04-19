---
phase: 06-advanced-tools
plan: 01
subsystem: forecasting
tags: [scenarios, what-if, covariates, xreg, timesfm, mcp-tool, cli]

# Dependency graph
requires:
  - phase: 05-analytics-covariates
    provides: "covariate engineering (build_aligned_covariates), analytics layer, MCP tools pattern"
provides:
  - "ScenarioResult dataclass for structured scenario output"
  - "run_scenarios async function for XReg-based what-if forecasting"
  - "format_scenario_comparison markdown formatter with recommendation"
  - "compare_scenarios MCP tool (7th tool)"
  - "CLI 'scenarios' verb with --scenarios JSON and --json output"
affects: [07-distribution]

# Tech tracking
tech-stack:
  added: []
  patterns: ["scenario comparison via XReg covariate pipeline", "side-by-side markdown table with recommendation"]

key-files:
  created:
    - src/shopify_forecast_mcp/core/scenarios.py
    - tests/test_scenarios.py
    - tests/test_mcp_tools_scenarios.py
    - tests/test_cli_scenarios.py
  modified:
    - src/shopify_forecast_mcp/mcp/tools.py
    - src/shopify_forecast_mcp/cli.py

key-decisions:
  - "ScenarioResult uses dataclass (not Pydantic) for core module consistency"
  - "Recommendation logic computes lift percentage vs runner-up scenario"

patterns-established:
  - "Scenario dict format: {name, promo_start, promo_end, discount_depth} reused across MCP and CLI"

requirements-completed: [R8.6]

# Metrics
duration: 5min
completed: 2026-04-19
---

# Phase 6 Plan 1: Scenario Comparison Summary

**What-if promotional scenario comparison via XReg pipeline with side-by-side markdown table, recommendation, and covariates disclaimer**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-19T10:39:34Z
- **Completed:** 2026-04-19T10:44:31Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Core scenarios module with ScenarioResult dataclass, run_scenarios (2-4 scenario validation, XReg pipeline), and format_scenario_comparison (markdown table with recommendation and COVARIATES_DISCLAIMER)
- MCP compare_scenarios tool with ScenarioInput/CompareScenariosParams Pydantic models (discount_depth 0-1, scenarios min 2 max 4, horizon 1-365)
- CLI 'scenarios' verb accepting --scenarios JSON string or file path, --json output, --horizon, --context, --country flags
- 25 tests covering core module, MCP tool, Pydantic validation, and CLI (all passing)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create scenarios.py core module** (TDD)
   - `8031043` (test: failing tests for scenario comparison)
   - `657c657` (feat: implement scenario comparison core module)
2. **Task 2: Add MCP tool and CLI verb** - `565fb12` (feat)

## Files Created/Modified
- `src/shopify_forecast_mcp/core/scenarios.py` - ScenarioResult dataclass, run_scenarios, format_scenario_comparison
- `src/shopify_forecast_mcp/mcp/tools.py` - ScenarioInput, CompareScenariosParams, compare_scenarios MCP tool handler
- `src/shopify_forecast_mcp/cli.py` - scenarios subparser, _run_scenarios with JSON parsing and validation
- `tests/test_scenarios.py` - 9 unit tests for core scenarios module
- `tests/test_mcp_tools_scenarios.py` - 9 tests for MCP tool and Pydantic validation
- `tests/test_cli_scenarios.py` - 7 tests for CLI parsing and execution

## Decisions Made
- ScenarioResult uses a plain dataclass rather than Pydantic BaseModel, consistent with the core module pattern (ForecastResult is also a dataclass)
- Recommendation section computes lift percentage of best scenario over runner-up to quantify the advantage
- CLI --scenarios accepts both inline JSON strings and file paths; file path is detected by absence of leading `[`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] MCP tool count was 7 not 6**
- **Found during:** Task 2 verification
- **Issue:** Plan acceptance criteria expected 6 @mcp.tool decorators (5 existing + 1 new), but there were already 6 existing tools (forecast_revenue, forecast_demand, analyze_promotion, compare_periods, get_seasonality, detect_anomalies)
- **Fix:** No code fix needed -- the plan's count assumption was simply off by one. The new tool was correctly added as the 7th.
- **Impact:** None -- cosmetic discrepancy in acceptance criteria only.

---

**Total deviations:** 1 (cosmetic plan count mismatch, no code impact)
**Impact on plan:** No scope creep. All functional requirements met.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Scenario comparison feature complete and tested
- All 7 MCP tools now registered and functional
- CLI has full verb coverage: revenue, demand, promo, compare, scenarios, auth
- Ready for remaining Phase 6 plans or Phase 7 distribution

## Self-Check: PASSED

All 4 created files verified present. All 3 task commits verified in git log.

---
*Phase: 06-advanced-tools*
*Completed: 2026-04-19*
