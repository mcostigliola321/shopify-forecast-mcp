---
phase: 05-analytics-covariates-remaining-tools
plan: 01
subsystem: analytics
tags: [pandas, numpy, analytics, metrics, cohort, anomaly-detection, promotion-analysis]

# Dependency graph
requires:
  - phase: 03-timeseries-forecaster
    provides: orders_to_daily_series, ForecastResult, ForecastEngine
  - phase: 02-shopify-client
    provides: normalize_order, ShopifyClient, GraphQL queries
provides:
  - AnalyticsResult/AnalyticsSection dataclasses with markdown rendering
  - SUPPORTED_METRICS tuple (6 metrics including discount_rate, units_per_order)
  - Five pure analytics functions (analyze_promotion, detect_anomalies, compare_periods, get_seasonality, cohort_retention)
  - aggregate_metrics, compute_discount_rate, compute_units_per_order helpers
  - normalize_order customer_id extraction
  - sample_orders_with_promos test fixture (120+ days, 3 customers, promos)
affects: [05-02, 05-03, 05-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "AnalyticsResult pattern: dataclass with sections list, summary, recommendations, to_markdown()"
    - "Pure function analytics: no I/O, consume order dicts and Series, return AnalyticsResult"
    - "SENSITIVITY_BANDS mapping for anomaly detection quantile thresholds"

key-files:
  created:
    - src/shopify_forecast_mcp/core/metrics.py
    - src/shopify_forecast_mcp/core/analytics.py
    - tests/test_metrics.py
    - tests/test_analytics.py
  modified:
    - src/shopify_forecast_mcp/core/normalize.py
    - src/shopify_forecast_mcp/core/shopify_client.py
    - tests/conftest.py
    - tests/test_normalize.py

key-decisions:
  - "AnalyticsResult uses multi-section architecture allowing flexible output (e.g., promo lift + hangover + cannibalization)"
  - "Units/Order display label used instead of units_per_order for human readability"
  - "customer_id defaults to 'unknown' when customer field is missing (graceful degradation)"

patterns-established:
  - "AnalyticsResult: title + sections[] + summary + recommendations + metadata"
  - "SENSITIVITY_BANDS: low=q10/q90, medium=q20/q80, high=q30/q70"
  - "Anomaly clustering: consecutive days with gap <= 1 merged into single cluster"
  - "Seasonality index: 100 = average baseline, >110 above, <90 below"

requirements-completed: [R6.1, R6.2, R6.3, R6.4, R8.3, R8.4, R8.5, R8.7]

# Metrics
duration: 8min
completed: 2026-04-18
---

# Phase 5 Plan 01: Core Analytics Module Summary

**Five pure analytics functions (promotion analysis, anomaly detection, period comparison, seasonality, cohort retention) with shared metrics infrastructure and 22 unit tests**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-18T15:31:22Z
- **Completed:** 2026-04-18T15:39:13Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- Built AnalyticsResult/AnalyticsSection dataclasses with full markdown rendering (title, table sections, summary, recommendations)
- Implemented all five analytics functions as pure functions: analyze_promotion (lift + hangover + cannibalization), detect_anomalies (quantile bands + clustering + event labeling), compare_periods (6 metrics + biggest movers), get_seasonality (day/month/quarter index), cohort_retention (matrix + LTV)
- Extended metrics system with discount_rate and units_per_order, totaling 6 supported metrics
- Added customer_id to normalize_order and GraphQL queries for cohort analysis

## Task Commits

Each task was committed atomically:

1. **Task 1: Metrics infrastructure, AnalyticsResult, normalize customer_id** - `1aa3d58` (feat)
2. **Task 2: Core analytics functions (RED)** - `86e7a14` (test)
3. **Task 2: Core analytics functions (GREEN)** - `6cdd85c` (feat)

## Files Created/Modified
- `src/shopify_forecast_mcp/core/metrics.py` - SUPPORTED_METRICS, AnalyticsResult/AnalyticsSection, compute_discount_rate, compute_units_per_order, aggregate_metrics
- `src/shopify_forecast_mcp/core/analytics.py` - analyze_promotion, detect_anomalies, compare_periods, get_seasonality, cohort_retention
- `src/shopify_forecast_mcp/core/normalize.py` - Added customer_id extraction from order customer field
- `src/shopify_forecast_mcp/core/shopify_client.py` - Added `customer { id }` to paginated and bulk GraphQL queries
- `tests/test_metrics.py` - 9 tests for metrics infrastructure
- `tests/test_analytics.py` - 13 tests for analytics functions
- `tests/conftest.py` - Added sample_orders_with_promos fixture, updated _make_order with customer_id/discount_codes
- `tests/test_normalize.py` - Updated expected_keys to include customer_id

## Decisions Made
- AnalyticsResult uses multi-section architecture for flexible output composition
- Units/Order display label used for human readability in tables
- customer_id defaults to "unknown" when customer field is missing (graceful degradation)
- Anomaly day clustering uses gap <= 1 day threshold for merging consecutive anomalies

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_normalize_order_from_bulk expected_keys**
- **Found during:** Task 1 (after adding customer_id to normalize_order)
- **Issue:** Existing test checked exact key set, failed when customer_id was added
- **Fix:** Added "customer_id" to the expected_keys set in test_normalize.py
- **Files modified:** tests/test_normalize.py
- **Verification:** Full test suite passes (207 tests)
- **Committed in:** 1aa3d58 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Necessary fix for test compatibility with new customer_id field. No scope creep.

## Issues Encountered
- Test assertion for compare_periods used underscore metric names but display labels use slash notation (Units/Order). Fixed test to match display labels.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All five analytics functions ready to be wrapped as MCP tools (Plan 03)
- AnalyticsResult.to_markdown() provides consistent output format for tool responses
- sample_orders_with_promos fixture available for downstream integration tests
- Metrics infrastructure shared across all analytics functions

## Self-Check: PASSED

All 4 key files verified present. All 3 task commits verified in git log.

---
*Phase: 05-analytics-covariates-remaining-tools*
*Completed: 2026-04-18*
