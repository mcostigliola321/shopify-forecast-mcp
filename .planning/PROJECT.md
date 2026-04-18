# shopify-forecast-mcp

## What This Is

An open-source MCP (Model Context Protocol) server that connects Google's TimesFM 2.5 time-series foundation model to Shopify stores via the Admin GraphQL API. It gives any MCP-compatible AI client (Claude Desktop, Claude Code, Cursor, custom agents) conversational access to ecommerce sales forecasting, demand planning, promotional analysis, and anomaly detection — powered by a state-of-the-art foundation model instead of legacy methods like Prophet or ARIMA.

## Core Value

A merchant can ask their AI assistant "what does next month look like?" and get a foundation-model-grade forecast with confidence bands, grounded in their real Shopify order history — with zero dashboards, exports, or per-store training.

## Requirements

### Validated

- [x] Covariate engineering: day-of-week, weekend, month, holidays, holiday proximity, discount flags, custom events — Validated in Phase 5
- [x] Analytics layer: promotion analysis, anomaly detection, period comparison (YoY/MoM), cohort retention — Validated in Phase 5
- [x] Standalone CLI for non-MCP use (`shopify-forecast revenue|demand|promo|compare`) — Validated in Phase 5 (promo/compare verbs added)

### Active

- [ ] Two-layer architecture: importable Python core library + thin MCP server wrapper
- [ ] Shopify GraphQL Admin API client with bulk operations, pagination, rate-limit handling, and refund-aware revenue normalization
- [ ] Time-series shaping: aggregate orders to daily/weekly/monthly series by store / product / collection / SKU, with gap-filling and outlier capping
- [ ] TimesFM 2.5 wrapper with singleton model loading, quantile head, covariate (XReg) support, and structured `ForecastResult`
- [ ] Covariate engineering: day-of-week, weekend, month, holidays (60+ countries), holiday proximity, discount flags, custom events
- [ ] Analytics layer: promotion analysis, anomaly detection, period comparison (YoY/MoM), cohort retention
- [ ] MCP server (stdio + SSE transports) exposing 7 tools: `forecast_revenue`, `forecast_demand`, `analyze_promotion`, `detect_anomalies`, `compare_periods`, `compare_scenarios`, `get_seasonality`
- [ ] Standalone CLI for non-MCP use (`shopify-forecast revenue|demand|promo|compare`)
- [ ] All MCP responses formatted as human-readable markdown (tables + natural-language summaries), never raw JSON or stack traces
- [ ] Test suite with realistic fixture data (1yr of orders, ~5k orders, seasonality, promos, refunds)
- [ ] Quick-start documentation (README, SETUP.md, TOOLS.md, ARCHITECTURE.md) — clone-to-running in under 5 minutes
- [ ] Distribution: PyPI package, npx wrapper, Docker image, optional Shopify Sidekick App Extension

### Out of Scope

- Generic CSV ingestion — this is Shopify-native, not a generic forecasting tool
- Legacy forecasting models (Prophet, ARIMA, moving averages) — TimesFM only
- Web dashboard / UI — MCP-native and CLI only
- Per-store model retraining — TimesFM is zero-shot
- Buyer-facing or developer-facing tooling — this serves the merchant operations layer
- Multi-store support in MVP — deferred to Phase 3
- Paid SaaS features — MIT-licensed, free forever

## Context

- **Ecosystem gap (April 2026):** Shopify has four official MCP servers (Dev, Storefront, Customer Account, Checkout). All are buyer-facing or developer-facing. None serve merchant operations (forecasting, demand planning, performance analysis).
- **Competitive landscape:** Existing third-party tools either use weak forecasting models (moving averages, Prophet) or are locked inside closed SaaS products with no MCP exposure. Nobody has connected TimesFM + Shopify GraphQL + MCP.
- **TimesFM 2.5:** 200M params, 16k context, continuous quantile head, zero-shot. State-of-the-art on GIFT-Eval benchmark. Apache-2.0 licensed by Google Research. ~400MB download, cached locally.
- **Shopify gotchas to handle:** `totalPriceSet` includes tax/shipping (use `subtotalPriceSet`), bulk ops return JSONL not JSON, bulk result URLs expire after 1hr, GraphQL is cost-based rate-limited (1000 pts/sec), GIDs need stripping, multi-currency requires `shopMoney`.
- **Author:** Mark (OmniAlta LLC). Repo: `github.com/omnialta/shopify-forecast-mcp`. License: MIT.
- **Source spec:** `shopify-forecast-mcp-PRD.md` in project root — comprehensive PRD with build order, file structure, tool schemas, gotchas, and roadmap.

## Constraints

- **Tech stack:** Python 3.11+ (TimesFM is Python-native, MCP SDK is Python). PyTorch backend for TimesFM. `mcp` Python package, `httpx` for async Shopify calls, `pandas`/`numpy` for data shaping, `pydantic-settings` for config, `holidays` for calendar covariates, `pytest`/`pytest-asyncio` for tests. Package management via `uv` (recommended) or `pip`.
- **API:** Shopify GraphQL Admin API version `2026-01`. Required scopes: `read_orders`, `read_products`, `read_inventory`, `read_reports` (optional).
- **Performance targets:** Model load <30s first run / <5s cached; store-level forecast (1yr context, 30d horizon) <10s; SKU forecast (top 10) <30s; bulk fetch (10k orders) <60s; ~800MB RAM with model loaded.
- **Architectural rule:** Core library must be importable and testable without MCP. MCP server is a thin wrapper.
- **Response format:** All MCP tool responses are markdown strings — never raw JSON. Errors return human-readable messages, never stack traces.
- **Model loading:** Singleton pattern — TimesFM loads once per server lifecycle, not per request.
- **License compatibility:** MIT for this project; TimesFM model is Apache-2.0 (compatible).

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| TimesFM 2.5 over Prophet/ARIMA | Foundation model outperforms legacy methods on retail benchmarks; zero-shot eliminates per-store training | — Pending |
| Two-layer architecture (core lib + MCP wrapper) | Enables standalone CLI use and unit testing without MCP runtime | — Pending |
| Shopify GraphQL bulk operations over REST | Required for stores with >10k orders; cost-based rate limit is more generous | — Pending |
| Singleton model loading | TimesFM is ~800MB in memory — per-request loading would be unusable | — Pending |
| Markdown responses (not JSON) | MCP clients render markdown natively; tables and summaries are merchant-readable | — Pending |
| `subtotalPriceSet` for revenue (not `totalPriceSet`) | Excludes tax and shipping — actual product revenue is what merchants forecast | — Pending |
| `financial_status: paid` filter by default | Excludes pending/authorized/refunded; matches merchant intuition for "real" orders | — Pending |
| Build order from PRD §"Implementation Notes" | Each layer testable before the next: config → shopify_client → timeseries → forecaster → MCP tools → analytics → covariates | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-18 after Phase 5 completion (analytics, covariates, remaining tools)*
