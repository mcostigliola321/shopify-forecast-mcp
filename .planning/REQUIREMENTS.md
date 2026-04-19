# Requirements — shopify-forecast-mcp

Source: `shopify-forecast-mcp-PRD.md` + research synthesis at `.planning/research/SUMMARY.md`.

## R1. Project scaffold & packaging

- **R1.1** `uv init --package` layout under `src/shopify_forecast_mcp/` (single distribution, not split `src/core` + `src/mcp`)
- **R1.2** `pyproject.toml` with hatchling backend, PEP 639 SPDX license (`MIT`), Python `>=3.11,<3.12`, two `[project.scripts]` entries (`shopify-forecast`, `shopify-forecast-mcp`)
- **R1.3** PyTorch CPU wheel via `[tool.uv.sources]` index override; GPU as opt-in extra
- **R1.4** TimesFM as git dependency pinned to commit SHA (NOT PyPI — 2.5 not published)
- **R1.5** `LICENSE` (MIT), `.env.example`, `.gitignore`, `README.md` placeholder, `.python-version`
- **R1.6** `pydantic-settings` config in `src/shopify_forecast_mcp/config.py` with `SHOPIFY_FORECAST_*` env prefix and `SecretStr` for token

## R2. Shopify Admin API client

- **R2.1** Async client built on `httpx.AsyncClient` (no third-party Shopify lib) targeting Admin GraphQL `2026-04`
- **R2.2** Bulk operations lifecycle: `bulkOperationRunQuery` → poll via `bulkOperation(id: $id)` → download JSONL → reconstruct nested children using `__parentId`
- **R2.3** Paginated query fallback for small fetches (<10k orders)
- **R2.4** Cost-based rate limiting: parse `extensions.cost.throttleStatus`, exponential backoff on `THROTTLED`
- **R2.5** Order normalization: GID stripping, `subtotalPriceSet.shopMoney.amount` for revenue (NOT `totalPriceSet`), refund-aware net revenue and net quantity per line item
- **R2.6** Filter exclusions: draft orders, `test: true` orders, cancelled orders (via `cancelledAt`)
- **R2.7** Fetch shop `ianaTimezone` once; bucket `createdAt` into local-time days (not UTC) to avoid midnight misclassification
- **R2.8** Required scopes documented: `read_orders`, **`read_all_orders`** (mandatory — `read_orders` alone caps to 60d), `read_products`, `read_inventory`
- **R2.9** GraphQL query uses `displayFinancialStatus` (NOT `financialStatus` — renamed)
- **R2.10** Multi-currency: always `shopMoney`, never `presentmentMoney`
- **R2.11** `fetch_orders`, `fetch_products`, `fetch_collections` async functions returning normalized dicts
- **R2.12** Local file cache for fetched orders, keyed by date range, TTL = `forecast_cache_ttl` (default 1hr)

## R3. Time-series shaping

- **R3.1** `orders_to_daily_series(orders, metric, group_by)` — aggregate to daily `pd.Series` with `DatetimeIndex`, gap-fill with zeros (not NaN)
- **R3.2** Metrics: `revenue` (net of refunds), `orders` (count), `units` (net of refund quantities), `aov` (revenue/orders)
- **R3.3** Group-by dimensions: store-level (None), `product_id`, `collection_id`, `sku`
- **R3.4** `resample_series(series, freq)` — D/W/M aggregation (sum for revenue/orders/units, mean for aov)
- **R3.5** `clean_series` — outlier capping (IQR or zscore), optional gap interpolation. Never removes data points (TimesFM needs continuity)
- **R3.6** Refund accounting at line-item level via line-item ID match (not variant ID)

## R4. TimesFM forecaster

- **R4.1** `ForecastEngine` class wrapping `TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")`
- **R4.2** Singleton model loading — load once at server startup via lifespan, never per-request
- **R4.3** `model.compile(ForecastConfig(...))` with: `max_context=1024`, `max_horizon=256`, `normalize_inputs=True`, `use_continuous_quantile_head=True`, `force_flip_invariance=True`, `infer_is_positive=True`, `fix_quantile_crossing=True`
- **R4.4** Univariate `forecast()` only in MVP — XReg deferred to Phase 2 behind feature flag
- **R4.5** `forecast(series, horizon)` accepts numpy array or list of arrays (batch); returns `ForecastResult`
- **R4.6** `ForecastResult` dataclass with `point_forecast`, `quantile_forecast` (channels: `[mean, q10..q90]`), `dates`, `confidence_bands` dict, `metadata`
- **R4.7** `ForecastResult.to_table()` → markdown table; `summary()` → natural-language summary
- **R4.8** Device selection: `cuda` if available, else `cpu`. **No `mps` branch** (TimesFM 2.5 source doesn't support it; document as CPU on Apple Silicon)
- **R4.9** `torch.set_float32_matmul_precision("high")` at init
- **R4.10** First-run UX: log "Downloading TimesFM 2.5 (~400MB, one-time)…" so users don't think it hung
- **R4.11** Sine-wave sanity test in `test_forecaster.py` before fixture data tests

## R5. Covariate engineering (Phase 2)

- **R5.1** `build_covariates(date_range, orders, country, custom_events)` returning dict of name → numpy array aligned to date_range
- **R5.2** Built-in covariates: `day_of_week`, `is_weekend`, `month`, `is_holiday` (via `holidays` package, 60+ countries), `holiday_proximity` (-7 to +3 day window), `has_discount`, `discount_depth`
- **R5.3** Custom events: list of `{date, label, type}` dicts
- **R5.4** `build_future_covariates(horizon, last_date, country, planned_promos)` for the forecast window — holiday flags deterministic, promo flags from input
- **R5.5** Wire into `forecast_with_covariates()` API: dynamic_numerical_covariates as `Sequence[Sequence[float]]` of length `context_len + horizon` per series (NOT split historical/future)
- **R5.6** Feature-flagged: covariates off by default in MVP, opt-in via tool param

## R6. Analytics

- **R6.1** `analyze_promotion(orders, promo_start, promo_end, baseline_days)` → revenue lift, order lift, AOV change, discount depth, cannibalization estimate, post-promo hangover analysis
- **R6.2** `detect_anomalies(series, forecast, sensitivity)` — flag dates where actuals fell outside quantile bands; returns date, actual, expected, bounds, deviation %, direction
- **R6.3** `compare_periods(orders, period_a, period_b, metrics)` — YoY/MoM comparison per metric
- **R6.4** `cohort_retention(orders, cohort_period, periods_out)` — cohort matrix, retention rates, avg LTV by cohort

## R7. MCP server

- **R7.1** Built on `FastMCP` (NOT low-level `Server`) from `mcp.server.fastmcp`
- **R7.2** Pin `mcp>=1.27,<2.0`
- **R7.3** Lifespan pattern: initialize `httpx.AsyncClient` + `ForecastEngine` at startup, inject via `Context[ServerSession, AppContext]`
- **R7.4** Tool registration via `@mcp.tool()` decorator with Pydantic `BaseModel` input schemas
- **R7.5** Async tool handlers (required for httpx Shopify calls)
- **R7.6** All tool responses are markdown strings (FastMCP auto-wraps to `TextContent`)
- **R7.7** Errors caught per-tool, returned as friendly markdown — never raised
- **R7.8** **All Python logging to stderr only** (`logging.basicConfig(stream=sys.stderr)`). Stdio transport uses stdout for JSON-RPC framing — no `print()` allowed in server process
- **R7.9** Transports: `stdio` (default, for Claude Desktop / Code) and `streamable-http` (for hosted; NOT pure SSE — deprecated)
- **R7.10** In-protocol info via `ctx.info()` / `ctx.report_progress()` for long-running operations
- **R7.11** Console script `shopify-forecast-mcp` with sync `main()` wrapper

## R8. MCP tools (7 total)

- **R8.1** `forecast_revenue` — store-level revenue with confidence bands; params: `horizon_days`, `context_days`, `frequency`, `include_chart_data`
- **R8.2** `forecast_demand` — product/collection/SKU demand; params: `group_by`, `group_value`, `metric`, `horizon_days`, `top_n`; reorder alerts when projected demand > inventory
- **R8.3** `analyze_promotion` — past promo vs baseline; params: `promo_start`, `promo_end`, `promo_name`, `baseline_days`
- **R8.4** `detect_anomalies` — flag deviation days; params: `lookback_days`, `sensitivity` (low/medium/high), `metric`
- **R8.5** `compare_periods` — two-period comparison; params: `period_a_start/end`, `period_b_start/end`, `metrics`, `group_by`
- **R8.6** `compare_scenarios` — what-if forecasting with 2-4 scenarios varying `promo_dates` and `discount_depth`
- **R8.7** `get_seasonality` — explain learned seasonal patterns; params: `lookback_days`, `granularity` (day_of_week / monthly / quarterly)

## R9. CLI

- **R9.1** Console script `shopify-forecast` exposed via `[project.scripts]`
- **R9.2** Subcommands: `revenue`, `demand`, `promo`, `compare`
- **R9.3** Same backing core library as MCP server — no MCP runtime dependency
- **R9.4** Output to stdout as markdown (or `--json` flag for piping)

## R10. Testing

- **R10.1** `pytest` + `pytest-asyncio` in `strict` mode, configured in `pyproject.toml`
- **R10.2** Realistic fixture data in `tests/fixtures/`: 1yr of daily orders (~5k orders), mix of products across 3-4 collections, seasonal pattern (holiday spike, summer dip), 2-3 promo periods with discount codes, refunds mixed in
- **R10.3** Unit tests per module: `test_timeseries.py`, `test_covariates.py`, `test_forecaster.py`, `test_analytics.py`
- **R10.4** Integration tests: `test_shopify_client.py` (mock GraphQL responses, bulk op polling), `test_mcp_tools.py` (end-to-end with mock data)
- **R10.5** Shopify mocks via `respx` (httpx-native)
- **R10.6** Forecaster sine-wave smoke test before fixture-data tests

## R11. Documentation

- **R11.1** `README.md` — one-liner, why, quick start (clone-to-running <5min), tools table, 3-4 conversation examples, architecture diagram, configuration, CLI usage, dev/contributing, roadmap, license
- **R11.2** `docs/SETUP.md` — installation, Shopify custom app + token setup, scope configuration, env var setup
- **R11.3** `docs/TOOLS.md` — full reference for all 7 MCP tools with input schemas, example prompts, example outputs
- **R11.4** `docs/ARCHITECTURE.md` — two-layer design, data flow diagram, key design decisions
- **R11.5** Claude Desktop config snippet using `uvx shopify-forecast-mcp`

## R12. Distribution

- **R12.1** PyPI publish via `uv publish` (Trusted Publisher OIDC from GitHub Actions)
- **R12.2** Docker image (`ghcr.io/mcostigliola321/shopify-forecast-mcp`) — multistage with `python:3.12-slim`, `uv` from `ghcr.io/astral-sh/uv`, CPU torch
- **R12.3** Two image tags: `:latest` (lazy model download) and `:bundled` (model baked into separate build stage at `/opt/hf-cache`)
- **R12.4** GitHub Actions: test on Python 3.11, build wheel + sdist, publish on tag
- **R12.5** Skip npx wrapper — `uvx` is the equivalent and works natively in MCP client configs

## Performance targets

| Metric | Target |
|---|---|
| Model load | <30s first run / <5s cached |
| Store-level forecast (1yr context, 30d horizon) | <10s |
| SKU forecast (top 10) | <30s |
| Bulk fetch (10k orders) | <60s |
| RAM with model loaded | ~800MB |

## Out of scope

- Generic CSV ingestion — Shopify-native only
- Legacy forecasting models (Prophet, ARIMA, moving averages) — TimesFM only
- Web dashboard / UI — MCP + CLI only
- Per-store retraining — TimesFM is zero-shot
- Buyer-facing or dev-facing tooling — merchant operations only
- Multi-store support in MVP (deferred to Phase 3)
- npx Node wrapper (use `uvx` instead)
- Apple Silicon `mps` device support (TimesFM 2.5 source has no MPS branch)
