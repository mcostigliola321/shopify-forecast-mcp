---
phase: 05-analytics-covariates-remaining-tools
plan: 02
subsystem: core/covariates + core/forecaster + config
tags: [covariates, xreg, feature-flag, holidays, timesfm]
dependency_graph:
  requires: []
  provides: [build_covariates, build_future_covariates, build_aligned_covariates, forecast_with_covariates, covariates_enabled]
  affects: [core/forecaster.py, config.py]
tech_stack:
  added: [holidays]
  patterns: [lazy-recompilation, feature-flag, batch-dimension-wrapping]
key_files:
  created:
    - src/shopify_forecast_mcp/core/covariates.py
  modified:
    - src/shopify_forecast_mcp/core/forecaster.py
    - src/shopify_forecast_mcp/config.py
    - tests/test_covariates.py
decisions:
  - "D-18: All covariates activate together when enabled"
  - "D-19: Holiday proximity window fixed at -7/+3 days"
  - "D-20: Marginal value disclaimer constant defined"
  - "Country code fallback to US on unknown country (T-05-05)"
  - "Covariate length validation before TimesFM call (T-05-07)"
metrics:
  duration: ~8min
  completed: "2026-04-18"
  tasks: 2/2
  tests: 22
---

# Phase 05 Plan 02: Covariate Engineering & XReg Integration Summary

Covariate engineering module producing 7 aligned covariate arrays (day_of_week, is_weekend, month, is_holiday, holiday_proximity, has_discount, discount_depth) with custom event support, wired into ForecastEngine via forecast_with_covariates() with lazy XReg recompilation behind a covariates_enabled feature flag defaulting to off.

## What Was Built

### Task 1: Covariate Engineering Module (TDD)

Created `src/shopify_forecast_mcp/core/covariates.py` with:

- **`build_covariates()`** -- Computes 7 built-in covariates from order data and holiday calendars. Returns `dict[str, list[list[float]]]` with batch dimension wrapping for TimesFM compatibility.
- **`build_future_covariates()`** -- Generates deterministic covariates for a future horizon window. Supports planned promotions for has_discount and discount_depth.
- **`build_aligned_covariates()`** -- Convenience function producing a single covariate dict spanning context+horizon dates, the exact shape required by `forecast_with_covariates()`.
- **`_compute_holiday_proximity()`** -- Normalized proximity to nearest holiday within -7/+3 day window (D-19).
- **`_compute_discount_covariates()`** -- has_discount and discount_depth from order discount data.
- **`_get_country_holidays()`** -- Country code validation with fallback to US on unknown codes (T-05-05).
- Custom events support with proximity decay around event dates.

14 unit tests covering all 11 specified behaviors.

### Task 2: XReg Integration + Feature Flag (TDD)

Extended `src/shopify_forecast_mcp/core/forecaster.py` with:

- **`COVARIATES_DISCLAIMER`** -- Module-level constant noting marginal improvement of covariates (D-20).
- **`_xreg_compiled`** -- Instance flag tracking lazy recompilation state.
- **`_ensure_xreg_compiled()`** -- Lazily recompiles ForecastConfig with `return_backcast=True`, required for XReg support.
- **`forecast_with_covariates()`** -- New method accepting series + covariates dict. Validates covariate array lengths (T-05-07), delegates to model's `forecast_with_covariates()`.

Extended `src/shopify_forecast_mcp/config.py` with:

- **`covariates_enabled: bool = False`** -- Feature flag, opt-in via `SHOPIFY_FORECAST_COVARIATES_ENABLED=true`.

8 additional unit tests (22 total) covering feature flag, method existence, return types, lazy recompilation, model delegation, and disclaimer content.

**Existing `forecast()` method is completely untouched.**

## Deviations from Plan

None -- plan executed exactly as written.

## Verification Results

- `uv run pytest tests/test_covariates.py -x -v` -- 22/22 passed
- `uv run pytest tests/ -x` -- 229 passed, 1 skipped (no regressions)
- All acceptance criteria verified via grep

## Commits

Git commits could not be created due to permission restrictions in the execution environment. Files are ready to be committed:

**Task 1 commit (covariates module):**
- `src/shopify_forecast_mcp/core/covariates.py` (new)
- `tests/test_covariates.py` (new)

**Task 2 commit (XReg integration + feature flag):**
- `src/shopify_forecast_mcp/core/forecaster.py` (modified)
- `src/shopify_forecast_mcp/config.py` (modified)
- `tests/test_covariates.py` (modified)

## Self-Check: PASSED

- [x] `src/shopify_forecast_mcp/core/covariates.py` exists and contains all 3 public functions
- [x] `src/shopify_forecast_mcp/core/forecaster.py` contains `forecast_with_covariates`, `_ensure_xreg_compiled`, `return_backcast=True`, `COVARIATES_DISCLAIMER`
- [x] `src/shopify_forecast_mcp/config.py` contains `covariates_enabled: bool`
- [x] `tests/test_covariates.py` -- 22 tests, all passing
- [x] Full test suite -- 229 passed, 0 failed, 1 skipped
