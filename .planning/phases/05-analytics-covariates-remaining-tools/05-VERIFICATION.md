---
phase: 05-analytics-covariates-remaining-tools
verified: 2026-04-18T18:30:00Z
status: human_needed
score: 14/15 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Covariate-enabled forecast runs on real fixture data"
    expected: "forecast_with_covariates() returns ForecastResult without crashing; result has same shape as standard forecast()"
    why_human: "Unit tests mock the model; the ROADMAP success criterion requires the full TimesFM model loaded with return_backcast=True and aligned covariate arrays — only verifiable with a live model or a non-mocked integration test."
---

# Phase 5: Analytics, Covariates & Remaining Tools Verification Report

**Phase Goal:** Five more MCP tools (analyze_promotion, detect_anomalies, compare_periods, get_seasonality) plus XReg covariates behind a feature flag, plus the remaining CLI verbs.
**Verified:** 2026-04-18T18:30:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | analyze_promotion returns lift metrics, post-promo hangover, and cannibalization estimate | VERIFIED | analytics.py lines 123-235: three-section AnalyticsResult with "Promotion Impact", "Post-Promo Impact", "Product Cannibalization"; tests in test_analytics.py pass |
| 2 | detect_anomalies flags days outside quantile bands with clustering and event labeling | VERIFIED | analytics.py lines 243-420: SENSITIVITY_BANDS dict, cluster merging loop (gap<=2 days), event_lookup labeling; test_analytics.py + test_mcp_tools_analytics.py pass |
| 3 | compare_periods produces YoY/MoM comparison across all six metrics | VERIFIED | analytics.py lines 428-526: iterates SUPPORTED_METRICS (6), boldest mover highlighted; test_analytics.py passes |
| 4 | get_seasonality returns index table with 100=average baseline | VERIFIED | analytics.py lines 540-635: groups by granularity, divides by overall_mean * 100; 7 rows (dow), 12 rows (monthly), 4 rows (quarterly); tests pass |
| 5 | cohort_retention returns full cohort x period retention matrix with LTV | VERIFIED | analytics.py lines 643-810: builds cohort matrix with P1%..P{N}% columns and Avg LTV; tests pass |
| 6 | discount_rate and units_per_order are available as metrics | VERIFIED | metrics.py line 12: SUPPORTED_METRICS = ("revenue", "orders", "units", "aov", "discount_rate", "units_per_order"); tests pass |
| 7 | build_covariates returns dict of aligned numpy arrays spanning full date range | VERIFIED | covariates.py lines 151-228: returns 7 keys each wrapped in outer list for batch dim; test_covariates.py passes |
| 8 | All 7 built-in covariates computed: day_of_week, is_weekend, month, is_holiday, holiday_proximity, has_discount, discount_depth | VERIFIED | covariates.py lines 174-199: all 7 keys present in result dict |
| 9 | Custom events are processed into covariate arrays | VERIFIED | covariates.py lines 202-226: custom_event covariate with proximity decay |
| 10 | build_future_covariates generates covariate arrays for horizon window | VERIFIED | covariates.py lines 231-283: generates future date_range, supports planned_promos |
| 11 | forecast_with_covariates runs without crashing and returns ForecastResult-compatible output | PARTIAL — human needed | Method exists and validates covariate lengths; unit tests mock the model; ROADMAP success criterion requires live model test |
| 12 | Feature flag covariates_enabled defaults to False | VERIFIED | config.py line 39: `covariates_enabled: bool = Field(False, ...)` |
| 13 | Marginal value disclaimer appended when covariates enabled | VERIFIED | forecaster.py lines 25-28: COVARIATES_DISCLAIMER constant defined |
| 14 | Four MCP tools (analyze_promotion, detect_anomalies, compare_periods, get_seasonality) registered and returning markdown | VERIFIED | tools.py: 6 @mcp.tool() decorators (2 existing + 4 new); all 4 analytics tools import from core.analytics; tests pass |
| 15 | CLI promo and compare verbs work with all required flags | VERIFIED | cli.py: promo subparser (--start, --end, --name, --baseline-days, --json), compare subparser (--yoy, --mom, --period-a-start/end, --period-b-start/end, --json); main() dispatches both; tests pass |

**Score:** 14/15 truths verified (1 requires human testing)

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/shopify_forecast_mcp/core/metrics.py` | SUPPORTED_METRICS, AnalyticsResult/AnalyticsSection, aggregation functions | VERIFIED | 147 lines; contains class AnalyticsResult, class AnalyticsSection, SUPPORTED_METRICS tuple, compute_discount_rate, compute_units_per_order, aggregate_metrics |
| `src/shopify_forecast_mcp/core/analytics.py` | Five pure analytics functions | VERIFIED | 811 lines; contains analyze_promotion, detect_anomalies, compare_periods, get_seasonality, cohort_retention, SENSITIVITY_BANDS |
| `src/shopify_forecast_mcp/core/covariates.py` | build_covariates, build_future_covariates, build_aligned_covariates | VERIFIED | 332 lines; all 3 public functions present; holidays_lib.country_holidays used with fallback |
| `src/shopify_forecast_mcp/core/forecaster.py` | forecast_with_covariates, COVARIATES_DISCLAIMER, feature flag wiring | VERIFIED | Contains COVARIATES_DISCLAIMER, _xreg_compiled, _ensure_xreg_compiled, forecast_with_covariates, return_backcast=True; existing forecast() method untouched |
| `src/shopify_forecast_mcp/config.py` | covariates_enabled feature flag | VERIFIED | Line 39: `covariates_enabled: bool = Field(False, ...)` |
| `src/shopify_forecast_mcp/mcp/tools.py` | Four new MCP tool handlers | VERIFIED | analyze_promotion, compare_periods, get_seasonality, detect_anomalies — all with @mcp.tool() decorators; 6 total tools |
| `src/shopify_forecast_mcp/cli.py` | promo and compare CLI subcommands | VERIFIED | Both subparsers in build_parser(); _run_promo, _resolve_compare_dates, _run_compare; dispatched from main() |
| `src/shopify_forecast_mcp/core/normalize.py` | customer_id field | VERIFIED | Lines 165-175: customer_id extracted via strip_gid, defaults to "unknown" |
| `src/shopify_forecast_mcp/core/shopify_client.py` | customer { id } in GraphQL queries | VERIFIED | Lines 103, 168: customer { id } in both paginated and bulk queries |
| `tests/test_metrics.py` | Unit tests for metrics infrastructure | VERIFIED | File exists; 9+ tests; all pass |
| `tests/test_analytics.py` | Unit tests for all analytics functions | VERIFIED | File exists; 13+ tests; all pass |
| `tests/test_covariates.py` | Unit tests for covariates + XReg | VERIFIED | File exists; 22 tests; all pass |
| `tests/test_mcp_tools_analytics.py` | End-to-end tests for analytics MCP tools | VERIFIED | File exists; 15 tests; all pass |
| `tests/test_cli.py` | Tests for promo and compare CLI verbs | VERIFIED | File exists; 33 tests total (16 new); all pass |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `core/analytics.py` | `core/metrics.py` | imports AnalyticsResult, SUPPORTED_METRICS, aggregate functions | VERIFIED | Line 20: `from shopify_forecast_mcp.core.metrics import (AnalyticsResult, AnalyticsSection, aggregate_metrics, compute_discount_rate, compute_units_per_order, SUPPORTED_METRICS)` |
| `core/analytics.py` | `core/timeseries.py` | orders_to_daily_series for time-series aggregation | INTENTIONAL DEVIATION | analytics.py receives pre-built pd.Series as arguments; series-building lives in tools.py/cli.py callers. All analytics functions are pure (no I/O). The wiring exists in tools.py (lines 23, 79, 478, 535) and cli.py (line 27). This is the correct layered architecture. |
| `mcp/tools.py` | `core/analytics.py` | imports analyze_promotion, detect_anomalies, compare_periods, get_seasonality | VERIFIED | Lines 14-19: all four functions imported as `_analyze_promotion`, `_compare_periods`, `_detect_anomalies`, `_get_seasonality` |
| `mcp/tools.py` | `core/covariates.py` | optional import for holiday event labeling | VERIFIED | tools.py lines 577-587: optional import `from shopify_forecast_mcp.core.covariates import _get_country_holidays` with graceful fallback |
| `cli.py` | `core/analytics.py` | imports analytics functions for CLI verbs | VERIFIED | cli.py lines 19-22: `from shopify_forecast_mcp.core.analytics import (analyze_promotion as _analyze_promotion, compare_periods as _compare_periods)` |
| `core/covariates.py` | holidays package | country_holidays() for is_holiday and holiday_proximity | VERIFIED | covariates.py lines 16-19: `import holidays as holidays_lib`; line 142: `holidays_lib.country_holidays(country, years=years)` |
| `core/forecaster.py` | timesfm.forecast_with_covariates | ForecastEngine delegates to model | VERIFIED | forecaster.py line 195: `self._model.forecast_with_covariates(inputs=inputs, dynamic_numerical_covariates=covariates, horizon=horizon)` |

---

### Data-Flow Trace (Level 4)

Analytics functions are pure (consume pd.Series and order dicts, return AnalyticsResult). No async data sources. Data flows from test fixtures to functions to AnalyticsResult.to_markdown() outputs. MCP tool handlers: fetch_orders -> orders_to_daily_series -> core analytics function -> to_markdown(). All wiring verified in tools.py.

---

### Behavioral Spot-Checks

Step 7b: No server start required. The test suite covers analytical behaviors with fixture data. The TimesFM model cannot be invoked without downloading ~400MB weights; skip live model checks.

| Behavior | Method | Result | Status |
|----------|--------|--------|--------|
| 92 phase-5 tests pass | `uv run pytest tests/test_metrics.py tests/test_analytics.py tests/test_covariates.py tests/test_mcp_tools_analytics.py tests/test_cli.py -q` | 92 passed, 1 warning in 1.53s | PASS |
| Full suite (no regressions) | `uv run pytest tests/ -q` | 260 passed, 1 skipped, 1 warning in 6.63s | PASS |
| 6 MCP tools registered | grep @mcp.tool() tools.py | 6 matches | PASS |
| 5 CLI subcommands | grep sub.add_parser cli.py | revenue, demand, auth, promo, compare | PASS |
| covariates_enabled defaults False | grep covariates_enabled config.py | Field(False, ...) | PASS |
| COVARIATES_DISCLAIMER defined | grep COVARIATES_DISCLAIMER forecaster.py | module-level constant | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| R5.1 | 05-02 | build_covariates with date_range, orders, country, custom_events | SATISFIED | covariates.py:151 — build_covariates() signature matches exactly |
| R5.2 | 05-02 | 7 built-in covariates including holiday (60+ countries) | SATISFIED | covariates.py: all 7 covariates; _get_country_holidays() uses holidays package supporting 60+ countries |
| R5.3 | 05-02 | Custom events: list of {date, label, type} dicts | SATISFIED | covariates.py lines 202-226: custom_events param processed into custom_event covariate |
| R5.4 | 05-02 | build_future_covariates for forecast window | SATISFIED | covariates.py:231 — build_future_covariates() with planned_promos |
| R5.5 | 05-02 | forecast_with_covariates() API with dynamic_numerical_covariates | SATISFIED | forecaster.py:150 — method present; delegates to model's forecast_with_covariates |
| R5.6 | 05-02 | Feature flag off by default, opt-in via env var | SATISFIED | config.py:39 — covariates_enabled: bool = Field(False, ...) |
| R6.1 | 05-01 | analyze_promotion with lift, hangover, cannibalization | SATISFIED | analytics.py: three-section output including all required components |
| R6.2 | 05-01 | detect_anomalies with quantile bands, date/actual/expected/bounds/deviation/direction | SATISFIED | analytics.py: SENSITIVITY_BANDS, clustering, table with all 6 columns |
| R6.3 | 05-01 | compare_periods YoY/MoM comparison per metric | SATISFIED | analytics.py: all SUPPORTED_METRICS compared; CLI has --yoy/--mom |
| R6.4 | 05-01 | cohort_retention with cohort matrix, retention rates, avg LTV | SATISFIED | analytics.py: full retention matrix with LTV per cohort and avg row |
| R8.3 | 05-03 | analyze_promotion MCP tool | SATISFIED | tools.py: AnalyzePromotionParams + async analyze_promotion + @mcp.tool() |
| R8.4 | 05-03 | detect_anomalies MCP tool with sensitivity param | SATISFIED | tools.py: DetectAnomaliesParams (sensitivity: Literal["low","medium","high"]) + async detect_anomalies |
| R8.5 | 05-03 | compare_periods MCP tool | SATISFIED | tools.py: ComparePeriodsParams + async compare_periods |
| R8.7 | 05-03 | get_seasonality MCP tool with granularity param | SATISFIED | tools.py: GetSeasonalityParams (granularity: Literal["day_of_week","monthly","quarterly"]) + async get_seasonality |
| R9.2 | 05-03 | CLI subcommands promo and compare | SATISFIED | cli.py: both subparsers in build_parser(); _run_promo, _run_compare, _resolve_compare_dates |

All 15 requirement IDs from plans are accounted for. No orphaned requirements found for Phase 5 in REQUIREMENTS.md.

---

### Anti-Patterns Found

Scanned all key files created/modified in this phase.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | — | — | — | — |

No TODO/FIXME/placeholder comments. No empty implementations. No hardcoded empty data flowing to rendering. Stub detection: all `return {}` / `return []` are guarded by empty-list checks that produce real computed values.

---

### Human Verification Required

#### 1. Covariate-Enabled Forecast Integration

**Test:** Load the TimesFM model normally (let it download or use cached weights). Build a ForecastEngine instance, then call:
```python
from shopify_forecast_mcp.core.covariates import build_aligned_covariates
from shopify_forecast_mcp.core.forecaster import ForecastEngine
import pandas as pd, numpy as np

engine = ForecastEngine()
engine.load()  # loads without XReg
series = np.random.rand(90).astype(np.float32)
context_dates = pd.date_range("2025-01-01", periods=90, freq="D")
covariates = build_aligned_covariates(context_dates, 30, [], "US")
point, quantile = engine.forecast_with_covariates(series, covariates, horizon=30)
assert point.shape == (1, 30)
```

**Expected:** Returns without raising ValueError or RuntimeError. point.shape == (1, 30). This exercises the lazy recompilation path (`_ensure_xreg_compiled`) which adds `return_backcast=True` to ForecastConfig — a non-trivial TimesFM model interaction that cannot be mocked away.

**Why human:** Unit tests mock `self._model.forecast_with_covariates`. The ROADMAP success criterion "Covariate-enabled forecast runs without crashing on the fixture and returns a ForecastResult" specifically requires a live model run. This needs a machine with the ~400MB TimesFM weights available.

---

### Gaps Summary

No actionable gaps found. All code artifacts exist, are substantive, and are wired. The 1 human verification item is a live-model integration smoke test for the XReg pathway — the code structure is correct, the unit tests confirm the logic, but only a live TimesFM instance can verify the end-to-end covariate flow.

The key link deviation (analytics.py not importing timeseries.py) is intentional: the pure analytics functions accept pre-built `pd.Series` as arguments, and `orders_to_daily_series` is called in the MCP tool handlers and CLI, which is the correct separation of concerns.

---

_Verified: 2026-04-18T18:30:00Z_
_Verifier: Claude (gsd-verifier)_
