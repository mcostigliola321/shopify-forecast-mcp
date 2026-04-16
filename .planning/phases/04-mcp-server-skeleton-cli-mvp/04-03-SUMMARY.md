---
phase: 04-mcp-server-skeleton-cli-mvp
plan: 03
subsystem: mcp
tags: [fastmcp, pydantic, demand-forecast, grouping, mcp-tool]
dependency_graph:
  requires: [04-01, 04-02]
  provides: [forecast_demand tool]
  affects: [mcp/tools.py]
tech_stack:
  added: []
  patterns: [per-group forecasting, top-N ranking by volume, markdown table output]
key_files:
  created:
    - tests/test_mcp_tools_demand.py
  modified:
    - src/shopify_forecast_mcp/mcp/tools.py
decisions:
  - "Collection grouping deferred to Phase 5 -- requires product_collection_map wiring"
  - "Groups with < 7 data points show 'Insufficient data' instead of bad forecast"
metrics:
  duration: ~3 min
  completed: 2026-04-16
  tasks: 2/2
  tests: 15 new (138 total suite)
  files_changed: 2
---

# Phase 4 Plan 3: forecast_demand Tool Summary

Per-product/collection/SKU demand forecasting tool with top-N ranking by historical volume, returning ranked markdown tables with confidence bands.

## Task Results

| Task | Name | Commit | Key Changes |
|------|------|--------|-------------|
| 1 | Add forecast_demand tool | df2607f | ForecastDemandParams model, forecast_demand handler in tools.py |
| 2 | Write demand tests | c827997 | 15 tests: params validation, all-groups, specific group, missing group, error paths |

## Implementation Details

**ForecastDemandParams** fields: `group_by` (product/collection/sku), `group_value` (specific ID or "all"), `metric` (units/revenue/orders), `horizon_days` (1-365, default 30), `top_n` (1-50, default 10).

**Handler flow:**
1. Fetch 365 days of orders via ShopifyClient
2. Map user-facing group_by names to timeseries.py internal fields (product -> product_id, sku -> sku)
3. Call `orders_to_daily_series()` with group_by parameter
4. If "all": rank groups by total historical volume, take top N
5. If specific: filter to that single group (or return "not found")
6. Forecast each group independently via `app.forecaster.forecast()`
7. Build ranked markdown table with Historical Total, Projected, Low (10%), High (90%)

**Edge cases handled:**
- Empty orders -> "No orders found" message
- Missing group_value -> "not found" with available groups listed
- Groups with < 7 data points -> "Insufficient data" row
- Collection grouping without map -> ValueError caught with suggestion to use product/sku
- All exceptions -> friendly markdown error with type and message

## Deviations from Plan

None - plan executed exactly as written.

## Verification

- `uv run python -c "from shopify_forecast_mcp.mcp.tools import forecast_demand, forecast_revenue"` -- PASS
- `uv run pytest tests/test_mcp_tools_demand.py tests/test_mcp_tools_revenue.py -x -v` -- 26/26 PASS
- `uv run pytest -x -q -m "not slow"` -- 138 passed, 11 deselected

## Self-Check: PASSED

- [x] src/shopify_forecast_mcp/mcp/tools.py modified with forecast_demand
- [x] tests/test_mcp_tools_demand.py created with 15 tests
- [x] Commit df2607f exists
- [x] Commit c827997 exists
- [x] All tests pass
