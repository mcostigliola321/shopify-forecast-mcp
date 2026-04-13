# Phase 1: Scaffold & Config — Plan Index

**Goal:** A `uv`-managed package that installs, imports, loads config from env, and runs a trivial smoke test in CI.

**Requirements covered:** R1.1, R1.2, R1.3, R1.4, R1.5, R1.6

**Depends on:** Nothing (this is the first phase).

---

## Plans

| # | Plan | Wave | Depends On | Summary |
|---|---|---|---|---|
| 01 | [Package skeleton](./01-01-PLAN.md) | 1 | — | `pyproject.toml` with hatchling + PEP 639 + Python 3.11 pin + two console scripts; `src/shopify_forecast_mcp/{core,mcp}/` tree with stub `main()` entry points printing "not implemented" to stderr. Includes LICENSE (MIT) and README placeholder so pyproject metadata refs resolve. |
| 02 | [Dependency pinning](./01-02-PLAN.md) | 2 | 01 | Runtime deps (mcp, httpx, pandas, numpy, pydantic-settings, holidays, torch), PyTorch CPU index override for linux/win, **live lookup of TimesFM commit SHA** and git pin, dev extras (pytest/ruff/mypy/respx), `uv sync` resolves cleanly. |
| 03 | [Config module](./01-03-PLAN.md) | 3 | 02 | `src/shopify_forecast_mcp/config.py` with `Settings(BaseSettings)` using `SHOPIFY_FORECAST_*` prefix, `SecretStr` for token, 2026-04 API default, `get_settings()` factory, `.env.example`, TDD-style unit tests including `model_dump` masking. |
| 04 | [Repo hygiene & CI smoke](./01-04-PLAN.md) | 4 | 03 | `.gitignore`, `.python-version`, GH Actions workflow on **Linux + macOS matrix** running `uv sync --frozen` → `uv build` → import + config smoke test → pytest. Ends with a human-verify checkpoint on first green CI run. |

Dependency shape: **strictly sequential (1 → 2 → 3 → 4)**. No parallelism available — each plan builds on the previous plan's output (package → deps → code that imports from deps → hygiene + CI that runs the code). Waves are assigned 1/2/3/4 accordingly.

---

## Key corrections baked in (from research)

These are the research findings this phase encodes so nothing downstream has to re-litigate them:

1. **Source layout** — `src/shopify_forecast_mcp/{core,mcp,cli.py}` single distribution. PRD's `src/core/` + `src/mcp/` top-level is WRONG (collides with installed `mcp` SDK). [Plan 01]
2. **TimesFM git pin** — TimesFM 2.5 is NOT on PyPI. Must install via `git+https://github.com/google-research/timesfm.git@<SHA>`. SHA looked up live in Plan 02 Task 1 (research confidence LOW — verify live). [Plan 02]
3. **API version** — `2026-04`, not PRD's `2026-01`. [Plan 03]
4. **No `mps` device** — TimesFM 2.5 source has no MPS branch; Apple Silicon falls back to CPU. Encoded in `.env.example` comment. [Plan 03]
5. **Logging to stderr** — R7.8 discipline: stdio transport uses stdout for JSON-RPC. Both stub `main()` functions in Plan 01 already print to stderr so Phase 4 inherits the pattern.

---

## Phase success criteria (from ROADMAP.md)

- [ ] `uv sync` resolves cleanly on Linux + macOS; TimesFM installs from git pin
- [ ] `uv run python -c "from shopify_forecast_mcp.config import Settings; Settings()"` loads `.env` or errors with named missing vars
- [ ] `uv build` produces wheel + sdist
- [ ] CI green on push

Phase 1 is complete when all four boxes are checked — the CI run from Plan 04 proves boxes 1, 3, and 4; the pytest suite from Plan 03 proves box 2.

---

## What Phase 1 deliberately does NOT do

- **No TimesFM model load.** Phase 3 owns that. Plan 02 only pins the dep.
- **No real MCP server.** Plan 01 ships a stub `main()` that prints "not implemented". Phase 4 writes the FastMCP server.
- **No Shopify code.** Phase 2 owns the HTTP client.
- **No real CLI logic.** Plan 01 stubs `shopify-forecast` to print "not implemented". Phase 4 wires the subcommands.
- **No `tests/` fixture data.** Phase 3 creates the 1yr fixture orders.
- **No Docker image.** Phase 7 owns distribution.

---

## Next step

Run `/gsd-execute-phase 01-scaffold-config` to execute Plans 01 → 02 → 03 → 04 in sequence.
