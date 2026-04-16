# Roadmap — shopify-forecast-mcp

Source: `.planning/REQUIREMENTS.md` (R1–R12), `.planning/research/SUMMARY.md`, `shopify-forecast-mcp-PRD.md`.
Granularity: **standard** (7 phases, 3–5 plans each). Build order follows PRD §Implementation Notes with XReg deferred from Phase 1 to Phase 3 per research finding.

Each phase is buildable, testable, and demoable before the next begins. Phases 1–4 together constitute the MVP (Phase 1 of the PRD); Phase 5 is PRD Phase 2 (analytics + covariates); Phase 6 is PRD Phase 3 (advanced); Phase 7 is PRD Phase 4 (distribution).

## Phases

- [x] **Phase 1: Scaffold & Config** — `uv` package layout, pyproject, config loader, smoke CI (completed 2026-04-13)
- [x] **Phase 2: Shopify Client** — async GraphQL client with bulk ops, pagination, refund-aware normalization (completed 2026-04-16)
- [ ] **Phase 3: Time-series & Forecaster** — aggregation pipeline and TimesFM 2.5 singleton wrapper
- [ ] **Phase 4: MCP Server Skeleton + CLI (MVP)** — FastMCP server, `forecast_revenue` + `forecast_demand`, CLI entry points
- [ ] **Phase 5: Analytics, Covariates & Remaining Tools** — analytics module, XReg behind flag, 4 more MCP tools
- [ ] **Phase 6: Advanced Tools** — `compare_scenarios`, inventory-aware reorder, multi-store
- [ ] **Phase 7: Distribution & Docs** — PyPI Trusted Publisher, Docker images, README/SETUP/TOOLS/ARCHITECTURE

---

## Phase Details

### Phase 1: Scaffold & Config

**Goal**: A `uv`-managed package that installs, imports, loads config from env, and runs a trivial smoke test in CI.
**Depends on**: Nothing
**Requirements**: R1.1, R1.2, R1.3, R1.4, R1.5, R1.6
**Plans**:
1. **Package skeleton** — `uv init --package`, `src/shopify_forecast_mcp/{core,mcp,cli.py}` directories, `__init__.py` files, hatchling backend, PEP 639 SPDX license string, two `[project.scripts]` entries, Python `>=3.11,<3.12`.
2. **Dependency pinning** — `mcp>=1.27,<2.0`, `httpx`, `pandas`, `numpy`, `pydantic-settings`, `holidays`, `pytest`/`pytest-asyncio`, PyTorch CPU via `[tool.uv.sources]` index override, **TimesFM as git dep pinned to commit SHA with `[torch]` extras** (verify SHA at scaffold time — flagged LOW confidence in research).
3. **Config module** — `core/config.py` using `pydantic-settings` with `SHOPIFY_FORECAST_*` prefix, `SecretStr` for token, validation errors surfaced clearly. `.env.example` with all vars documented.
4. **Repo hygiene & CI smoke** — `LICENSE` (MIT), `.gitignore`, `.python-version`, `README.md` placeholder, GitHub Actions workflow that runs `uv sync` + `uv build` + a one-line import smoke test on Python 3.11.

**Success criteria**:
- `uv sync` resolves cleanly on Linux + macOS; TimesFM installs from git pin
- `uv run python -c "from shopify_forecast_mcp.core.config import Settings; Settings()"` loads `.env` or errors with named missing vars
- `uv build` produces wheel + sdist
- CI green on push

---

### Phase 2: Shopify Client

**Goal**: Given credentials, fetch a year of normalized orders (refund-aware, test-order-filtered, timezone-bucketed) via paginated OR bulk path.
**Depends on**: Phase 1
**Requirements**: R2.1, R2.2, R2.3, R2.4, R2.5, R2.6, R2.7, R2.8, R2.9, R2.10, R2.11, R2.12, R10.5 (mocking infra)
**Plan files:** 4 plans, 3 waves
- [x] 02-01-PLAN.md — HTTP client + auth + schema constants (Wave 1)
- [x] 02-02-PLAN.md — Paginated orders query (Wave 2)
- [x] 02-03-PLAN.md — Bulk operations path (Wave 2, parallel with 02-02)
- [x] 02-04-PLAN.md — Normalization, caching, wrappers (Wave 3)

**Success criteria**:
- Against mocked GraphQL, `fetch_orders(start, end)` returns normalized dicts matching fixture expectations
- Bulk path correctly reconstructs parent→children from `__parentId` JSONL
- Refund accounting produces correct net revenue per line item in fixture test
- Rate-limit backoff triggers on simulated THROTTLED extension
- Timezone bucketing places a 23:30 local-time order in the correct local day (not UTC day)

---

### Phase 3: Time-series & Forecaster

**Goal**: Orders in → `ForecastResult` out, with a singleton TimesFM 2.5 model and univariate inference validated on sine-wave + fixture data.
**Depends on**: Phase 2 (for fixture shape)
**Requirements**: R3.1, R3.2, R3.3, R3.4, R3.5, R3.6, R4.1, R4.2, R4.3, R4.4, R4.5, R4.6, R4.7, R4.8, R4.9, R4.10, R4.11, R10.2, R10.3, R10.6
**Plans:** 4 plans, 3 waves
- [x] 03-01-PLAN.md — Time-series aggregation: orders_to_daily_series (Wave 1)
- [x] 03-02-PLAN.md — Resample & clean: resample_series, clean_series (Wave 1, parallel with 03-01)
- [x] 03-03-PLAN.md — TimesFM engine: ForecastEngine singleton + sine-wave test (Wave 2)
- [x] 03-04-PLAN.md — ForecastResult dataclass + fixture data + integration tests (Wave 3)

**Success criteria**:
- Sine-wave forecast recovers the known period within quantile band
- Fixture-data forecast runs in <10s for 1yr context / 30d horizon on CPU
- Model loads once across multiple sequential `forecast()` calls (verified via log count)
- `ForecastResult.to_table()` renders a readable markdown table; `summary()` includes trend direction and band width
- Channel-0 = mean verified (regression guard against the PRD's "q10" mistake)

---

### Phase 4: MCP Server Skeleton + CLI (MVP)

**Goal**: A working `shopify-forecast-mcp` server in Claude Desktop that answers `forecast_revenue` and `forecast_demand` with real Shopify data, plus a matching CLI.
**Depends on**: Phase 3
**Requirements**: R7.1, R7.2, R7.3, R7.4, R7.5, R7.6, R7.7, R7.8, R7.9, R7.10, R7.11, R8.1, R8.2, R9.1, R9.2, R9.3, R9.4, R10.4 (mcp tool tests)
**Plans**:
1. **FastMCP server skeleton** — `mcp/server.py` using `FastMCP` from `mcp.server.fastmcp` (NOT low-level `Server`). Lifespan `@asynccontextmanager` initializes `httpx.AsyncClient` + `ForecastEngine`, injects via `Context[ServerSession, AppContext]`. Transports: `stdio` default, `streamable-http` optional (NOT pure SSE). **All logging to stderr** via `logging.basicConfig(stream=sys.stderr)` — zero `print()` in server process. Console script `shopify-forecast-mcp` with sync `main()` around `asyncio.run()`.
2. **`forecast_revenue` tool** — `mcp/tools.py` with `@mcp.tool()` decorator, Pydantic `BaseModel` input (`horizon_days`, `context_days`, `frequency`, `include_chart_data`). Async handler: fetch orders → aggregate → forecast → return markdown string. Errors caught and returned as friendly markdown, never raised. `ctx.info()` / `ctx.report_progress()` during long ops.
3. **`forecast_demand` tool** — extend `timeseries.py` group-by usage; input schema includes `group_by`, `group_value`, `metric`, `horizon_days`, `top_n`. Reorder alerts when projected demand > inventory (pull inventory via client).
4. **CLI + end-to-end tests** — `cli.py` with subcommands `revenue` and `demand` (the other two CLI verbs arrive in Phase 5). Shares the core library, no MCP runtime import. `--json` flag for piping, markdown to stdout default. `tests/test_mcp_tools.py` end-to-end with mocked Shopify + real forecaster, plus Claude Desktop config snippet for manual validation.

**Success criteria**:
- `uvx shopify-forecast-mcp` launches under Claude Desktop; both tools appear in the tool list
- "What does next month look like?" returns a markdown table with point forecast and 80% band, no stack traces on error paths
- Stdio transport never emits anything to stdout except JSON-RPC framing (verified via test capturing stdout)
- `shopify-forecast revenue --horizon 30` CLI prints markdown table
- `pytest` green on fixture-backed end-to-end tests for both tools

**MVP milestone**: End of Phase 4 = PRD's "Phase 1 MVP" complete and shippable.

---

### Phase 5: Analytics, Covariates & Remaining Tools

**Goal**: Five more MCP tools (`analyze_promotion`, `detect_anomalies`, `compare_periods`, `get_seasonality`) plus XReg covariates behind a feature flag, plus the remaining CLI verbs.
**Depends on**: Phase 4
**Requirements**: R5.1, R5.2, R5.3, R5.4, R5.5, R5.6, R6.1, R6.2, R6.3, R6.4, R8.3, R8.4, R8.5, R8.7, R9.2 (promo/compare verbs)
**Plans**:
1. **Analytics module** — `core/analytics.py`: `analyze_promotion`, `detect_anomalies` (use mean + quantile bands — channel 0 = mean discipline from Phase 3), `compare_periods` (YoY/MoM per metric), `cohort_retention`. Unit tests with fixture data.
2. **Covariate engineering (feature-flagged)** — `core/covariates.py`: `build_covariates` with `day_of_week`, `is_weekend`, `month`, `is_holiday` (60+ countries via `holidays`), `holiday_proximity` (-7/+3), `has_discount`, `discount_depth`, custom events. `build_future_covariates` for horizon window.
3. **Wire XReg into forecaster** — use `model.forecast_with_covariates()` (separate method, not flat dict on `forecast()`), dynamic numerical covariates as `Sequence[Sequence[float]]` of length `context_len + horizon` per series. Off by default; opt-in tool param. Document marginal value caveat from research.
4. **Four analytics MCP tools + CLI verbs** — `analyze_promotion`, `detect_anomalies`, `compare_periods`, `get_seasonality` via `@mcp.tool()`, each returning markdown tables and a natural-language summary. CLI subcommands `promo` and `compare`. End-to-end fixture tests per tool.

**Success criteria**:
- `analyze_promotion` on the fixture promo window returns sensible lift, AOV change, and hangover estimate
- `detect_anomalies` correctly flags an injected spike day in the fixture
- `compare_periods` produces a YoY table matching hand-computed truth
- `get_seasonality` surfaces the fixture's holiday spike and summer dip
- Covariate-enabled forecast runs without crashing on the fixture and returns a `ForecastResult` (accuracy delta measured but not gated)

---

### Phase 6: Advanced Tools

**Goal**: What-if scenario planning, inventory-aware reorder suggestions, and multi-store support.
**Depends on**: Phase 5
**Requirements**: R8.6 (`compare_scenarios`), plus multi-store support (deferred from MVP per PROJECT.md "Out of Scope → deferred to Phase 3")
**Plans**:
1. **`compare_scenarios` tool** — what-if forecasting with 2–4 scenarios varying `promo_dates` and `discount_depth`. Builds future covariates per scenario, reuses XReg pathway from Phase 5, returns a side-by-side markdown comparison table.
2. **Inventory-aware reorder** — extend `forecast_demand` to produce reorder alerts using `read_inventory` data: days-until-stockout, suggested reorder qty, lead-time param.
3. **Multi-store support** — config shape for multiple store credentials, store selector on every tool, cache isolation per store. Document Claude Desktop config for multi-store setup.

**Success criteria**:
- `compare_scenarios` with 3 promo scenarios returns 3 differentiated forecasts in one markdown response
- Reorder alert fires when fixture inventory is below projected 30d demand
- Multi-store config loads two stores; a single MCP session can forecast either without restart

---

### Phase 7: Distribution & Docs

**Goal**: One-command install for merchants via `uvx`, Docker images on GHCR (lazy + bundled), and documentation that gets a new user clone-to-running in under 5 minutes.
**Depends on**: Phase 6 (or earlier — can start once Phase 4 MVP is stable; sequenced last so docs reflect final tool set)
**Requirements**: R11.1, R11.2, R11.3, R11.4, R11.5, R12.1, R12.2, R12.3, R12.4, R12.5
**Plans**:
1. **PyPI publishing** — GitHub Actions workflow using `uv publish` with Trusted Publisher OIDC, tag-triggered, builds wheel + sdist, tests on Python 3.11 first. Verify installability via `uvx shopify-forecast-mcp` from PyPI.
2. **Docker images** — multistage `Dockerfile` on `python:3.12-slim` with `uv` from `ghcr.io/astral-sh/uv`, CPU torch. Two tags: `:latest` (lazy model download) and `:bundled` (TimesFM baked into a separate build stage at `/opt/hf-cache`). Publish to `ghcr.io/omnialta/shopify-forecast-mcp`. Skip npx wrapper — `uvx` is the equivalent.
3. **README + SETUP + TOOLS + ARCHITECTURE** — `README.md` with one-liner, quick start, tools table, 3–4 conversation examples, architecture diagram, config, CLI usage, roadmap, license. `docs/SETUP.md` (custom app + token + scopes + env). `docs/TOOLS.md` (all 7 tools with schemas + example prompts + outputs). `docs/ARCHITECTURE.md` (two-layer design, data flow, key decisions including the research corrections). Claude Desktop config snippet using `uvx`.
4. **Release cut** — tag v0.1.0, verify GH Actions pipeline end-to-end (test → build → publish PyPI + GHCR), smoke-test `uvx shopify-forecast-mcp` from a clean machine, announce.

**Success criteria**:
- Fresh laptop, no prior Python setup → installs and runs via `uvx shopify-forecast-mcp` in under 5 minutes
- `docker run ghcr.io/omnialta/shopify-forecast-mcp:bundled` starts without an internet download
- PyPI publish on tag succeeds via OIDC with no static token
- README quick-start walkthrough reproduces the "what does next month look like?" flow

---

## Coverage Matrix

Every R-ID from REQUIREMENTS.md mapped to exactly one phase. Sub-requirements inherit their parent's phase unless noted.

| R-ID | Topic | Phase |
|---|---|---|
| R1 (R1.1–R1.6) | Scaffold & packaging | Phase 1 |
| R2 (R2.1–R2.12) | Shopify Admin API client | Phase 2 |
| R3 (R3.1–R3.6) | Time-series shaping | Phase 3 |
| R4 (R4.1–R4.11) | TimesFM forecaster | Phase 3 |
| R5 (R5.1–R5.6) | Covariate engineering | Phase 5 |
| R6 (R6.1–R6.4) | Analytics | Phase 5 |
| R7 (R7.1–R7.11) | MCP server | Phase 4 |
| R8.1 `forecast_revenue` | MCP tool | Phase 4 |
| R8.2 `forecast_demand` | MCP tool | Phase 4 |
| R8.3 `analyze_promotion` | MCP tool | Phase 5 |
| R8.4 `detect_anomalies` | MCP tool | Phase 5 |
| R8.5 `compare_periods` | MCP tool | Phase 5 |
| R8.6 `compare_scenarios` | MCP tool | Phase 6 |
| R8.7 `get_seasonality` | MCP tool | Phase 5 |
| R9 (R9.1–R9.4) | CLI | Phase 4 (revenue, demand) + Phase 5 (promo, compare) |
| R10 (R10.1–R10.6) | Testing | Phase 1 (config), Phase 2 (client mocks + respx), Phase 3 (forecaster + fixtures + sine wave), Phase 4 (MCP e2e), Phase 5 (analytics/covariates) |
| R11 (R11.1–R11.5) | Documentation | Phase 7 |
| R12 (R12.1–R12.5) | Distribution | Phase 7 |

**Unmapped**: none.

**Performance targets** (REQUIREMENTS.md §Performance) are validated at the phase where the target applies:
- Model load <30s / <5s cached → Phase 3 success criteria
- Store-level forecast <10s → Phase 3 success criteria
- SKU forecast (top 10) <30s → Phase 4 success criteria (under `forecast_demand`)
- Bulk fetch <60s for 10k orders → Phase 2 success criteria (add to bulk-op plan)
- ~800MB RAM with model loaded → Phase 3 success criteria

## Notes

- **PRD Phase 1 (MVP) = our Phases 1–4.** Split per the brief because the single-phase MVP in the PRD violates the 3–5 plan granularity rule.
- **XReg moved from MVP to Phase 5** behind a feature flag, per research finding (linear-ridge, marginal value over the 200M foundation model alone).
- **All 5 critical research corrections baked in**: TimesFM git pin, FastMCP API, single-distribution layout, `displayFinancialStatus`, `read_all_orders` scope.
- **Phase 6 (advanced) has only 3 plans** — intentionally smaller than other phases because multi-store and scenario forecasting are optional and can be punted to v2 if timeline pressure emerges.
- **Sequencing risk**: Phase 3 depends on a valid TimesFM commit SHA (LOW research confidence). Scaffold plan 2 must verify the SHA before Phase 3 begins.
