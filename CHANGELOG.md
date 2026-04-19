# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-04-19

First public alpha release. MVP covers the full 7-tool MCP surface plus a standalone CLI, dual-backend Shopify access, and both lazy + bundled Docker image variants.

### Added

- **Seven MCP tools** exposed via FastMCP over stdio:
  - `forecast_revenue` — store-level revenue forecast with TimesFM 2.5 quantile bands
  - `forecast_demand` — product / collection / SKU demand with inventory-aware reorder alerts
  - `analyze_promotion` — revenue lift, order lift, AOV change, discount depth, and post-promo hangover analysis
  - `detect_anomalies` — flag days falling outside forecast quantile bands with configurable sensitivity
  - `compare_periods` — year-over-year and month-over-month comparison across metrics
  - `compare_scenarios` — what-if forecasting with 2-4 promo / discount scenarios in one response
  - `get_seasonality` — surface learned day-of-week, monthly, and quarterly seasonal patterns
- **Standalone `shopify-forecast` CLI** with four verbs (`revenue`, `demand`, `promo`, `compare`) plus `auth` for browser OAuth
- **Dual-backend Shopify client** (Phase 4.1): `DirectBackend` (httpx + access token) as the default; `CliBackend` (`shopify store execute` — no token required) when the Shopify CLI is on PATH
- **Bulk operations lifecycle** for stores with >10k orders, with JSONL reconstruction and cost-based rate limiting
- **Refund-aware revenue normalization**: `subtotalPriceSet.shopMoney.amount` (not `totalPriceSet`), line-item-level refund accounting
- **Timezone-correct bucketing**: orders bucketed by shop's `ianaTimezone`, not UTC (fixes midnight misclassification)
- **Multi-store support** (Phase 6): configure N additional stores via nested env vars (`SHOPIFY_FORECAST_STORES__0__SHOP` etc.); every tool accepts an optional `store` parameter
- **Covariate engineering** (Phase 5, feature-flagged): day-of-week, weekend, month, holidays (60+ countries via `holidays` package), holiday proximity windows, discount flags, custom events — off by default, opt in via `SHOPIFY_FORECAST_COVARIATES_ENABLED=true` or tool param
- **TimesFM 2.5 singleton loader** with compile-time config (`max_context=1024`, `max_horizon=256`, continuous quantile head, normalized inputs, flip invariance, positive inference, fix quantile crossing)
- **Local order cache** keyed by date range with 1-hour default TTL (`SHOPIFY_FORECAST_FORECAST_CACHE_TTL`)
- **`uvx shopify-forecast-mcp` install path** — zero manual Python setup
- **Docker images** on GHCR: `ghcr.io/omnialta/shopify-forecast-mcp:latest` (lazy model download) and `:bundled` (TimesFM baked in at `/opt/hf-cache`), multi-arch for `linux/amd64` + `linux/arm64`
- **Trusted Publisher OIDC** publish flow to PyPI — no static tokens in the repo
- **Full documentation suite**: `README.md`, `docs/SETUP.md`, `docs/TOOLS.md`, `docs/ARCHITECTURE.md` with three Mermaid diagrams

### Changed

- TimesFM dependency migrated from a `git+https://github.com/google-research/timesfm.git@<sha>` direct URL to the PyPI-resolvable community fork `timecopilot-timesfm>=0.2,<0.3` (same `TimesFM_2p5_200M_torch` API). Required for PyPI publish — the upstream package is not yet on PyPI with 2.5 support.

### Known Limitations

- Alpha quality — API surface may change before v0.2.
- Apple Silicon `mps` device not supported; Apple users run on CPU (TimesFM 2.5 source doesn't have an mps branch).
- Browser-based OAuth (`shopify store auth`) does not work inside Docker containers — use `SHOPIFY_FORECAST_ACCESS_TOKEN` env var instead.
- First-run TimesFM download is ~400MB; plan for 30-60 seconds of initial latency on uncached installs.
- `uvx` on a Python 3.12-only machine may need `uvx --python 3.11 shopify-forecast-mcp` (pyproject is pinned to `>=3.11,<3.12`).

[Unreleased]: https://github.com/omnialta/shopify-forecast-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/omnialta/shopify-forecast-mcp/releases/tag/v0.1.0
