# Phase 5: Analytics, Covariates & Remaining Tools - Context

**Gathered:** 2026-04-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Five analytics MCP tools (`analyze_promotion`, `detect_anomalies`, `compare_periods`, `get_seasonality`, `cohort_retention`), XReg covariates behind a feature flag, two new CLI verbs (`promo`, `compare`), and two additional metrics (`discount_rate`, `units_per_order`) folded into the metrics system. All built on the existing order data pipeline — no new Shopify API surfaces.

</domain>

<decisions>
## Implementation Decisions

### Analytics Output Convention
- **D-01:** All analytics tools return markdown table + 2-3 sentence natural-language summary with key takeaway. Consistent with forecast_revenue/forecast_demand from Phase 4.
- **D-02:** Tools include 1-2 actionable recommendations after findings (e.g., "Revenue lifted 23% during promo — consider extending by 2 days next time based on the hangover pattern").
- **D-03:** `compare_periods` shows all six metrics by default (revenue, orders, units, AOV, discount_rate, units_per_order) with the biggest movers bolded/highlighted.

### analyze_promotion
- **D-04:** Separate "Post-Promo Impact" section after the main promo lift table, showing revenue dip in days after promo ends vs baseline.
- **D-05:** Product-level cannibalization estimate — compare product mix during promo vs baseline, flag products that lost share (cannibalized by discounted items). Requires group_by product analysis.

### detect_anomalies
- **D-06:** Sensitivity maps to quantile bands from TimesFM forecast: Low = outside q10/q90, Medium = outside q20/q80, High = outside q30/q70.
- **D-07:** Stores with <90 days history: warn and proceed. Prepend: "Limited history (N days) — anomaly detection may be less reliable."
- **D-08:** Consecutive anomaly days grouped into clusters (single "event" with start/end dates), not listed individually.
- **D-09:** Anomaly clusters labeled with known events when overlap detected — e.g., "Anomaly (likely: Black Friday)" or "Anomaly (during promo: Summer Sale)". Cross-references covariate data when available.
- **D-10:** Direction shown as "Spike (+42% above expected)" or "Drop (-31% below expected)" per cluster.
- **D-11:** Each anomaly row includes: date range, actual value, expected value, confidence band, deviation %.
- **D-12:** Single metric per call (consistent with forecast tools). User calls multiple times for different metrics.
- **D-13:** Default lookback: 90 days. Auto-clamp to available history if less data exists. Short-history warning applies.

### get_seasonality
- **D-14:** Index table format: rows are day-of-week or month, column is index value where 100 = average. E.g., Monday=87, Saturday=134. Simple and scannable.

### cohort_retention
- **D-15:** Full cohort × period retention matrix plus summary line with avg retention per period and LTV.

### Additional Metrics (folded from discussion)
- **D-16:** `discount_rate` (% of orders using discount code) added as a supported metric on `compare_periods` and available across analytics tools.
- **D-17:** `units_per_order` (average basket size) added as a supported metric on `compare_periods` and available across analytics tools.

### Covariate Engineering
- **D-18:** When covariates are enabled (opt-in), ALL built-in covariates activate: day_of_week, is_weekend, month, is_holiday, holiday_proximity, has_discount, discount_depth. No cherry-picking needed.
- **D-19:** holiday_proximity window fixed at -7/+3 days. Not configurable in v1.
- **D-20:** Always append marginal value disclaimer when covariates are enabled: "Note: Covariates provide marginal improvement over TimesFM's foundation model. Results with and without covariates may be similar."

### CLI Verbs
- **D-21:** `shopify-forecast promo --start 2025-11-29 --end 2025-12-02 --name 'Black Friday'`. Explicit dates, name optional. No presets.
- **D-22:** Default output is markdown (same as MCP tools). `--json` flag for piping. Consistent with existing revenue/demand CLI verbs.
- **D-23:** `shopify-forecast compare` supports shortcuts: `--yoy` (this month vs same month last year), `--mom` (this month vs last month), plus custom `--period-a-start/end --period-b-start/end`.

### Claude's Discretion
- Exact markdown table column ordering and formatting
- Error message wording for invalid date ranges, missing data, etc.
- Whether `cohort_retention` cohort period param defaults to monthly or weekly
- Internal module organization of analytics.py (single file vs split per function)
- Custom events API shape for covariates (list of dicts per PRD — exact field names at Claude's discretion)
- Country auto-detection from shop timezone vs explicit param

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` §R5 — Covariate engineering requirements (R5.1–R5.6)
- `.planning/REQUIREMENTS.md` §R6 — Analytics requirements (R6.1–R6.4)
- `.planning/REQUIREMENTS.md` §R8 — MCP tool specs (R8.3–R8.5, R8.7)
- `.planning/REQUIREMENTS.md` §R9 — CLI requirements (R9.2 promo/compare verbs)

### Existing Code
- `src/shopify_forecast_mcp/core/forecaster.py` — ForecastEngine singleton, quantile channels (channel 0 = mean)
- `src/shopify_forecast_mcp/core/forecast_result.py` — ForecastResult dataclass with to_table(), summary()
- `src/shopify_forecast_mcp/core/timeseries.py` — orders_to_daily_series, resample_series, clean_series
- `src/shopify_forecast_mcp/core/normalize.py` — Order normalization with refund accounting
- `src/shopify_forecast_mcp/mcp/tools.py` — Existing tool handlers (forecast_revenue, forecast_demand) — pattern to follow
- `src/shopify_forecast_mcp/mcp/server.py` — AppContext, lifespan, mcp instance
- `src/shopify_forecast_mcp/cli.py` — Existing CLI with revenue, demand, auth subcommands
- `src/shopify_forecast_mcp/config.py` — Settings with feature flags

### Test Infrastructure
- `tests/fixtures/sample_orders.json` — Fixture orders with promo periods, seasonal patterns, refunds
- `tests/fixtures/sample_daily_revenue.csv` — Pre-aggregated daily revenue series
- `tests/conftest.py` — Shared fixtures and mock infrastructure

### Research
- `.planning/research/SUMMARY.md` — Research synthesis including TimesFM XReg marginal value caveat

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ForecastEngine.forecast()` — returns quantile channels needed for anomaly band thresholds
- `ForecastResult` dataclass — `to_table()` and `summary()` pattern to replicate for analytics results
- `orders_to_daily_series()` — core aggregation already handles metrics (revenue, orders, units, aov)
- `clean_series()` — outlier capping available for pre-processing before analytics
- `FREQ_MAP` in tools.py — frequency mapping pattern to reuse

### Established Patterns
- MCP tools use Pydantic BaseModel for input schemas with `@mcp.tool()` decorator
- All tool responses are markdown strings (FastMCP auto-wraps to TextContent)
- Errors caught per-tool, returned as friendly markdown — never raised
- CLI subcommands use argparse with `--json` flag for machine output
- Singleton pattern for model loading (ForecastEngine._instance)

### Integration Points
- `mcp/tools.py` — register 4 new tool handlers alongside existing forecast_revenue/demand
- `mcp/server.py` — AppContext may need analytics module reference in lifespan
- `cli.py` — add `promo` and `compare` subcommands to existing argparse
- `core/` — new `analytics.py` and `covariates.py` modules
- `config.py` — add `covariates_enabled: bool = False` feature flag

</code_context>

<specifics>
## Specific Ideas

- Anomaly clusters should cross-reference holiday/promo data from covariates module when available, creating a dependency between analytics and covariates modules
- The six metrics (revenue, orders, units, AOV, discount_rate, units_per_order) should be defined as an enum or constant list shared across analytics tools and compare_periods
- `--yoy` and `--mom` CLI shortcuts should auto-compute dates based on current date, not require date math from the user

</specifics>

<deferred>
## Deferred Ideas

- **Conversion rate (mobile/desktop)** — Requires session data from Shopify Analytics API and new `read_analytics` scope. Different data pipeline entirely.
- **Product mix shift analysis** — Track which SKUs/collections grow or decline as % of revenue over time. New analytics capability.
- **Repeat vs new customer segmentation** — Use customer email/ID to segment first-time vs returning buyers. New analytics capability.
- **Revenue concentration / Pareto analysis** — Top N products as % of total revenue. New analytics capability.
- **Refund rate trending by product** — Track refund rates per product over time. New analytics capability.

</deferred>

---

*Phase: 05-analytics-covariates-remaining-tools*
*Context gathered: 2026-04-17*
