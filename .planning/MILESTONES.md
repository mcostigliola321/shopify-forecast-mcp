# Milestones

## v0.1.0 — MVP Distribution (Shipped: 2026-04-20)

**Delivered:** One-command Shopify sales forecasting for merchants via `uvx`, `pip`, or Docker — TimesFM 2.5 foundation model, 7 MCP tools, 6 CLI verbs, dual-backend (Shopify CLI toolkit + httpx), multi-store support.

**Stats:** 8 phases, 31 plans, 45 tasks, 140 commits, ~12,900 LOC (Python), 7 days (2026-04-13 → 2026-04-20).

**Live release:**
- PyPI: https://pypi.org/project/shopify-forecast-mcp/ (`0.1.0`)
- GHCR: https://github.com/mcostigliola321?tab=packages (`:latest`, `:bundled`, `:0.1.0`, `:0.1.0-bundled`; multi-arch amd64+arm64)
- GitHub Release: https://github.com/mcostigliola321/shopify-forecast-mcp/releases/tag/v0.1.0

**Key accomplishments:**

1. **Shopify Admin GraphQL client (Phase 2)** — async client with bulk-operation lifecycle (JSONL `__parentId` reconstruction), pagination, throttling, refund-aware normalization, test-order filtering, timezone bucketing.
2. **Time-series & TimesFM 2.5 forecaster (Phase 3)** — resample/clean pipeline with IQR+zscore outlier capping, singleton engine with lazy loading, sine-wave validated univariate inference, batch support.
3. **MCP server + CLI MVP (Phase 4)** — FastMCP server with `forecast_revenue`, `forecast_demand`, markdown output, full Pydantic validation, matching CLI verbs.
4. **Shopify CLI toolkit integration (Phase 4.1)** — dual-backend architecture (CliBackend primary, DirectBackend fallback), browser OAuth replacing manual token flow, public API unchanged.
5. **Analytics + XReg covariates (Phase 5)** — 4 MCP tools (`analyze_promotion`, `detect_anomalies`, `compare_periods`, `get_seasonality`), shared metrics infrastructure, XReg pipeline behind feature flag, YoY/MoM CLI shortcuts.
6. **Advanced tools (Phase 6)** — what-if `compare_scenarios`, inventory-aware reorder alerts in `forecast_demand` with days-to-stockout formula, multi-store config (domain/label resolution, cache isolation, `--store` CLI flag, `store` param on all 7 tools).
7. **v0.1.0 distribution pipeline (Phase 7)** — GitHub Actions publish workflow (wait-for-ci → PyPI via Trusted Publisher OIDC → GHCR multi-arch matrix → GitHub Release), 4-stage Dockerfile with lazy + bundled variants, full docs suite (README, CHANGELOG, SETUP, ARCHITECTURE with Mermaid, TOOLS auto-generated from Pydantic schemas), maintainer runbook.
8. **Live release validated** — `uvx shopify-forecast --help` → 30s cold, all 4 D-20 legs green (PyPI upload, GHCR multi-arch push, GitHub Release with assets, clone-to-running stopwatch), 354 tests pass, zero static secrets.

**Noteworthy in-flight fixes during Phase 7 release dry-run:**
- TimesFM swap `git+https` → PyPI-resolvable `timecopilot-timesfm` fork (PyPI rejects direct-URL `Requires-Dist`).
- Dockerfile missing `COPY README.md LICENSE` for hatchling metadata validation.
- PyPI upload idempotent pre-check (version-exists short-circuit) — prevents sdist-hash-drift failures on retagged SHAs.
- Owner rename `omnialta` → `mcostigliola321` across 84 references (plan had stale owner).

**Archive:** `.planning/milestones/v0.1.0-ROADMAP.md`, `.planning/milestones/v0.1.0-REQUIREMENTS.md`

---
