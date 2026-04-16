---
phase: 03-time-series-forecaster
plan: 02
subsystem: timeseries
tags: [pandas, resample, outlier-detection, iqr, zscore, preprocessing]

# Dependency graph
requires:
  - phase: 03-time-series-forecaster/01
    provides: orders_to_daily_series producing pd.Series with DatetimeIndex
provides:
  - resample_series function for D/W/M frequency conversion
  - clean_series function for outlier capping and gap interpolation
affects: [03-time-series-forecaster/03, 03-time-series-forecaster/04, 04-mcp-server]

# Tech tracking
tech-stack:
  added: []
  patterns: [pandas resample with ME offset for monthly, clip-based outlier capping for TimesFM continuity]

key-files:
  created: [tests/test_timeseries_resample.py]
  modified: [src/shopify_forecast_mcp/core/timeseries.py, pyproject.toml]

key-decisions:
  - "Map user-facing 'M' freq to pandas 'ME' internally for pandas 2.2+ compat"
  - "Use clip() not drop() for outlier handling -- TimesFM requires continuous series"

patterns-established:
  - "Preprocessing pipeline order: interpolate gaps -> cap outliers -> resample"
  - "Metric-aware aggregation: sum for additive metrics, mean for derived (aov)"

requirements-completed: [R3.4, R3.5]

# Metrics
duration: 4min
completed: 2026-04-16
---

# Phase 3 Plan 02: Resample & Clean Summary

**resample_series for D/W/M frequency conversion with metric-aware aggregation, and clean_series with IQR/zscore outlier capping preserving TimesFM series continuity**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-16T15:28:45Z
- **Completed:** 2026-04-16T15:33:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- resample_series converts daily series to weekly or monthly with correct aggregator (sum for revenue/orders/units, mean for aov)
- clean_series caps outliers via IQR (1.5x) or zscore (3-sigma) bounds using clip -- never drops data points
- Linear interpolation fills NaN gaps with edge-NaN fallback to 0.0
- 10 dedicated tests all passing, 76 total suite tests green

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing tests for resample_series and clean_series** - `42591ad` (test)
2. **Task 2: Implement resample_series and clean_series** - `7b263dd` (feat)

## Files Created/Modified
- `tests/test_timeseries_resample.py` - 10 tests covering resample (D/W/M, sum/mean) and clean (IQR, zscore, length preservation, interpolation, passthrough)
- `src/shopify_forecast_mcp/core/timeseries.py` - Added resample_series and clean_series functions
- `pyproject.toml` - Registered `slow` pytest marker for future TimesFM tests

## Decisions Made
- Mapped user-facing `"M"` frequency to pandas `"ME"` offset internally since pandas 2.2+ deprecated the bare `"M"` offset
- Used `series.clip(lower, upper)` for outlier capping to guarantee series length preservation (TimesFM continuity requirement)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pandas 2.2+ "M" offset deprecation**
- **Found during:** Task 2 (implementation)
- **Issue:** `series.resample("M")` raises ValueError in pandas 2.2+ -- "M" is no longer supported, must use "ME"
- **Fix:** Added internal mapping `pandas_freq = "ME" if freq == "M" else freq` while keeping the public API accepting "M"
- **Files modified:** src/shopify_forecast_mcp/core/timeseries.py
- **Verification:** test_daily_to_monthly passes with correct January (3100), February (2900), March (3000) sums
- **Committed in:** 7b263dd (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary for pandas 2.2+ compatibility. No scope creep.

## Issues Encountered
None beyond the pandas offset deprecation handled above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- resample_series and clean_series ready for Plan 03 (TimesFM forecaster) to consume
- Preprocessing pipeline: orders_to_daily_series -> clean_series -> resample_series -> TimesFM
- `slow` marker registered for TimesFM model download/inference tests

---
*Phase: 03-time-series-forecaster*
*Completed: 2026-04-16*
