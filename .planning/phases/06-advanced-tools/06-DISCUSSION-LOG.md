# Phase 6: Advanced Tools - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-18
**Phase:** 06-advanced-tools
**Areas discussed:** Scenario format, Reorder alerts, Multi-store config, Inventory source
**Mode:** Auto (all decisions auto-selected as recommended defaults)

---

## Scenario Comparison Format

| Option | Description | Selected |
|--------|-------------|----------|
| Side-by-side table | One column per scenario, rows for metrics | ✓ |
| Sequential blocks | One section per scenario, stacked vertically | |
| Diff-style | Show only differences between scenarios | |

**User's choice:** Side-by-side table (auto-selected)
**Notes:** Consistent with compare_periods format from Phase 5. Reuses AnalyticsResult sections architecture.

---

## Reorder Alert Thresholds

| Option | Description | Selected |
|--------|-------------|----------|
| Forecast-based | days_to_stockout = inventory / daily_demand_forecast | ✓ |
| Historical-based | days_to_stockout from trailing average sales | |

**User's choice:** Forecast-based (auto-selected)
**Notes:** Leverages the forecaster already built. Safety factor 1.2 default with configurable param.

---

## Multi-Store Config Shape

| Option | Description | Selected |
|--------|-------------|----------|
| Stores list in Settings | List of store configs, default_store selector | ✓ |
| Separate env prefix per store | SHOPIFY_FORECAST_STORE1_*, SHOPIFY_FORECAST_STORE2_* | |
| Config file only | JSON/YAML config file, no env vars | |

**User's choice:** Stores list in Settings (auto-selected)
**Notes:** Extends existing pydantic-settings pattern. Claude Desktop config example needed in docs.

---

## Inventory Data Source

| Option | Description | Selected |
|--------|-------------|----------|
| inventoryLevels GraphQL | New fetch_inventory on ShopifyClient | ✓ |
| REST inventory API | Simpler but less consistent with existing pattern | |

**User's choice:** inventoryLevels GraphQL (auto-selected)
**Notes:** Consistent with existing GraphQL patterns. Graceful degradation when scope not granted.

---

## Claude's Discretion

- Exact inventory GraphQL query field selection and pagination strategy
- Multi-store ShopifyClient lifecycle (pool vs on-demand creation)
- Scenario result caching strategy

## Deferred Ideas

None
