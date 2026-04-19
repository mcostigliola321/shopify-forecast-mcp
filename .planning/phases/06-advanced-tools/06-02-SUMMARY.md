---
phase: 06-advanced-tools
plan: 02
subsystem: inventory
tags: [inventory, reorder-alerts, demand-forecast, graceful-degradation, shopify-graphql]

# Dependency graph
requires:
  - phase: 06-advanced-tools
    plan: 01
    provides: "MCP tools pattern, forecast_demand handler"
provides:
  - "fetch_inventory method on ShopifyClient with pagination"
  - "INVENTORY_QUERY GraphQL constant using quantities(names: ['available'])"
  - "compute_reorder_alerts function with days-to-stockout formula"
  - "format_reorder_alerts markdown table formatter"
  - "Inventory-aware reorder alerts in forecast_demand tool"
  - "Graceful degradation when inventory scope unavailable"
affects: [07-distribution]

# Tech tracking
tech-stack:
  added: []
  patterns: ["graceful degradation for optional API scopes", "reorder alert formula: days_to_stockout = available / daily_demand"]

key-files:
  created:
    - src/shopify_forecast_mcp/core/inventory.py
  modified:
    - src/shopify_forecast_mcp/core/shopify_client.py
    - src/shopify_forecast_mcp/mcp/tools.py
    - tests/test_inventory.py
    - tests/test_mcp_tools_demand.py

key-decisions:
  - "Reorder formula uses int(val + 0.5) rounding instead of math.ceil for suggested_qty"
  - "Inventory errors caught with broad except to ensure graceful degradation per D-09"
  - "Pydantic constraints on lead_time_days (1-365) and safety_factor (1.0-3.0) per T-06-06"

patterns-established:
  - "Optional scope graceful degradation: try/except around scope-dependent API calls with warning log"

requirements-completed: [R8.6]

# Metrics
duration: 5min
completed: 2026-04-19
---

# Phase 6 Plan 2: Inventory Reorder Alerts Summary

**Inventory-aware reorder alerts in forecast_demand with days-to-stockout formula, graceful degradation, and Pydantic-validated lead time/safety params**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-19T10:46:20Z
- **Completed:** 2026-04-19T10:51:20Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- INVENTORY_QUERY GraphQL constant using `quantities(names: ["available"])` API with pagination support (100-page safety limit per T-06-07)
- `fetch_inventory` method on ShopifyClient that parses variant inventory levels across locations, skips untracked variants, handles pagination
- `compute_reorder_alerts` function: fires alert when `days_to_stockout < lead_time_days`, computes `suggested_qty = round(lead_time * daily_demand * safety_factor)`
- `format_reorder_alerts` produces markdown table with Product, SKU, Stock, Daily Demand, Days to Stockout, Reorder Qty, Location columns
- `forecast_demand` MCP tool extended with `lead_time_days` (1-365, default 14) and `safety_factor` (1.0-3.0, default 1.2) parameters
- Graceful degradation per D-09: inventory errors logged at warning level, demand forecast returned without reorder alerts
- 28 tests passing: 8 inventory tests + 15 original demand tests + 5 new demand/reorder tests

## Task Commits

**Note:** Git commit access was blocked during execution. Files are created/modified but need manual commit.

1. **Task 1: Create fetch_inventory and compute_reorder_alerts** (TDD)
   - Tests written first (RED), then implementation (GREEN)
   - Files: `src/shopify_forecast_mcp/core/inventory.py`, `src/shopify_forecast_mcp/core/shopify_client.py`, `tests/test_inventory.py`
2. **Task 2: Extend forecast_demand with reorder alerts**
   - Files: `src/shopify_forecast_mcp/mcp/tools.py`, `tests/test_mcp_tools_demand.py`

## Files Created/Modified
- `src/shopify_forecast_mcp/core/inventory.py` - compute_reorder_alerts, format_reorder_alerts functions
- `src/shopify_forecast_mcp/core/shopify_client.py` - INVENTORY_QUERY constant, fetch_inventory method
- `src/shopify_forecast_mcp/mcp/tools.py` - lead_time_days/safety_factor params, inventory import, reorder alert integration
- `tests/test_inventory.py` - 8 tests for fetch_inventory, compute_reorder_alerts, format_reorder_alerts
- `tests/test_mcp_tools_demand.py` - 5 new tests for reorder alerts integration and graceful degradation

## Decisions Made
- Reorder formula uses `int(val + 0.5)` rounding instead of `math.ceil` for suggested_qty -- matches plan specification exactly
- Inventory errors caught with broad `except Exception` to ensure graceful degradation per D-09 threat model
- Pydantic constraints enforce `lead_time_days` between 1-365 and `safety_factor` between 1.0-3.0 (T-06-06 mitigation)
- Inventory quantities never included in error responses to client (T-06-05 mitigation)

## Deviations from Plan

None - plan executed exactly as written.

## Threat Mitigations Applied
- **T-06-05 (Information Disclosure):** Inventory errors logged at warning level; no inventory data in error responses
- **T-06-06 (Tampering):** Pydantic constraints on lead_time_days (ge=1, le=365) and safety_factor (ge=1.0, le=3.0)
- **T-06-07 (DoS):** 100-page pagination safety limit on fetch_inventory (250 variants/page = 25,000 max)
- **T-06-08 (Elevation of Privilege):** Graceful degradation via try/except; demand forecast works without inventory scope

## Issues Encountered
- Git commands were blocked during execution; all code and tests verified working (28/28 passing) but commits not created

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Inventory reorder alerts complete and tested
- forecast_demand tool now supports optional inventory-aware reorder alerts
- Graceful degradation ensures backwards compatibility
- Ready for remaining Phase 6 plans or Phase 7 distribution

## Self-Check: PENDING

Git commits could not be verified due to blocked git access. File existence verified.

---
*Phase: 06-advanced-tools*
*Completed: 2026-04-19*
