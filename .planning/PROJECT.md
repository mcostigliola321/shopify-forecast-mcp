# shopify-forecast-mcp

## Current State (post-v0.1.0)

**Shipped 2026-04-20.** `shopify-forecast-mcp 0.1.0` is publicly installable via:
- `uvx --from shopify-forecast-mcp==0.1.0 shopify-forecast --help` (PyPI)
- `docker pull ghcr.io/mcostigliola321/shopify-forecast-mcp:latest` (GHCR, multi-arch amd64+arm64)
- Claude Desktop JSON snippet documented in `docs/SETUP.md`

**What shipped:** 7 MCP tools (forecast_revenue, forecast_demand, analyze_promotion, detect_anomalies, compare_periods, compare_scenarios, get_seasonality), 6 CLI verbs, TimesFM 2.5 foundation model, dual-backend (Shopify CLI toolkit primary + httpx fallback), multi-store config, XReg covariates (feature-flagged), inventory-aware reorder alerts.

**Tech stack in production:** Python 3.11, TimesFM 2.5 via `timecopilot-timesfm` PyPI fork (D-23), PyTorch CPU, `mcp>=1.27`, `httpx`, `pandas`, `pydantic-settings`, `holidays`, hatchling build backend, `uv` package management.

**Codebase:** ~12,900 LOC Python, 354 tests passing (non-slow+non-integration), 140 commits across 7 days.

## What This Is

An open-source MCP (Model Context Protocol) server that connects Google's TimesFM 2.5 time-series foundation model to Shopify stores via the Admin GraphQL API. It gives any MCP-compatible AI client (Claude Desktop, Claude Code, Cursor, custom agents) conversational access to ecommerce sales forecasting, demand planning, promotional analysis, and anomaly detection — powered by a state-of-the-art foundation model instead of legacy methods like Prophet or ARIMA.

## Core Value

A merchant can ask their AI assistant "what does next month look like?" and get a foundation-model-grade forecast with confidence bands, grounded in their real Shopify order history — with zero dashboards, exports, or per-store training. **Validated** in v0.1.0: clone-to-running in 30s via `uvx`.

## Requirements

### Validated (v0.1.0)

- ✓ Two-layer architecture: importable Python core library + thin MCP server wrapper — v0.1.0
- ✓ Shopify GraphQL Admin API client with bulk operations, pagination, rate-limit handling, refund-aware revenue normalization — v0.1.0 (Phase 2)
- ✓ Time-series shaping: aggregate orders to daily/weekly/monthly series by store/product/collection/SKU, gap-filling, outlier capping — v0.1.0 (Phase 3)
- ✓ TimesFM 2.5 wrapper with singleton model loading, quantile head, XReg covariate support, structured `ForecastResult` — v0.1.0 (Phase 3, Phase 5)
- ✓ Covariate engineering: day-of-week, weekend, month, holidays, holiday proximity, discount flags, custom events — v0.1.0 (Phase 5)
- ✓ Analytics layer: promotion analysis, anomaly detection, period comparison (YoY/MoM), cohort retention — v0.1.0 (Phase 5)
- ✓ MCP server (stdio transport) exposing 7 tools: `forecast_revenue`, `forecast_demand`, `analyze_promotion`, `detect_anomalies`, `compare_periods`, `compare_scenarios`, `get_seasonality` — v0.1.0 (Phase 4, 5, 6)
- ✓ Standalone CLI for non-MCP use (`shopify-forecast revenue|demand|promo|compare|scenarios|auth`) — v0.1.0
- ✓ Markdown responses (never raw JSON / stack traces) — v0.1.0
- ✓ Test suite with realistic fixture data — v0.1.0 (354 tests passing)
- ✓ Quick-start documentation (README, SETUP, TOOLS, ARCHITECTURE, CHANGELOG, RELEASE) — v0.1.0 (Phase 7)
- ✓ Distribution: PyPI package + Docker image (GHCR) — v0.1.0 (Phase 7)
- ✓ Multi-store support — v0.1.0 (Phase 6, moved from v0.2)
- ✓ Dual-backend: Shopify CLI toolkit primary with httpx fallback — v0.1.0 (Phase 4.1, emerged during MVP)

### Active (v0.2.0 candidates — TBD during `/gsd-new-milestone`)

No requirements formally locked yet. Potential directions surfaced during v0.1.0 that could feed into v0.2 brainstorming:
- SSE transport (v0.1.0 is stdio-only)
- Shopify Sidekick App Extension distribution channel (originally scoped for later)
- `npx` wrapper parallel to `uvx`
- Performance tuning: GPU path for TimesFM, batched forecasting for multi-SKU queries
- Observability/metrics for merchant-facing deployments

### Out of Scope (confirmed at v0.1.0)

- Generic CSV ingestion — Shopify-native by design.
- Legacy forecasting models (Prophet, ARIMA, moving averages) — TimesFM only, validated as the right call.
- Web dashboard / UI — MCP-native and CLI only; merchants use their AI assistant.
- Per-store model retraining — TimesFM is zero-shot; validated by shipping.
- Buyer-facing or developer-facing tooling — this serves the merchant operations layer.
- Paid SaaS features — MIT-licensed, free forever.

## Context

- **Ecosystem gap (April 2026):** Shopify has four official MCP servers (Dev, Storefront, Customer Account, Checkout). All are buyer-facing or developer-facing. None serve merchant operations. `shopify-forecast-mcp 0.1.0` is the first MCP server in that gap.
- **Competitive landscape:** Existing third-party tools use weak forecasting models (moving averages, Prophet) or are locked inside closed SaaS products with no MCP exposure. v0.1.0 is the first TimesFM + Shopify GraphQL + MCP integration.
- **TimesFM 2.5:** 200M params, 16k context, continuous quantile head, zero-shot. State-of-the-art on GIFT-Eval benchmark. Apache-2.0 licensed by Google Research. ~400MB download. Distributed via the `timecopilot-timesfm` community fork (upstream Google package lacks PyPI release).
- **Shopify gotchas handled:** `totalPriceSet` → `subtotalPriceSet` for revenue (excludes tax/shipping), bulk ops return JSONL with `__parentId` tree, bulk result URLs expire after 1hr, GraphQL is cost-based rate-limited (1000 pts/sec), GIDs stripped on parse, multi-currency via `shopMoney`.
- **Distribution:** PyPI (Trusted Publisher OIDC, no static tokens), GHCR (multi-arch via `${{ github.repository }}`, public packages), GitHub Releases (wheel + sdist attached).
- **Author:** Mark (OmniAlta LLC). Repo: `github.com/mcostigliola321/shopify-forecast-mcp`. License: MIT. Package owner on PyPI + GHCR: `mcostigliola321`.

## Constraints

- **Tech stack:** Python 3.11+ (TimesFM is Python-native, MCP SDK is Python). PyTorch CPU. `mcp>=1.27`, `httpx`, `pandas`, `numpy`, `pydantic`, `pydantic-settings`, `holidays`, `timecopilot-timesfm>=0.2,<0.3`, `huggingface-hub>=0.34,<1.0`. Package management via `uv`.
- **API:** Shopify GraphQL Admin API version `2026-01`. Scopes: `read_orders`, `read_products`, `read_inventory`.
- **Performance targets (v0.1.0 actuals):** uvx cold install → 30s. Docker bundled pull → seconds (weights baked). Full test suite → 2.7s. Build → <30s.
- **Architectural invariants:** Core library importable and testable without MCP. MCP server is a thin wrapper. All tool responses are markdown (never JSON). Singleton TimesFM. ForecastResult is structured Pydantic.
- **Security posture:** No static PyPI tokens (OIDC only). Non-root Docker user (`app`, UID 1000). JSON-array `ENTRYPOINT` so SIGTERM reaches Python. `.dockerignore` filters secrets + build context.
- **License compatibility:** MIT for this project; TimesFM weights Apache-2.0; `timecopilot-timesfm` MIT.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| TimesFM 2.5 over Prophet/ARIMA | Foundation model outperforms legacy methods on retail benchmarks; zero-shot eliminates per-store training | ✓ Good — shipped v0.1.0 with sine-wave validation; merchant workflow unblocked |
| Two-layer architecture (core lib + MCP wrapper) | Enables standalone CLI use and unit testing without MCP runtime | ✓ Good — CLI has 6 verbs; core tested independently |
| Shopify GraphQL bulk operations over REST | Required for stores with >10k orders; cost-based rate limit is more generous | ✓ Good — JSONL `__parentId` pipeline handles real-world stores |
| Singleton model loading | TimesFM is ~800MB in memory — per-request loading would be unusable | ✓ Good — lazy + singleton in production |
| Markdown responses (not JSON) | MCP clients render markdown natively; tables and summaries are merchant-readable | ✓ Good — every tool returns merchant-readable output |
| `subtotalPriceSet` for revenue | Excludes tax and shipping — actual product revenue is what merchants forecast | ✓ Good |
| `financial_status: paid` filter by default | Excludes pending/authorized/refunded; matches merchant intuition | ✓ Good |
| Build order from PRD §"Implementation Notes" | Each layer testable before the next: config → shopify_client → timeseries → forecaster → MCP tools → analytics → covariates | ✓ Good — shipped in 7 days |
| **D-23: `timecopilot-timesfm` PyPI fork instead of git+https Google upstream** | PyPI rejects `Requires-Dist: git+https://`, blocking wheel uploads | ✓ Good — enabled the entire Phase 7 release |
| **Dual-backend (CliBackend primary, DirectBackend fallback)** | Merchants already have Shopify CLI for OAuth; reuse their auth flow, fall back to httpx when CLI absent | ✓ Good — browser OAuth replaces manual tokens |
| **Multi-store in v0.1 (not v0.2)** | Merchants with multiple stores would have had zero path; isolation via per-store cache is cheap | ✓ Good — landed without overrunning the milestone |
| **PyPI upload idempotent pre-check (not `--check-url` alone)** | `--check-url` refuses sdist hash drift on retagged SHAs; a version-exists short-circuit is what "idempotent" means | ✓ Good — documented in docs/RELEASE.md for future releases |
| **Dockerfile must COPY README.md + LICENSE** | Hatchling validates these during `--no-editable` sync even though they're not in `src/` | ✓ Good — bundled into runbook and Wave 0 tests for v0.2 should assert this |

## Evolution

Evolves at phase transitions and milestone boundaries.

**Per milestone:**
1. Move shipped requirements to Validated with version reference
2. Audit Out of Scope — reasons still valid?
3. Update Context with live state (URLs, tech stack, codebase stats)
4. Add decisions to Key Decisions with outcomes

---
*Last updated: 2026-04-20 after v0.1.0 milestone completion.*
