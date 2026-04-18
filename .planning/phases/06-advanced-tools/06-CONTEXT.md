# Phase 6: Advanced Tools - Context

**Gathered:** 2026-04-18
**Status:** Ready for planning

<domain>
## Phase Boundary

What-if scenario planning (`compare_scenarios` MCP tool), inventory-aware reorder alerts (extending `forecast_demand`), and multi-store support (config + cache isolation + store selector on every tool). This is PRD Phase 3 — advanced features that build on the analytics and covariate foundations from Phase 5.

</domain>

<decisions>
## Implementation Decisions

### compare_scenarios (R8.6)
- **D-01:** Side-by-side markdown table with one column per scenario, rows for key metrics (total revenue, peak day, confidence range). Each scenario varies `promo_dates` and `discount_depth`. Reuses XReg pathway from Phase 5 (`build_future_covariates` + `forecast_with_covariates`).
- **D-02:** 2-4 scenarios per call. Each scenario is a named dict: `{"name": "Aggressive", "promo_start": "...", "promo_end": "...", "discount_depth": 0.3}`. The tool runs each scenario through the forecaster and collates results.
- **D-03:** Output includes a recommendation highlighting the best-performing scenario with rationale (e.g., "Scenario B ('Moderate') produces 12% more revenue than baseline with less post-promo hangover than Scenario C").
- **D-04:** `COVARIATES_DISCLAIMER` appended to output since scenarios use XReg (consistent with D-20 from Phase 5).

### Inventory-Aware Reorder
- **D-05:** Extend `forecast_demand` response to include reorder alerts when `read_inventory` scope is available. Not a separate tool — augments existing demand forecast.
- **D-06:** Reorder logic: `days_to_stockout = current_inventory / daily_demand_forecast`. Alert when `days_to_stockout < lead_time_days` (user-provided param, default 14).
- **D-07:** Suggested reorder qty = `lead_time_days * daily_demand_forecast * safety_factor`. Safety factor defaults to 1.2 (20% buffer). Configurable via param.
- **D-08:** New `fetch_inventory` method on ShopifyClient using `inventoryLevels` GraphQL query. Returns `{variant_id, sku, product_id, available, location_id}`.
- **D-09:** Graceful degradation: if `read_inventory` scope not granted, demand forecast works normally without reorder alerts. Log warning once.

### Multi-Store Support
- **D-10:** Config shape: `stores` list in Settings, each entry has `shop`, `access_token`, and optional `label`. A `default_store` field selects which store to use when no `store` param is provided.
- **D-11:** Single MCP session supports all configured stores. Each tool accepts optional `store` param (store domain or label) to override the default.
- **D-12:** Cache isolation per store — forecast cache keyed by `(store_domain, metric, params_hash)` to prevent cross-store cache hits.
- **D-13:** ForecastEngine singleton is store-agnostic (TimesFM model doesn't change per store). Only ShopifyClient instances are per-store.
- **D-14:** Claude Desktop config example in docs: show how to configure multi-store in `claude_desktop_config.json` with env vars per store.

### CLI
- **D-15:** New `shopify-forecast scenarios` CLI verb with `--scenarios` flag accepting JSON or file path. `--json` flag for piped output (consistent with D-22 from Phase 5).
- **D-16:** Multi-store CLI: `--store` flag on all verbs to select store by domain or label.

### Claude's Discretion
- Exact inventory GraphQL query field selection and pagination strategy
- Multi-store ShopifyClient lifecycle (pool vs on-demand creation)
- Scenario result caching strategy

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 5 foundations
- `.planning/phases/05-analytics-covariates-remaining-tools/05-CONTEXT.md` — Covariate decisions (D-18 through D-20) that compare_scenarios builds on
- `src/shopify_forecast_mcp/core/covariates.py` — `build_future_covariates` function reused by scenarios
- `src/shopify_forecast_mcp/core/forecaster.py` — `forecast_with_covariates` method reused by scenarios

### Existing patterns
- `src/shopify_forecast_mcp/mcp/tools.py` — MCP tool handler pattern (Pydantic params + @mcp.tool + async handler)
- `src/shopify_forecast_mcp/cli.py` — CLI verb pattern (argparse subparser + async _run_X)
- `src/shopify_forecast_mcp/config.py` — Settings class structure to extend
- `src/shopify_forecast_mcp/core/shopify_client.py` — GraphQL query patterns for new inventory query

### Spec
- `shopify-forecast-mcp-PRD.md` — R8.6 compare_scenarios spec, multi-store design notes

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `build_future_covariates(horizon, last_date, planned_promos)` — builds scenario-specific covariates from promo params
- `forecast_with_covariates(series, covariates, horizon)` — runs XReg-enabled forecast
- `AnalyticsResult` + `to_markdown()` — shared output format for all analytics tools
- `ForecastResult` + `summary()` + `to_table()` — forecast output format

### Established Patterns
- All MCP tools: Pydantic BaseModel params + `@mcp.tool()` + async handler + `ctx.info()` + try/except
- All CLI verbs: argparse subparser + async `_run_X` + `--json` flag
- Error handling: catch Exception, return markdown error string (never stack traces)
- Config: pydantic-settings with `SHOPIFY_FORECAST_*` env prefix

### Integration Points
- `mcp/tools.py` — add `compare_scenarios` tool handler
- `cli.py` — add `scenarios` verb
- `config.py` — extend Settings with `stores` list and `default_store`
- `core/shopify_client.py` — add `fetch_inventory` method
- `mcp/server.py` — AppContext may need multi-store ShopifyClient support

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches following established patterns from Phases 4-5.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 06-advanced-tools*
*Context gathered: 2026-04-18*
