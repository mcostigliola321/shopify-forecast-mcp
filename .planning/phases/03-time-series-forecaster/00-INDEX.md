# Phase 03: Time-series & Forecaster

**Goal:** Orders in -> `ForecastResult` out, with a singleton TimesFM 2.5 model and univariate inference validated on sine-wave + fixture data.

**Depends on:** Phase 2 (normalized order dict shape)

## Plans

| Plan | Name | Wave | Depends On | Autonomous | Type |
|------|------|------|------------|------------|------|
| 03-01 | Time-series aggregation | 1 | -- | yes | tdd |
| 03-02 | Resample & clean | 2 | 03-01 | yes | tdd |
| 03-03 | TimesFM engine | 2 | -- | yes | execute |
| 03-04 | ForecastResult + fixtures + integration | 3 | 03-01, 03-02, 03-03 | yes | execute |

## Wave Structure

```
Wave 1: [03-01]           (creates timeseries.py)
         |
         v
Wave 2: [03-02, 03-03]   (parallel -- 03-02 adds to timeseries.py, 03-03 loads TimesFM model)
         |         |
         v         v
Wave 3: [03-04]           (wires everything together)
```

## File Ownership

| File | Plan |
|------|------|
| src/shopify_forecast_mcp/core/timeseries.py | 03-01, 03-02 |
| src/shopify_forecast_mcp/core/forecaster.py | 03-03 |
| src/shopify_forecast_mcp/core/forecast_result.py | 03-04 |
| tests/test_timeseries.py | 03-01 |
| tests/test_timeseries_resample.py | 03-02 |
| tests/test_forecaster.py | 03-03 |
| tests/test_forecast_result.py | 03-04 |
| tests/test_integration_forecast.py | 03-04 |
| tests/fixtures/sample_daily_revenue.csv | 03-04 |
| tests/fixtures/sample_orders.json | 03-04 |
| tests/conftest.py | 03-01 |
| pyproject.toml | 03-02 |

## Requirement Coverage

| R-ID | Plan | Full/Partial |
|------|------|-------------|
| R3.1 | 03-01 | Full |
| R3.2 | 03-01 | Full |
| R3.3 | 03-01 | Full |
| R3.4 | 03-02 | Full |
| R3.5 | 03-02 | Full |
| R3.6 | 03-01 | Full |
| R4.1 | 03-03 | Full |
| R4.2 | 03-03 | Full |
| R4.3 | 03-03 | Full |
| R4.4 | 03-03 | Full |
| R4.5 | 03-03, 03-04 | Full |
| R4.6 | 03-04 | Full |
| R4.7 | 03-04 | Full |
| R4.8 | 03-03 | Full |
| R4.9 | 03-03 | Full |
| R4.10 | 03-03 | Full |
| R4.11 | 03-03 | Full |
| R10.2 | 03-04 | Full |
| R10.3 | 03-01, 03-02, 03-03, 03-04 | Full |
| R10.6 | 03-03 | Full |

## Notes

- **Wave 1 parallelism:** Plans 03-01 and 03-02 both modify `timeseries.py`, but 03-01 creates the file and 03-02 adds to it. In practice, both CAN run in parallel because 03-02's `resample_series` and `clean_series` are additive functions with no dependency on `orders_to_daily_series`. However, if the executor merges conflict, 03-02 should be applied after 03-01.
- **Collection grouping gap:** Normalized orders from Phase 2 do NOT include `collection_ids` on line items. Plan 03-01 handles this via an optional `product_collection_map` parameter. The actual map will be built in Phase 4 from `fetch_collections` + product data.
- **Model download:** Plan 03-03 triggers a ~400MB HuggingFace download on first run. All tests using the model are marked `@pytest.mark.slow`.
- **`slow` marker:** Plan 03-02 registers the `slow` marker in `pyproject.toml` so strict-markers mode doesn't reject it in Plans 03-03 and 03-04.
