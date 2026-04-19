# Phase 7: Distribution & Docs - Context

**Gathered:** 2026-04-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Ship `shopify-forecast-mcp` publicly as an installable product. Four deliverables:
1. **PyPI publish pipeline** — GitHub Actions workflow using `uv publish` + Trusted Publisher OIDC, tag-triggered, produces wheel + sdist + GitHub Release with attached artifacts.
2. **Docker images on GHCR** — `ghcr.io/omnialta/shopify-forecast-mcp:latest` (lazy model download) and `:bundled` (TimesFM baked into `/opt/hf-cache`), multi-arch linux/amd64 + linux/arm64.
3. **User-facing documentation** — `README.md`, `docs/SETUP.md`, `docs/TOOLS.md`, `docs/ARCHITECTURE.md`, all written merchant-operator-first. Target: clone-to-running in <5 minutes.
4. **v0.1.0 release cut** — Exercise the full pipeline via a `v0.1.0-rc1` dry-run, then tag `v0.1.0` as a production alpha (classifier stays "Development Status :: 3 - Alpha").

Out of scope for this phase: new tools, new capabilities, Shopify Sidekick App Extension, landing site, web dashboard.

</domain>

<decisions>
## Implementation Decisions

### PyPI Release Flow
- **D-01:** Publish trigger = git tag matching `v*`. No manual dispatch backup for v0.1.0 (add later if needed). Single GitHub Actions workflow (`.github/workflows/publish.yml`) gated on the existing `ci.yml` passing.
- **D-02:** Direct to PyPI on every tag. No TestPyPI staging. PEP 440 pre-release tags (e.g., `v0.1.0-rc1`) publish to PyPI as pre-releases — `uvx` will not install them by default without `--prerelease=allow`, which is the desired gating behavior.
- **D-03:** Test matrix inside the publish workflow = Python 3.11 only, matching `pyproject.toml` (`>=3.11,<3.12`). Do not duplicate the existing 3.11 Ubuntu + macOS smoke job — make the publish job depend on it being green for the same SHA.
- **D-04:** Artifact scope = PyPI upload **plus** a GitHub Release created from the tag, with `dist/*.whl` and `dist/*.tar.gz` attached, body populated from the matching `CHANGELOG.md` section (see D-16).
- **D-05:** Publisher auth = PyPI Trusted Publisher OIDC (`id-token: write` permission on the publish job). No static token committed anywhere. PyPI project created and Trusted Publisher configured before the first real tag (part of planning prep, not code).

### Docker Strategy
- **D-06:** Base image = `python:3.11-slim` in both stages. Do **not** widen `pyproject.toml` to 3.12 in this phase — keep pyproject as the source of truth. The ROADMAP's `python:3.12-slim` reference was aspirational; revisit in v0.2 alongside a TimesFM/torch 3.12 compatibility check.
- **D-07:** Multi-arch build = `linux/amd64` + `linux/arm64` via `docker buildx`. Accept ~2× build time for native Apple Silicon support — merchants running MCP locally on M-series Macs is a primary use case.
- **D-08:** Dockerfile layout = multistage. Builder stage uses `ghcr.io/astral-sh/uv` to `uv sync --frozen` into a venv. Final stage copies the venv; CPU torch only. Two targets:
  - `:latest` — lazy: model downloads on first forecast call.
  - `:bundled` — adds a second build stage that runs `python -c "from timesfm import TimesFM_2p5_200M_torch; TimesFM_2p5_200M_torch.from_pretrained('google/timesfm-2.5-200m-pytorch')"` with `HF_HOME=/opt/hf-cache`, then `COPY --from=model-build /opt/hf-cache /opt/hf-cache` into the final image. Final image sets `HF_HOME=/opt/hf-cache` so loads are no-internet.
- **D-09:** Container credential delivery = environment variables only. `SHOPIFY_FORECAST_SHOP` + `SHOPIFY_FORECAST_ACCESS_TOKEN` force the DirectBackend path (httpx). Browser OAuth via `shopify store auth` does **not** work inside containers — documented explicitly in SETUP.md. No Shopify CLI inside the image.
- **D-10:** Entrypoint = custom `/app/entrypoint.sh` script. No arg → `shopify-forecast-mcp` (MCP server over stdio). First arg in `{revenue, demand, promo, compare, scenarios, auth, --help}` → dispatches to `shopify-forecast` CLI verb. First arg `mcp` → explicit MCP server. Enables `docker run ghcr.io/omnialta/shopify-forecast-mcp:bundled revenue --horizon 30` for one-shot CLI use.
- **D-11:** Multi-store env var support in Docker = documented pattern using compose-style `SHOPIFY_FORECAST_STORES__0__SHOP` etc. (matches pydantic-settings nested-env convention from Phase 6 D-10). No special Docker logic required.

### Documentation Scope & Style
- **D-12:** Primary reader = merchant-operator (store owner who can use a terminal but isn't a Python dev). Developer-oriented detail appears in explicit "For developers" call-out blocks. `ARCHITECTURE.md` drops into dev voice naturally.
- **D-13:** MCP client coverage = three tiers in README + SETUP.md:
  - **Claude Desktop** — full walkthrough with `claude_desktop_config.json` snippet using `uvx shopify-forecast-mcp`.
  - **Claude Code** — CLI install + config snippet.
  - **Generic MCP server spec** — section documenting stdio entrypoint, required env vars, and a note that it works with Cursor/custom agents — link to MCP spec.
  - **Not included in v0.1.0:** Cursor walkthrough, Shopify Sidekick teaser.
- **D-14:** `docs/ARCHITECTURE.md` uses **Mermaid** diagrams (rendered by GitHub natively). Required diagrams:
  - Two-layer architecture (core lib ↔ MCP wrapper ↔ CLI).
  - End-to-end data flow: Shopify GraphQL → normalize → orders_to_daily_series → clean/resample → ForecastEngine → ForecastResult → tool response.
  - Backend selection: DirectBackend vs CliBackend decision tree (from Phase 4.1).
- **D-15:** `docs/TOOLS.md` depth = per-tool section for each of the 7 tools. Each section includes: Pydantic input schema rendered as a table, 2 sample merchant prompts, 1 fully-rendered markdown output. Top-of-page index with anchor links. Derived directly from the tool code — no drift.
- **D-16:** `README.md` structure (merchant-first): one-liner → "Why" (merchant value, not tech flex) → Quick start (uvx + Claude Desktop config block, 3 steps) → 3-4 conversation examples ("what does next month look like?", "which SKUs need reordering?", "how did Black Friday perform vs last year?", "compare 3 promo scenarios") → Tools table with anchor links to TOOLS.md → Architecture diagram (mermaid, summary) → Configuration summary with deep-link to SETUP.md → CLI usage summary → Roadmap (link to ROADMAP.md) → Contributing → License.
- **D-17:** `docs/SETUP.md` covers: Shopify custom app creation, required scopes (`read_orders`, `read_all_orders`, `read_products`, `read_inventory`), access token generation, env var setup, two install paths (uvx + Docker), multi-store config, verification step ("ask Claude 'what does next month look like?' and see the expected response shape"). Screenshots for the Shopify admin portions. Browser OAuth via `shopify store auth` documented as the interactive alternative (doesn't work in Docker — flagged in Docker section).
- **D-18:** `README.md` includes a persistent "⚠️ v0.1.0 Alpha" callout banner until we bump to beta.

### v0.1.0 Release Positioning
- **D-19:** Development status = **Alpha**. Keep `Development Status :: 3 - Alpha` classifier in `pyproject.toml`. README alpha banner stays. Honest for a zero-external-user launch.
- **D-20:** Pre-release dry-run = tag `v0.1.0-rc1` first. All four legs must go green: (a) CI tests pass, (b) publish workflow uploads to PyPI as pre-release, (c) `uvx --prerelease=allow shopify-forecast-mcp@0.1.0rc1` works on a fresh machine, (d) Docker images `:latest-rc` + `:bundled-rc` publish to GHCR and run. Only after rc1 validates all four do we tag `v0.1.0`.
- **D-21:** Changelog = `CHANGELOG.md` at repo root, Keep a Changelog format, semver sections. Phase 7 seeds it with the full `[0.1.0]` entry covering Phases 1–6 deliverables under Added. Publish workflow extracts the matching section (parsed by version header) for the GitHub Release body — single source of truth.
- **D-22:** Launch announce scope = **repo-only** for v0.1.0. GitHub Release notes + README banner linking to the Release + one pinned "Feedback wanted" issue. No Shopify community posts, no X/LinkedIn, no HN submission at this stage. Re-evaluate for v0.2 once we have usage data.

### Claude's Discretion
- Exact Mermaid diagram syntax and layout (flowchart TD vs LR, node shapes, styling).
- Shell syntax details inside `/app/entrypoint.sh` (bash vs sh, error handling style).
- Precise `CHANGELOG.md` wording under `[0.1.0] Added` — should accurately list the 7 MCP tools, 4 CLI verbs, dual-backend architecture, multi-store support, covariate engineering; exact phrasing is Claude's call.
- Screenshot tooling and image storage location in `docs/` (likely `docs/images/`).
- Whether to add `publiccode.yml` or `citation.cff` metadata (nice-to-have, not required).
- GitHub Actions runner OS for the publish job (ubuntu-latest assumed unless there's reason otherwise).
- Docker `HEALTHCHECK` directive wording and whether to include one (MCP servers over stdio don't have a natural health endpoint).
- Precise anchor slugs and nav structure within TOOLS.md.

### Folded Todos
None — `gsd-tools todo match-phase 7` returned zero matches.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` §R11 — Documentation requirements (R11.1–R11.5: README, SETUP, TOOLS, ARCHITECTURE, Claude Desktop snippet)
- `.planning/REQUIREMENTS.md` §R12 — Distribution requirements (R12.1–R12.5: PyPI OIDC, Docker tags, multi-stage, test matrix, skip npx)
- `.planning/ROADMAP.md` §"Phase 7: Distribution & Docs" — 4-plan breakdown, success criteria including `<5min` install, `uvx` validation, OIDC success
- `.planning/PROJECT.md` — "What This Is" framing + constraints (MIT, Python 3.11+, dual-backend, markdown-only responses) for README voice

### Source spec
- `shopify-forecast-mcp-PRD.md` §"Distribution" + §"Implementation Notes" — Original PRD distribution & docs plan (project root)

### Existing infrastructure
- `.github/workflows/ci.yml` — Current smoke/test workflow. The new `publish.yml` will depend on this being green for the same SHA, not duplicate it.
- `pyproject.toml` — Package metadata, version, console scripts, license, classifiers, Python constraint (`>=3.11,<3.12`) — authoritative.
- `uv.lock` — Frozen dependency lock consumed by `uv sync --frozen` in both CI and Docker builds.

### Prior phase context (carries forward)
- `.planning/phases/04.1-shopify-cli-toolkit-integration/04.1-CONTEXT.md` — Dual-backend architecture decisions (D-01 factory, D-02 CLI-only path) for ARCHITECTURE.md and Docker credential section.
- `.planning/phases/05-analytics-covariates-remaining-tools/05-CONTEXT.md` — Covariate disclaimer (D-20), metrics list (D-16/D-17), CLI verb shape (D-21–D-23) — source for TOOLS.md entries on analyze_promotion, detect_anomalies, compare_periods, get_seasonality and README examples.
- `.planning/phases/06-advanced-tools/06-CONTEXT.md` — Multi-store config shape (D-10–D-14), compare_scenarios tool (D-01–D-04), reorder logic (D-05–D-09) — source for TOOLS.md entries on compare_scenarios + forecast_demand reorder alerts, and SETUP.md multi-store section.

### Research
- `.planning/research/SUMMARY.md` — TimesFM download size + load time (affects SETUP.md expectations + Docker :bundled rationale)
- `.planning/research/packaging.md` — uv publish + Trusted Publisher OIDC flow reference

### External documentation to consult during implementation
- PyPI Trusted Publisher docs: https://docs.pypi.org/trusted-publishers/
- `uv publish` docs: https://docs.astral.sh/uv/guides/publish/
- Docker buildx multi-arch: https://docs.docker.com/build/building/multi-platform/
- Keep a Changelog: https://keepachangelog.com/en/1.1.0/
- MCP specification for the generic client section in SETUP.md

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `.github/workflows/ci.yml` — smoke + pytest workflow on Ubuntu + macOS, Python 3.11. The publish workflow should depend on the same SHA passing this, not duplicate test logic.
- `pyproject.toml` — already has `[project.scripts]` entries, license, classifiers, keywords, URLs. Publish workflow consumes it as-is.
- `uv.lock` — deterministic install for Docker builds (`uv sync --frozen`).
- `README.md` placeholder (337 bytes) — overwrite entirely; keep only the project name header pattern.
- `docs/` exists but only contains `docs/superpowers/specs/` (internal design specs from Phase 4.1). New user docs go directly in `docs/` alongside — no nesting needed.
- `src/shopify_forecast_mcp/mcp/tools.py` — source of truth for TOOLS.md schema extraction (Pydantic param models per tool).
- `src/shopify_forecast_mcp/cli.py` — source of truth for CLI verb docs in README + SETUP.md.
- `src/shopify_forecast_mcp/config.py` — source of truth for env var names in SETUP.md (the `SHOPIFY_FORECAST_*` prefix plus multi-store nested keys).
- `LICENSE` — MIT, already in place.
- `.env.example` — already documents required env vars; SETUP.md should mirror this, not replace it.

### Established Patterns
- All markdown outputs across tools follow the "table + summary" pattern — README examples should use actual rendered outputs copied from test fixtures, not hand-written mockups.
- Config via pydantic-settings `SHOPIFY_FORECAST_*` prefix — SETUP.md env var table reflects this consistently.
- Dual-backend architecture (Phase 4.1) — docs must explain both DirectBackend (Docker path) and CliBackend (interactive host path).
- Multi-store config shape (Phase 6) — docs must cover single-store (default) AND multi-store in both SETUP.md and the Claude Desktop config snippet.
- Two console scripts (`shopify-forecast` + `shopify-forecast-mcp`) — both must be documented; `uvx shopify-forecast-mcp` is the headline install.

### Integration Points
- `.github/workflows/publish.yml` — new file. Triggered on `push: tags: ['v*']`. Jobs: wait-for-ci → build → publish-pypi (OIDC) → publish-docker (multi-arch, 2 tags) → create-release.
- `Dockerfile` — new file at repo root. Multi-stage. Two build targets via `ARG INCLUDE_MODEL=false` or separate `bundled` stage.
- `docker-entrypoint.sh` — new file, copied into image, referenced by `ENTRYPOINT`.
- `.dockerignore` — new file to keep `.planning/`, `.venv/`, `tests/`, `.pytest_cache/` out of build context.
- `CHANGELOG.md` — new file at repo root.
- `docs/SETUP.md`, `docs/TOOLS.md`, `docs/ARCHITECTURE.md` — new files (README stays at repo root).
- `docs/images/` — new directory for SETUP.md screenshots.
- `README.md` — full rewrite (currently placeholder).

</code_context>

<specifics>
## Specific Ideas

- README's "Why" section leads with merchant value, not model/tech flex. Sample framing: "Ask your AI assistant what next month looks like and get a foundation-model-grade forecast grounded in your real Shopify order history — no dashboards, exports, or training." (Adapted from PROJECT.md "Core Value".)
- Four canonical conversation examples for README, one per tool family:
  1. `forecast_revenue`: "What does next month look like?"
  2. `forecast_demand` + reorder alerts: "Which SKUs need to be reordered in the next 2 weeks?"
  3. `analyze_promotion` / `compare_periods`: "How did Black Friday perform vs last year?"
  4. `compare_scenarios`: "Compare 3 promo scenarios for December."
- Mermaid data-flow diagram should show the Shopify → ForecastResult pipeline explicitly, including where covariates (off by default) hook in — makes the "XReg is optional" story visible without burying it.
- Docker `:bundled` rationale belongs in ARCHITECTURE.md, not just README — merchants on spotty connections are a real use case.
- v0.1.0-rc1 validation checklist is worth writing into the release plan itself (not just CHANGELOG): 4 legs to verify before cutting v0.1.0.
- Trusted Publisher OIDC registration on PyPI is a **manual prerequisite** the planner should call out — cannot be done by code. Must happen before the first tag. Same for GHCR — the package visibility must be flipped to public post-first-push.
- Docker entrypoint dispatch enables a nice demo: `docker run --rm -e SHOPIFY_FORECAST_SHOP=... -e SHOPIFY_FORECAST_ACCESS_TOKEN=... ghcr.io/omnialta/shopify-forecast-mcp:bundled revenue --horizon 30` returns a markdown forecast with zero install.

</specifics>

<deferred>
## Deferred Ideas

- **Shopify Sidekick App Extension** — mentioned in PROJECT.md Active. Separate future phase; docs link forward but do not ship in v0.1.0.
- **Cursor / custom-agent walkthroughs** — consolidated into a generic "MCP server spec" section for v0.1.0. Dedicated per-client walkthroughs deferred until usage data justifies them.
- **Landing site / GitHub Pages** — no separate site for v0.1.0. Repo README is the landing page.
- **SBOM generation, sigstore signing, artifact attestations** — supply-chain hardening is appropriate once the project has users. Not in v0.1.0 scope.
- **Submitting to awesome-mcp or Shopify community directories** — part of a broader v0.2 announce plan, not v0.1.0 repo-only launch.
- **Widening `pyproject.toml` to Python 3.12** — revisit in v0.2 after a TimesFM + torch + 3.12 compatibility spike. Docker base aligns with pyproject in the meantime.
- **`workflow_dispatch` manual trigger for publish workflow** — if v0.1.0-rc1 → v0.1.0 reveals a recovery need, add it in v0.1.1.
- **Docker `HEALTHCHECK`** — stdio-transport MCP servers don't have an obvious endpoint. Revisit if we ship SSE/streamable-http Docker image tags.
- **Reviewed todos (not folded):** None — no todos matched this phase.

</deferred>

---

*Phase: 07-distribution-docs*
*Context gathered: 2026-04-19*
