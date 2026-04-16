# Project State — shopify-forecast-mcp

Living memory file. Updated at every phase transition.

## Current Status

**Phase:** 3 — Time-series & Forecaster (in progress)
**Current Plan:** 3 of 4 complete
**Last completed:** 03-03 ForecastEngine singleton with TimesFM 2.5 (2026-04-16)
**Next action:** Execute 03-04 plan

## Initialization

- **2026-04-13** — Project initialized via `/gsd-new-project` from `shopify-forecast-mcp-PRD.md`
- **Config:** YOLO mode, standard granularity, parallel execution, git-tracked, quality model profile
- **Workflow agents enabled:** research, plan_check, verifier, nyquist_validation
- **Research completed** for 4 domains: TimesFM 2.5, Shopify GraphQL, MCP SDK, packaging
- **5 critical PRD corrections** captured in `.planning/research/SUMMARY.md` — see also REQUIREMENTS.md

## Phase Progress

| Phase | Name | Status |
|---|---|---|
| 1 | Scaffold & Packaging | ✅ Complete (CI green 2026-04-15) |
| 2 | Shopify Client | ✅ Complete (4/4 plans, 2026-04-16) |
| 3 | Time-series & Forecaster | 🔄 In Progress (3/4 plans) |
| 4 | MCP Server & CLI (MVP) | ⏳ Pending |
| 5 | Analytics & Covariates | ⏳ Pending |
| 6 | Advanced Features | ⏳ Pending |
| 7 | Distribution | ⏳ Pending |

## Open Risks

1. **TimesFM commit SHA** must be verified at Phase 1 scaffold time — 2.5 not on PyPI, git dependency required. LOW confidence in pinning.
2. **Apple Silicon `mps`** unsupported by TimesFM 2.5 source — falls back to CPU. Document in SETUP.md.
3. **Phase 6 (advanced features)** is the most droppable — multi-store, compare_scenarios, inventory reorder are optional for v1 launch.

## Key Artifacts

- `.planning/PROJECT.md` — project context
- `.planning/REQUIREMENTS.md` — R1–R12 requirements
- `.planning/ROADMAP.md` — 7-phase roadmap
- `.planning/config.json` — workflow config
- `.planning/research/SUMMARY.md` — research synthesis
- `.planning/research/{timesfm,shopify-graphql,mcp-sdk,packaging}.md` — domain detail
- `shopify-forecast-mcp-PRD.md` — original spec (project root)
