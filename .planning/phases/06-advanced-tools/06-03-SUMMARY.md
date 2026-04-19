---
phase: 06-advanced-tools
plan: 03
subsystem: multi-store
tags: [multi-store, config, store-param, cache-isolation, cli, mcp-tools]

# Dependency graph
requires:
  - phase: 06-advanced-tools
    plan: 01
    provides: "MCP tools pattern, compare_scenarios tool"
  - phase: 06-advanced-tools
    plan: 02
    provides: "Inventory reorder alerts, fetch_inventory method"
provides:
  - "StoreConfig pydantic model for per-store configuration"
  - "Settings.stores list and default_store field for multi-store env config"
  - "AppContext.get_client resolver (by domain or label)"
  - "store param on all 7 MCP tool handlers"
  - "--store flag on all 5 CLI verbs (revenue, demand, promo, compare, scenarios)"
  - "_resolve_store_config CLI helper for store resolution"
  - "Cache isolation per store via existing shop-keyed hash"
affects: [07-distribution]

# Tech tracking
tech-stack:
  added: []
  patterns: ["multi-store via store_clients dict in AppContext", "store param resolution by domain or label", "CLI --store flag with _resolve_store_config helper"]

key-files:
  created:
    - tests/test_multistore.py
  modified:
    - src/shopify_forecast_mcp/config.py
    - src/shopify_forecast_mcp/mcp/server.py
    - src/shopify_forecast_mcp/mcp/tools.py
    - src/shopify_forecast_mcp/cli.py
    - tests/test_config.py

key-decisions:
  - "StoreConfig uses pydantic BaseModel (not dataclass) for JSON env var parsing"
  - "AppContext.get_client returns default client when store=None for backward compat"
  - "CLI uses Settings.model_copy to create per-store settings rather than new Settings instance"
  - "Cache isolation already guaranteed by existing shop-keyed hash -- no cache changes needed"
  - "ForecastEngine remains singleton shared across all stores (per D-13)"

patterns-established:
  - "Multi-store resolution: try domain first, then label via _label_map"
  - "Tool handler pattern: try/except ValueError around get_client for friendly error"

requirements-completed: [R8.6]

# Metrics
duration: 8min
completed: 2026-04-19
---

# Phase 6 Plan 3: Multi-Store Support Summary

**Multi-store config, store-aware AppContext with domain/label resolution, store param on all 7 MCP tools and 5 CLI verbs, cache isolation per store**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-19T11:01:12Z
- **Completed:** 2026-04-19T11:09:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- StoreConfig pydantic model with shop, access_token (SecretStr), and label fields
- Settings extended with stores (list[StoreConfig] from JSON env var) and default_store fields
- AppContext.get_client(store) resolver: None -> default, domain -> direct lookup, label -> _label_map lookup, unknown -> ValueError
- Lifespan creates per-store ShopifyClient instances from settings.stores on startup
- All 7 MCP tool param classes have `store: str | None` field; all handlers use `app.get_client(params.store)` with ValueError -> "Store not found" friendly error
- All 5 CLI verbs (revenue, demand, promo, compare, scenarios) accept `--store` flag with `_resolve_store_config` helper
- Claude Desktop multi-store config example documented in config.py comments (D-14)
- Cache isolation verified: existing OrderCache._cache_key includes shop in hash
- ForecastEngine singleton shared across all stores (D-13)
- 16 new tests in test_multistore.py + 2 new tests in test_config.py
- Full test suite: 316 passed, 1 skipped, 0 failures

## Task Commits

**Note:** Git commit access was blocked during execution. Files are created/modified but need manual commit.

1. **Task 1: StoreConfig, AppContext, cache isolation** (TDD)
   - Files: `src/shopify_forecast_mcp/config.py`, `src/shopify_forecast_mcp/mcp/server.py`, `tests/test_multistore.py`, `tests/test_config.py`
2. **Task 2: Store param on MCP tools and CLI verbs**
   - Files: `src/shopify_forecast_mcp/mcp/tools.py`, `src/shopify_forecast_mcp/cli.py`, `tests/test_multistore.py`

## Files Created/Modified
- `src/shopify_forecast_mcp/config.py` - StoreConfig model, stores/default_store fields, Claude Desktop config example
- `src/shopify_forecast_mcp/mcp/server.py` - AppContext with store_clients dict, _label_map, get_client method; lifespan multi-store initialization
- `src/shopify_forecast_mcp/mcp/tools.py` - store param on all 7 Params classes; all handlers use get_client(params.store)
- `src/shopify_forecast_mcp/cli.py` - _resolve_store_config helper; --store flag on 5 verbs; store resolution in all _run_* functions
- `tests/test_multistore.py` - 16 tests: StoreConfig model, Settings compat, AppContext resolver, cache isolation, MCP tool params, CLI flags, _resolve_store_config
- `tests/test_config.py` - 2 new tests: stores_defaults_empty, default_store_field

## Decisions Made
- StoreConfig uses pydantic BaseModel (not dataclass) because pydantic-settings needs it for JSON env var parsing
- AppContext.get_client returns the default shopify client when store=None, preserving full backward compatibility
- CLI uses Settings.model_copy(update=...) to override shop/access_token for the selected store rather than constructing a new Settings instance
- Cache isolation is already guaranteed by the existing OrderCache._cache_key which includes shop in the SHA-256 hash -- no cache module changes needed
- ForecastEngine remains a singleton shared across all stores per D-13

## Deviations from Plan

None - plan executed exactly as written.

## Threat Mitigations Applied
- **T-06-09 (Information Disclosure):** get_client raises ValueError listing only configured store domains, never tokens
- **T-06-10 (Spoofing):** Only stores in settings.stores or settings.shop are accessible; no dynamic store creation from params
- **T-06-11 (Tampering):** pydantic-settings validates SHOPIFY_FORECAST_STORES JSON structure; malformed JSON fails at startup
- **T-06-12 (Information Disclosure):** SecretStr for all tokens; ValueError message only lists store domains

## Issues Encountered
- Git commands were blocked during execution; all code and tests verified working (316/316 passing) but commits not created

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Multi-store support complete and tested
- All 7 MCP tools accept optional store param
- All 5 CLI verbs accept --store flag
- Single MCP session can forecast different stores without restart
- Ready for Phase 7 distribution

## Self-Check: PENDING

Git commits could not be verified due to blocked git access. File existence verified via test execution.

---
*Phase: 06-advanced-tools*
*Completed: 2026-04-19*
