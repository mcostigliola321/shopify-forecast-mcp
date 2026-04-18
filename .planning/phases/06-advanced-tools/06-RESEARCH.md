# Phase 6: Advanced Tools - Research

**Researched:** 2026-04-18
**Domain:** What-if scenario planning, inventory-aware reorder, multi-store support
**Confidence:** HIGH

## Summary

Phase 6 adds three advanced capabilities to the existing shopify-forecast-mcp codebase: (1) a `compare_scenarios` MCP tool for what-if forecasting with 2-4 promo scenarios, (2) inventory-aware reorder alerts augmenting `forecast_demand`, and (3) multi-store support with config, cache isolation, and store selection per tool. All three build on well-established patterns from Phases 4-5 and require no new external dependencies beyond the existing stack.

The codebase already has all the foundational pieces: `build_future_covariates` and `forecast_with_covariates` for scenario-based forecasting, `ShopifyClient` with GraphQL query patterns for the new inventory query, `OrderCache` for cache isolation, and pydantic-settings `Settings` for config extension. The primary engineering challenge is the multi-store refactor of `AppContext` and `ShopifyClient` lifecycle management.

**Primary recommendation:** Implement in three sequential plans: (1) compare_scenarios tool + CLI, (2) inventory reorder extension to forecast_demand, (3) multi-store config/client/cache refactor. Each builds on existing patterns with minimal new abstraction.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Side-by-side markdown table with one column per scenario, rows for key metrics (total revenue, peak day, confidence range). Each scenario varies `promo_dates` and `discount_depth`. Reuses XReg pathway from Phase 5.
- **D-02:** 2-4 scenarios per call. Each scenario is a named dict: `{"name": "Aggressive", "promo_start": "...", "promo_end": "...", "discount_depth": 0.3}`.
- **D-03:** Output includes recommendation highlighting best-performing scenario with rationale.
- **D-04:** `COVARIATES_DISCLAIMER` appended to output since scenarios use XReg.
- **D-05:** Extend `forecast_demand` response to include reorder alerts when `read_inventory` scope is available. Not a separate tool.
- **D-06:** Reorder logic: `days_to_stockout = current_inventory / daily_demand_forecast`. Alert when `days_to_stockout < lead_time_days` (default 14).
- **D-07:** Suggested reorder qty = `lead_time_days * daily_demand_forecast * safety_factor`. Safety factor defaults to 1.2.
- **D-08:** New `fetch_inventory` method on ShopifyClient using `inventoryLevels` GraphQL query. Returns `{variant_id, sku, product_id, available, location_id}`.
- **D-09:** Graceful degradation: if `read_inventory` scope not granted, demand forecast works normally without reorder alerts. Log warning once.
- **D-10:** Config shape: `stores` list in Settings, each entry has `shop`, `access_token`, and optional `label`. A `default_store` field selects which store to use when no `store` param is provided.
- **D-11:** Single MCP session supports all configured stores. Each tool accepts optional `store` param.
- **D-12:** Cache isolation per store -- forecast cache keyed by `(store_domain, metric, params_hash)`.
- **D-13:** ForecastEngine singleton is store-agnostic. Only ShopifyClient instances are per-store.
- **D-14:** Claude Desktop config example in docs showing multi-store setup.
- **D-15:** New `shopify-forecast scenarios` CLI verb with `--scenarios` flag accepting JSON or file path. `--json` flag for piped output.
- **D-16:** Multi-store CLI: `--store` flag on all verbs.

### Claude's Discretion
- Exact inventory GraphQL query field selection and pagination strategy
- Multi-store ShopifyClient lifecycle (pool vs on-demand creation)
- Scenario result caching strategy

### Deferred Ideas (OUT OF SCOPE)
None
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| R8.6 | `compare_scenarios` -- what-if forecasting with 2-4 scenarios varying `promo_dates` and `discount_depth` | Existing `build_future_covariates` + `forecast_with_covariates` provide the full XReg pipeline. Tool follows established MCP tool pattern (Pydantic params + @mcp.tool + async handler). |
| Multi-store | Config shape, store selector, cache isolation, per-store ShopifyClient | Extend pydantic-settings `Settings` with `stores` list model. Cache already keys by shop domain. `AppContext` refactored to hold store registry. |
</phase_requirements>

## Standard Stack

### Core (already installed -- no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `mcp` | >=1.27,<2.0 | MCP server framework (FastMCP) | Already in use; tool registration via `@mcp.tool()` [VERIFIED: codebase] |
| `pydantic` | >=2.0 | Tool input schemas, config validation | Already in use for all tool params [VERIFIED: codebase] |
| `pydantic-settings` | >=2.0 | Settings with env prefix | Already in use for `Settings` class [VERIFIED: codebase] |
| `timesfm` | git+SHA | TimesFM 2.5 forecaster | Already pinned; `forecast_with_covariates` exists [VERIFIED: codebase] |
| `numpy` / `pandas` | latest | Array/series manipulation | Already in use throughout [VERIFIED: codebase] |
| `httpx` | >=0.27 | Async HTTP client for Shopify API | Already in use via backend abstraction [VERIFIED: codebase] |
| `holidays` | >=0.40 | Holiday detection for covariates | Already in use by covariates module [VERIFIED: codebase] |

### Supporting (no new installs)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` + `pytest-asyncio` | >=8.0 | Testing | All new tests [VERIFIED: pyproject.toml] |
| `respx` | installed | httpx mock for Shopify queries | Inventory query tests [VERIFIED: codebase] |

**Installation:** No new packages required. Phase 6 uses only existing dependencies.

## Architecture Patterns

### Recommended Project Structure (additions only)
```
src/shopify_forecast_mcp/
├── config.py              # MODIFY: add StoreConfig model + stores list + default_store
├── core/
│   ├── shopify_client.py  # MODIFY: add fetch_inventory(), INVENTORY_QUERY constant
│   ├── cache.py           # MODIFY: include store_domain in cache key
│   └── scenarios.py       # NEW: compare_scenarios logic (run N forecasts, collate, recommend)
├── mcp/
│   ├── server.py          # MODIFY: AppContext gains store registry, store resolver
│   └── tools.py           # MODIFY: add compare_scenarios tool, extend forecast_demand, add store param
└── cli.py                 # MODIFY: add scenarios verb, --store flag on all verbs
```

### Pattern 1: Scenario Runner (compare_scenarios core logic)
**What:** A pure function that takes N scenario dicts, runs each through the existing covariate + forecast pipeline, and returns a comparison table.
**When to use:** `compare_scenarios` tool and CLI verb.
**Example:**
```python
# Source: Pattern derived from existing forecast_demand + covariates pipeline [VERIFIED: codebase]
from dataclasses import dataclass

@dataclass
class ScenarioResult:
    name: str
    total_revenue: float
    peak_day: str
    peak_value: float
    q10_total: float
    q90_total: float
    daily_forecast: list[float]

async def run_scenarios(
    orders: list[dict],
    scenarios: list[dict],  # [{"name": str, "promo_start": str, "promo_end": str, "discount_depth": float}]
    horizon_days: int,
    engine: ForecastEngine,
    country: str = "US",
) -> list[ScenarioResult]:
    """Run each scenario through XReg pipeline and return results."""
    series_dict = orders_to_daily_series(orders, metric="revenue")
    daily = clean_series(series_dict["store"])
    values = daily.values.astype(np.float32)
    last_date = daily.index[-1]
    context_dates = daily.index

    results = []
    for scenario in scenarios:
        planned_promos = [{
            "start": scenario["promo_start"],
            "end": scenario["promo_end"],
            "depth": scenario["discount_depth"],
        }]
        covariates = build_aligned_covariates(
            context_dates, horizon_days, orders,
            country=country, planned_promos=planned_promos,
        )
        point, quantile = engine.forecast_with_covariates(
            values, covariates, horizon=horizon_days,
        )
        # ... build ScenarioResult from point/quantile ...
        results.append(result)
    return results
```

### Pattern 2: Multi-Store Config Model
**What:** A nested pydantic model for store configs within Settings.
**When to use:** Multi-store support.
**Example:**
```python
# Source: Extending existing Settings pattern [VERIFIED: codebase config.py]
from pydantic import BaseModel

class StoreConfig(BaseModel):
    """Configuration for a single Shopify store."""
    shop: str  # e.g., "mystore.myshopify.com"
    access_token: SecretStr | None = None
    label: str | None = None  # friendly name, e.g., "US Store"

class Settings(BaseSettings):
    # ... existing fields ...

    # Multi-store support (Phase 6)
    stores: list[StoreConfig] = Field(default_factory=list)
    default_store: str | None = Field(
        None, description="Store domain or label to use when no store param provided"
    )
```

### Pattern 3: Store Registry in AppContext
**What:** A dict mapping store domain/label to ShopifyClient, created at lifespan startup.
**When to use:** Multi-store request routing.
**Example:**
```python
# Source: Extending existing AppContext/lifespan pattern [VERIFIED: codebase server.py]
@dataclass
class AppContext:
    shopify: ShopifyClient  # default store (backward compat)
    forecaster: ForecastEngine
    store_clients: dict[str, ShopifyClient] = field(default_factory=dict)

    def get_client(self, store: str | None = None) -> ShopifyClient:
        """Resolve store param to a ShopifyClient."""
        if store is None:
            return self.shopify  # default
        # Try by domain first, then by label
        if store in self.store_clients:
            return self.store_clients[store]
        for domain, client in self.store_clients.items():
            if client._settings_label == store:
                return client
        raise ValueError(f"Unknown store: {store}")
```

### Pattern 4: Inventory GraphQL Query
**What:** Query `productVariants` with nested `inventoryItem.inventoryLevels` to get available quantities.
**When to use:** `fetch_inventory` method on ShopifyClient.
**Example:**
```graphql
# Source: Shopify Admin GraphQL docs [CITED: shopify.dev/docs/api/admin-graphql/latest/objects/InventoryLevel]
query FetchInventory($first: Int!, $after: String) {
  productVariants(first: $first, after: $after) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        sku
        product { id title }
        inventoryItem {
          id
          tracked
          inventoryLevels(first: 10) {
            edges {
              node {
                id
                location { id name }
                quantities(names: ["available"]) {
                  name
                  quantity
                }
              }
            }
          }
        }
      }
    }
  }
}
```

### Anti-Patterns to Avoid
- **Separate inventory tool:** D-05 explicitly says reorder is part of `forecast_demand`, not a separate tool. Don't create a standalone `check_inventory` MCP tool.
- **Per-store ForecastEngine:** D-13 says the engine is store-agnostic (TimesFM is zero-shot). Never create per-store engine instances.
- **Breaking backward compat on Settings:** The `shop` + `access_token` fields MUST remain for single-store setups. Multi-store is additive; `stores` list defaults to empty.
- **Eager ShopifyClient creation:** Don't create all store clients at startup if there are many stores. On-demand creation with caching is safer (Claude's discretion area).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Scenario forecasting | Custom forecast loop | Reuse `build_aligned_covariates` + `forecast_with_covariates` | Already handles covariate alignment, horizon stitching, XReg compilation [VERIFIED: codebase] |
| Inventory query | Raw GraphQL string construction | Follow existing `PAGINATED_ORDERS_QUERY` + cursor pagination pattern | Consistent error handling, GID stripping, pagination safety limits [VERIFIED: codebase] |
| Cache key generation | Manual string concat | Extend `OrderCache._cache_key` to include store domain | Already uses SHA-256 hashing, TTL expiry, atomic writes [VERIFIED: codebase] |
| Settings validation | Custom env parsing | Extend pydantic-settings `Settings` with `StoreConfig` model | Automatic env var binding, validation, SecretStr masking [VERIFIED: codebase] |

**Key insight:** Every feature in this phase is an extension of existing patterns. The covariate pipeline, GraphQL client, cache, and config are all proven. The risk is in integration, not in any single component.

## Common Pitfalls

### Pitfall 1: XReg Recompilation Per Scenario
**What goes wrong:** Calling `forecast_with_covariates` triggers `_ensure_xreg_compiled()` which recompiles `ForecastConfig` with `return_backcast=True`. If the first scenario call triggers this and subsequent calls don't, it's fine. But if someone later calls plain `forecast()`, the model remains in XReg mode.
**Why it happens:** The `_xreg_compiled` flag is one-way (True forever after first XReg call).
**How to avoid:** This is actually safe -- TimesFM with `return_backcast=True` works for non-XReg calls too (just ignores backcasts). The existing code already handles this. [VERIFIED: forecaster.py lines 72-90]
**Warning signs:** None expected; this is a non-issue.

### Pitfall 2: Inventory Scope Not Granted
**What goes wrong:** `fetch_inventory` fails because the store's access token doesn't include `read_inventory` scope.
**Why it happens:** Custom apps or CLI auth may not have requested this scope.
**How to avoid:** D-09 requires graceful degradation. Wrap the inventory fetch in try/except, catch Shopify permission errors, log a warning once (use a module-level flag), and return the demand forecast without reorder alerts.
**Warning signs:** GraphQL error response with "access denied" or "scope" in the error message.

### Pitfall 3: Multi-Store Config Env Var Complexity
**What goes wrong:** `pydantic-settings` with `env_prefix` doesn't natively support list-of-objects from env vars. Users can't easily set `SHOPIFY_FORECAST_STORES` as an env var containing a JSON list.
**Why it happens:** Env vars are strings; nested pydantic models from env vars require JSON encoding.
**How to avoid:** Accept `stores` as a JSON string env var (pydantic-settings supports this with `json_parse_fallback=True` or by using `@field_validator`). Also support direct config file. Document clearly in Claude Desktop config example.
**Warning signs:** Users getting validation errors when trying to configure multi-store.

### Pitfall 4: Cache Cross-Contamination Between Stores
**What goes wrong:** Two stores share the same cache key because the cache currently keys on `(shop, start_date, end_date)` and the `shop` field comes from Settings.
**Why it happens:** The `OrderCache._cache_key` already includes `shop` domain, so this is actually safe for the order cache. But forecast caches (if any are added for scenarios) must also include store domain.
**How to avoid:** D-12 is explicit: key by `(store_domain, metric, params_hash)`. Verify that ALL cache paths include store isolation.
**Warning signs:** Getting orders from store A when querying store B.

### Pitfall 5: Shopify Inventory Quantities API Shape
**What goes wrong:** Using `available` field directly instead of the `quantities(names: ["available"])` nested structure.
**Why it happens:** The Shopify inventory API changed; `available` was a direct field in older API versions but is now accessed through the `quantities` field with named quantity types.
**How to avoid:** Use `quantities(names: ["available"])` and extract from the returned array. [CITED: shopify.dev/docs/api/admin-graphql/latest/objects/InventoryLevel]
**Warning signs:** Getting null/missing data for inventory levels.

## Code Examples

### Compare Scenarios Output Format (D-01, D-03)
```python
# Source: Pattern from existing AnalyticsResult.to_markdown() [VERIFIED: codebase]
def format_scenario_comparison(results: list[ScenarioResult], horizon_days: int) -> str:
    """Format scenario results as side-by-side markdown table."""
    lines = [f"# Scenario Comparison ({horizon_days}-day horizon)", ""]

    # Header row
    headers = "| Metric |" + "|".join(f" {r.name} " for r in results) + "|"
    sep = "|---|" + "|".join("---" for _ in results) + "|"
    lines.extend([headers, sep])

    # Metric rows
    lines.append("| Total Revenue |" + "|".join(f" ${r.total_revenue:,.0f} " for r in results) + "|")
    lines.append("| Peak Day |" + "|".join(f" {r.peak_day} " for r in results) + "|")
    lines.append("| Peak Revenue |" + "|".join(f" ${r.peak_value:,.0f} " for r in results) + "|")
    lines.append("| Low Estimate (10%) |" + "|".join(f" ${r.q10_total:,.0f} " for r in results) + "|")
    lines.append("| High Estimate (90%) |" + "|".join(f" ${r.q90_total:,.0f} " for r in results) + "|")

    # Recommendation (D-03)
    best = max(results, key=lambda r: r.total_revenue)
    runner_up = sorted(results, key=lambda r: r.total_revenue, reverse=True)[1]
    lift_pct = ((best.total_revenue - runner_up.total_revenue) / runner_up.total_revenue) * 100
    lines.extend([
        "",
        f"**Recommendation:** Scenario '{best.name}' produces "
        f"{lift_pct:.1f}% more revenue than '{runner_up.name}'.",
    ])

    return "\n".join(lines)
```

### Inventory Fetch with Graceful Degradation (D-08, D-09)
```python
# Source: Following existing fetch_products pattern [VERIFIED: shopify_client.py]
INVENTORY_QUERY = """\
query FetchInventory($first: Int!, $after: String) {
  productVariants(first: $first, after: $after) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        sku
        product { id title }
        inventoryItem {
          id
          tracked
          inventoryLevels(first: 10) {
            edges {
              node {
                location { id name }
                quantities(names: ["available"]) {
                  name
                  quantity
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

async def fetch_inventory(self) -> list[dict]:
    """Fetch inventory levels for all tracked variants."""
    inventory: list[dict] = []
    cursor: str | None = None

    for _ in range(100):  # Safety limit
        variables = {"first": 250, "after": cursor}
        result = await self._post_graphql(INVENTORY_QUERY, variables)
        data = result["data"]["productVariants"]

        for edge in data["edges"]:
            node = edge["node"]
            inv_item = node.get("inventoryItem", {})
            if not inv_item.get("tracked", False):
                continue
            for level_edge in inv_item.get("inventoryLevels", {}).get("edges", []):
                level = level_edge["node"]
                available = 0
                for q in level.get("quantities", []):
                    if q["name"] == "available":
                        available = q["quantity"]
                inventory.append({
                    "variant_id": strip_gid(node["id"]),
                    "sku": node.get("sku", ""),
                    "product_id": strip_gid(node["product"]["id"]),
                    "product_title": node["product"].get("title", ""),
                    "available": available,
                    "location_id": strip_gid(level["location"]["id"]),
                    "location_name": level["location"].get("name", ""),
                })

        if not data["pageInfo"]["hasNextPage"]:
            break
        cursor = data["pageInfo"]["endCursor"]

    return inventory
```

### Reorder Alert Logic (D-06, D-07)
```python
# Source: Pure business logic derived from decisions [VERIFIED: D-06, D-07 in CONTEXT.md]
def compute_reorder_alerts(
    inventory: list[dict],
    forecasts: dict[str, float],  # group_key -> daily demand forecast
    lead_time_days: int = 14,
    safety_factor: float = 1.2,
) -> list[dict]:
    """Compute reorder alerts for products approaching stockout."""
    alerts = []
    for inv in inventory:
        key = inv["product_id"]  # or variant_id/sku depending on group_by
        daily_demand = forecasts.get(key, 0.0)
        if daily_demand <= 0:
            continue

        days_to_stockout = inv["available"] / daily_demand
        if days_to_stockout < lead_time_days:
            suggested_qty = int(
                lead_time_days * daily_demand * safety_factor + 0.5
            )
            alerts.append({
                "product_id": inv["product_id"],
                "product_title": inv.get("product_title", ""),
                "sku": inv["sku"],
                "current_stock": inv["available"],
                "daily_demand": round(daily_demand, 1),
                "days_to_stockout": round(days_to_stockout, 1),
                "suggested_reorder_qty": suggested_qty,
                "location": inv.get("location_name", ""),
            })
    return sorted(alerts, key=lambda a: a["days_to_stockout"])
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `available` direct field on InventoryLevel | `quantities(names: ["available"])` nested accessor | Shopify API 2023-10+ | Must use named quantities API [CITED: shopify.dev] |
| Single-store hardcoded | Multi-store config with store selector | This phase | Config model change, backward-compatible |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | pydantic-settings can parse a JSON string env var for the `stores` list field | Pitfall 3 | Config won't load from env vars; need custom validator or file-only config |
| A2 | `inventoryLevels(first: 10)` is sufficient pagination for most stores (few locations) | Code Examples | Stores with 10+ locations would miss inventory data; need higher limit or full pagination |
| A3 | `productVariants` query supports nested `inventoryItem.inventoryLevels` in API version 2026-04 | Code Examples | Would need separate inventory query approach if nesting is not supported |

## Open Questions

1. **Multi-store env var format**
   - What we know: pydantic-settings supports JSON strings in env vars for complex types
   - What's unclear: Whether the Claude Desktop `claude_desktop_config.json` env section can handle multi-line JSON or if a simpler format is needed
   - Recommendation: Support both JSON env var and direct config; document the simplest path (separate env vars per store with index: `SHOPIFY_FORECAST_STORES_0_SHOP`, etc.)

2. **ShopifyClient pool lifecycle**
   - What we know: D-13 says engine is shared, only clients are per-store. Claude's discretion on lifecycle.
   - What's unclear: Whether to create all clients at startup or on-demand
   - Recommendation: On-demand with dict caching. Create client on first request for a store, cache in AppContext. Avoids startup cost for stores not used in a session.

3. **Scenario caching**
   - What we know: Claude's discretion. Scenarios involve XReg forecasts which are slower than plain forecasts.
   - What's unclear: Whether scenario results should be cached and with what key
   - Recommendation: Don't cache scenario results. They're inherently exploratory (what-if), and caching by promo params would have low hit rate. The underlying order data is already cached.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio (strict mode) |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_scenarios.py tests/test_inventory.py tests/test_multistore.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| R8.6-a | compare_scenarios runs 2-4 scenarios through XReg pipeline | unit | `uv run pytest tests/test_scenarios.py::test_run_scenarios -x` | Wave 0 |
| R8.6-b | Scenario output is side-by-side markdown table | unit | `uv run pytest tests/test_scenarios.py::test_format_comparison -x` | Wave 0 |
| R8.6-c | Recommendation highlights best scenario | unit | `uv run pytest tests/test_scenarios.py::test_recommendation -x` | Wave 0 |
| R8.6-d | COVARIATES_DISCLAIMER appended | unit | `uv run pytest tests/test_scenarios.py::test_disclaimer -x` | Wave 0 |
| INV-01 | fetch_inventory returns variant/location/available | unit | `uv run pytest tests/test_inventory.py::test_fetch_inventory -x` | Wave 0 |
| INV-02 | Reorder alerts computed correctly | unit | `uv run pytest tests/test_inventory.py::test_reorder_alerts -x` | Wave 0 |
| INV-03 | Graceful degradation without read_inventory scope | unit | `uv run pytest tests/test_inventory.py::test_no_inventory_scope -x` | Wave 0 |
| MS-01 | StoreConfig model validates correctly | unit | `uv run pytest tests/test_multistore.py::test_store_config -x` | Wave 0 |
| MS-02 | Store resolver finds by domain and label | unit | `uv run pytest tests/test_multistore.py::test_store_resolver -x` | Wave 0 |
| MS-03 | Cache isolation between stores | unit | `uv run pytest tests/test_multistore.py::test_cache_isolation -x` | Wave 0 |
| MCP-01 | compare_scenarios MCP tool end-to-end | integration | `uv run pytest tests/test_mcp_tools_scenarios.py -x` | Wave 0 |
| CLI-01 | scenarios CLI verb with --json | integration | `uv run pytest tests/test_cli_scenarios.py -x` | Wave 0 |

### Wave 0 Gaps
- [ ] `tests/test_scenarios.py` -- covers R8.6-a through R8.6-d
- [ ] `tests/test_inventory.py` -- covers INV-01 through INV-03
- [ ] `tests/test_multistore.py` -- covers MS-01 through MS-03
- [ ] `tests/test_mcp_tools_scenarios.py` -- MCP tool integration test
- [ ] `tests/test_cli_scenarios.py` -- CLI verb integration test

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_scenarios.py tests/test_inventory.py tests/test_multistore.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A (Shopify token auth unchanged) |
| V3 Session Management | no | N/A |
| V4 Access Control | yes | Store param validation -- prevent accessing unconfigured stores |
| V5 Input Validation | yes | Pydantic BaseModel for all tool params; scenario count 2-4 enforced |
| V6 Cryptography | no | N/A (SecretStr for tokens already in place) |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cross-store data access via `store` param | Information Disclosure | Validate `store` param against configured stores list; reject unknown stores |
| Scenario injection (malformed promo params) | Tampering | Pydantic validation on scenario dicts (date format, discount_depth 0-1 range) |
| Inventory data exposure | Information Disclosure | Respect `read_inventory` scope; don't expose inventory in error messages |

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `config.py`, `server.py`, `tools.py`, `shopify_client.py`, `covariates.py`, `forecaster.py`, `cache.py`, `cli.py` -- all patterns verified by reading source
- Phase 06 CONTEXT.md -- all 16 decisions verified

### Secondary (MEDIUM confidence)
- [Shopify InventoryLevel GraphQL docs](https://shopify.dev/docs/api/admin-graphql/latest/objects/InventoryLevel) -- quantities API shape
- [Shopify inventoryItems query docs](https://shopify.dev/docs/api/admin-graphql/latest/queries/inventoryItems) -- pagination and filters
- [Shopify ProductVariant docs](https://shopify.dev/docs/api/admin-graphql/latest/objects/ProductVariant) -- nested inventoryItem access

### Tertiary (LOW confidence)
- A1 (pydantic-settings JSON env var parsing) -- based on training knowledge, not verified against current pydantic-settings docs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all verified in codebase
- Architecture: HIGH -- all patterns extend existing proven code
- Pitfalls: HIGH -- derived from actual codebase analysis and Shopify API docs
- Multi-store config: MEDIUM -- env var parsing for nested models needs validation at implementation time

**Research date:** 2026-04-18
**Valid until:** 2026-05-18 (stable -- existing stack, no version-sensitive concerns)
