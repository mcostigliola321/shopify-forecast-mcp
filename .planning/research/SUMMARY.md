# Research Synthesis — shopify-forecast-mcp

Synthesis of four parallel research streams (TimesFM 2.5, Shopify GraphQL Admin API, MCP Python SDK, packaging/distribution). Read full reports in this directory for source links.

## The PRD is mostly right but has 5 critical errors that block Phase 1 if uncorrected

1. **TimesFM 2.5 is not on PyPI.** `pip install timesfm` returns 1.3.0, which only includes 2.0 checkpoints. The 2.5 model class (`TimesFM_2p5_200M_torch`) lives on the master branch of `google-research/timesfm`. Must install via git dependency: `timesfm @ git+https://github.com/google-research/timesfm.git@<sha>` with `[torch,xreg]` extras. Pin to a commit SHA for reproducibility.

2. **MCP SDK Server API is stale.** PRD imports `from mcp.server import Server` — that's the low-level API. The idiomatic 2026 pattern is `from mcp.server.fastmcp import FastMCP, Context` with `@mcp.tool()` decorators. Pin `mcp>=1.27,<2.0` (v2 is pre-alpha, breaking).

3. **Source layout collides with installed packages.** PRD's `src/core/` and `src/mcp/` as top-level directories are wrong: (a) you can't have two top-level namespaces in one distribution, (b) `src/mcp/` collides with the installed `mcp` SDK package. Restructure to a single distribution: `src/shopify_forecast_mcp/{core,mcp,cli.py}`.

4. **Shopify GraphQL field rename.** PRD uses `financialStatus` in the bulk operation query (line 284). That field has been renamed to `displayFinancialStatus` in the current schema. Query won't compile as written. The `query: "financial_status:paid"` filter syntax is unaffected — only the response field name changed.

5. **Missing `read_all_orders` scope.** PRD only lists `read_orders`, which silently caps history to the **last 60 days**. For meaningful forecasting, `read_all_orders` is mandatory. Drop `read_reports` (unrelated to orders).

## Other corrections worth making

| Area | PRD | Correct |
|---|---|---|
| Shopify API version | `2026-01` | Bump to **`2026-04`** (current stable, 12-month support) |
| TimesFM `xreg` API | flat `dict[str, np.ndarray]` to `forecast()` | Use `forecast_with_covariates()` — separate method, separate dynamic/static × numerical/categorical dicts. **Defer to Phase 2.** |
| TimesFM `mps` device | listed as supported | Source has no `mps` branch — Apple Silicon falls back to CPU. Drop or document fallback. |
| Quantile interpretation | "10 quantiles, 10th–90th" | Channels are `[mean, q10, q20, q30, q40, q50, q60, q70, q80, q90]` — channel 0 is **mean**, not q10. Critical for anomaly detection. |
| MCP SSE transport | "Support stdio and SSE" | Use **streamable-http** — pure SSE deprecated per 2025 spec revision |
| PRD logging | implicit | **All Python logging MUST go to stderr.** Stdio transport uses stdout for JSON-RPC framing — any `print()` corrupts the protocol stream. |
| Rate limit "1000/sec" | flat number | That's **Shopify Plus only** (20k bucket, 1k restore). Standard tier is 100/sec with 2k bucket. Bulk ops bypass entirely — main reason to use them. |
| PyPI `xreg` priority | Phase 1 covariates | XReg is just linear ridge regression on covariates, not deep attention. Marginal value over the 200M foundation model on its own. **MVP uses univariate `forecast()` only**, XReg gated behind feature flag in Phase 2. |
| Bulk op polling | `currentBulkOperation` | Use `bulkOperation(id: $id)` with explicit ID. JSONL output flattens nested connections — children arrive as sibling lines with `__parentId`, must reconstruct client-side. |
| Test orders | not mentioned | `test: true` orders aren't filtered automatically. Add `test` field and filter client-side. Also handle `cancelledAt` and shop `ianaTimezone` for day-bucketing. |

## Architecture decisions locked

1. **Two-layer:** `src/shopify_forecast_mcp/core/` (importable lib, no MCP) + `src/shopify_forecast_mcp/mcp/` (FastMCP wrapper). PRD's intent is right; only the path shape changes.
2. **Single distribution name:** `shopify-forecast-mcp` (PyPI), import as `shopify_forecast_mcp`.
3. **Two console scripts:** `shopify-forecast` (CLI) and `shopify-forecast-mcp` (MCP server). Both `main()` are sync wrappers around `asyncio.run()`.
4. **uv is the toolchain:** `uv init --package` → `hatchling` backend → `src/` layout → `uv build` → `uv publish`.
5. **PyTorch CPU wheels by default** via `[tool.uv.sources]` index override. GPU as opt-in extra. macOS falls through to PyPI.
6. **HuggingFace model cache:** Honor `$HF_HOME`. In Docker, bake into a separate build stage so the model travels with the image. Two image tags: `:latest` (lazy) and `:bundled` (model baked in).
7. **Lifespan pattern in MCP server:** Initialize `httpx.AsyncClient` and `ForecastEngine` (TimesFM singleton) in `@asynccontextmanager` lifespan. Inject via `Context[ServerSession, AppContext]`.
8. **All MCP responses are markdown strings** returned from `async def` tools. Errors caught and returned as friendly markdown — never raised.
9. **Shopify client = raw `httpx.AsyncClient`** (~80 LOC). Don't pull `shopify-python-api` (sync only) or `gql` (over-engineered). Single endpoint, full control of throttle/retry.
10. **Skip npx wrapper.** `uvx shopify-forecast-mcp` is the 2026 idiomatic equivalent and works natively in Claude Desktop configs.

## Build order (revised from PRD)

The PRD's build order is mostly right. Only XReg moves from Phase 1 to Phase 2.

1. Scaffold (uv init, pyproject.toml, src layout, LICENSE, .env.example, smoke test) — Phase 1
2. `config.py` — Phase 1
3. `shopify_client.py` (paginated → bulk ops, JSONL parsing with `__parentId` reconstruction, refund accounting, timezone-aware day bucketing) — Phase 1
4. `timeseries.py` (orders → daily/weekly/monthly series, gap fill, outlier capping) — Phase 1
5. `forecaster.py` (TimesFM singleton, **univariate** `forecast()` only, ForecastResult dataclass) — Phase 1
6. MCP server skeleton + `forecast_revenue` + `forecast_demand` tools — Phase 1
7. CLI entry point (`shopify-forecast revenue|demand`) — Phase 1
8. `analytics.py` (period comparison, anomaly detection, promo analysis, cohort) — Phase 2
9. `compare_periods`, `detect_anomalies`, `analyze_promotion`, `get_seasonality` MCP tools — Phase 2
10. `covariates.py` + XReg via `forecast_with_covariates` (feature flag) — Phase 2
11. `compare_scenarios` (what-if), inventory-aware reorder, multi-store — Phase 3
12. PyPI publish, Docker image (multistage, model baked), GH Actions trusted publisher, README + SETUP + TOOLS docs — Phase 4

## Open questions for phase-specific research

- **TimesFM:** XReg padding semantics with variable-length series; whether `compile()` must be re-run when `max_horizon` changes mid-session; consumer GPU benchmarks (no published numbers).
- **Shopify:** exact `extensions.cost.throttleStatus` shape for backoff strategy; bulk op concurrent limit (PRD assumes 5 in 2026-01).
- **MCP:** confirm `mcp[cli]` still ships `mcp dev` inspector in 1.27.
- **Packaging:** verify exact TimesFM commit SHA at scaffold time; PyPI Trusted Publisher OIDC setup (~15 min spike).

## Confidence assessment

| Domain | Confidence | Notes |
|---|---|---|
| TimesFM 2.5 API | HIGH | Verified against master branch source |
| Shopify GraphQL 2026-04 | HIGH | shopify.dev official docs |
| MCP SDK FastMCP API | HIGH | Verified against `mcp==1.27.0` SDK |
| uv + pyproject.toml | HIGH | Astral docs, PyPA spec |
| Docker + TimesFM bake | MEDIUM | Pattern is standard, exact final size depends on TimesFM transitive deps |
| TimesFM commit SHA | LOW | Must verify at scaffold time |
