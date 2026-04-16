---
phase: 03-time-series-forecaster
plan: 04
subsystem: forecast-result
tags: [dataclass, fixtures, integration, presentation]
dependency_graph:
  requires: [03-01, 03-02, 03-03]
  provides: [ForecastResult, fixture-csv, fixture-json]
  affects: [phase-04-mcp-tools, phase-04-cli]
tech_stack:
  added: []
  patterns: [dataclass-factory, markdown-table-rendering, natural-language-summary]
key_files:
  created:
    - src/shopify_forecast_mcp/core/forecast_result.py
    - tests/fixtures/sample_daily_revenue.csv
    - tests/fixtures/sample_orders.json
    - tests/test_forecast_result.py
    - tests/test_integration_forecast.py
    - scripts/generate_fixtures.py
  modified: []
key_decisions:
  - "ForecastResult uses from_forecast() classmethod to extract single series from batch arrays"
  - "Channel mapping follows QUANTILE_CHANNELS constant: [mean, q10..q90]"
  - "Currency formatting ($) applied for revenue and aov metrics, plain numbers for orders/units"
  - "Fixture generation via reproducible script with seed=42 for deterministic output"
metrics:
  duration_seconds: 169
  completed: "2026-04-16T15:36:01Z"
  tasks_completed: 2
  tasks_total: 2
  test_count: 15
  files_created: 6
---

# Phase 03 Plan 04: ForecastResult Dataclass + Fixtures Summary

ForecastResult dataclass wrapping TimesFM output with to_table() markdown rendering and summary() natural-language projection, plus 365-day seasonal revenue CSV and 97-order fixture JSON.

## Completed Tasks

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | ForecastResult dataclass + fixture data | 7394508 | forecast_result.py, sample_daily_revenue.csv, sample_orders.json |
| 2 | Unit tests + integration tests | 83b8241 | test_forecast_result.py, test_integration_forecast.py |

## Implementation Details

### ForecastResult Dataclass

- `from_forecast(point, quantile, start_date, freq, metric, **meta)` classmethod extracts single series from batch `(batch, horizon)` and `(batch, horizon, 10)` arrays
- `to_table(period="weekly")` renders markdown table with weekly/monthly buckets, projected total + 90% CI bands
- `summary(prior_period_value=None)` returns natural language: "Revenue is projected to be $X over the next N days (90% CI: $Y-$Z). Trend: +N% vs prior period."
- `confidence_bands` dict maps channel names to 1-D arrays: `{"mean": arr, "q10": arr, ..., "q90": arr}`
- Currency formatting (`$`) for revenue/aov metrics, plain numbers for orders/units

### Fixture Data

- **CSV (365 days):** 2025-04-01 to 2026-03-31, base ~$4,500/day with weekend dip (-20%), holiday spike (Nov +40%, Dec +30%), summer dip (Jun-Aug -15%), 3 promo bumps (+25%), +/-10% noise. Deterministic seed=42.
- **JSON (97 orders):** June 2025, 180 line items across 3 products (Widget A $25, Gadget B $50, Premium C $150), 10 orders with refunds, 3 with discount codes, 22 active days.

### Test Coverage

- **15 unit tests** (test_forecast_result.py): from_forecast extraction, date generation, None quantile handling, metadata, channel-0 regression, markdown table format, weekly/monthly buckets, currency formatting, summary content, trend calculation
- **5 integration tests** (test_integration_forecast.py, @pytest.mark.slow): orders-to-forecast pipeline, CSV fixture-to-forecast, 1yr/30d performance (<10s), channel-0 real model regression, grouped forecast by product_id

## Verification Results

```
Unit tests: 15 passed in 0.32s
Full fast suite: 106 passed, 11 deselected in 1.14s
Integration tests: marked @pytest.mark.slow (require TimesFM model)
```

## Deviations from Plan

None -- plan executed exactly as written.

## Self-Check: PASSED

All 6 created files verified on disk. Both commit hashes (7394508, 83b8241) confirmed in git log.
