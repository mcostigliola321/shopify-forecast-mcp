---
phase: 03-time-series-forecaster
plan: 01
subsystem: core/timeseries
tags: [timeseries, aggregation, pandas, tdd]
dependency_graph:
  requires: [normalize_order from Phase 2]
  provides: [orders_to_daily_series, Metric, GroupBy]
  affects: [03-03 forecaster, 04-01 MCP tools]
tech_stack:
  added: [numpy]
  patterns: [defaultdict aggregation, pd.date_range zero-fill, safe division with np.where]
key_files:
  created:
    - src/shopify_forecast_mcp/core/timeseries.py
    - tests/test_timeseries.py
  modified:
    - tests/conftest.py
decisions:
  - "Used defaultdict for O(n) single-pass aggregation instead of DataFrame groupby"
  - "Zero-fill with reindex(fill_value=0.0) not fillna to avoid any NaN intermediate state"
  - "AOV safe division via np.where(orders > 0, revenue / orders, 0.0)"
  - "Collection fan-out: each line item contributes to all collections its product belongs to"
metrics:
  duration_seconds: 160
  completed: "2026-04-16T15:27:34Z"
  tasks_completed: 2
  tasks_total: 2
  test_count: 15
---

# Phase 3 Plan 1: Daily Time-Series Aggregation Summary

Orders-to-daily-series bridge using defaultdict aggregation with zero-filled pd.Series output for all 4 metrics and 4 grouping dimensions.

## What Was Built

`orders_to_daily_series(orders, metric, group_by, product_collection_map)` in `core/timeseries.py`:

- **Metrics:** `revenue` (sum net_revenue), `orders` (count distinct), `units` (sum net_quantity), `aov` (revenue/orders with safe division)
- **Groupings:** `None` (store-level, key="store"), `product_id`, `sku`, `collection_id` (with fan-out via product_collection_map)
- **Output:** `dict[str, pd.Series]` with `DatetimeIndex`, zero-filled gaps (no NaN)
- **Types exported:** `Metric`, `GroupBy` (Literal types)

## TDD Execution

| Phase | Tests | Commit |
|-------|-------|--------|
| RED | 15 tests, all failing (NotImplementedError) | cc0a147 |
| GREEN | 15 tests, all passing | e66f8d3 |

## Test Coverage

15 tests across 10 test classes:
- `TestRevenueMetric` - revenue sum per day
- `TestOrdersMetric` - order count per day
- `TestUnitsMetric` - unit sum per day
- `TestAovMetric` - AOV with safe division on gap days
- `TestZeroFill` - gap days are 0.0, no NaN, correct length
- `TestGroupByNone` - single "store" key
- `TestGroupByProductId` - keys and values per product
- `TestGroupBySku` - keys and values per SKU
- `TestGroupByCollectionId` - fan-out and ValueError guard
- `TestEmptyOrders` - empty input edge cases
- `TestRefundAdjusted` - net values used, not gross

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

None -- all functionality is fully wired.
