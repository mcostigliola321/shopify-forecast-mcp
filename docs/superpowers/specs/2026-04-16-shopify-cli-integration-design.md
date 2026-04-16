# Shopify CLI Toolkit Integration Design

**Date:** 2026-04-16
**Status:** Approved
**Scope:** Replace httpx-based Shopify client with Shopify CLI (`shopify store execute`) as the primary query execution backend. Browser-based OAuth replaces manual custom app token setup.

## Problem

The current setup requires users to manually create a Shopify custom app, configure 4 scopes, install the app, copy an access token, and paste it into a `.env` file. This is error-prone (especially the `read_all_orders` scope, which silently caps history to 60 days if missed) and a significant barrier to adoption.

The Shopify AI toolkit (`@shopify/cli` with `shopify store auth` + `shopify store execute`) provides browser-based OAuth and authenticated GraphQL execution out of the box.

## Design

### Auth Flow

**Primary path (interactive):** Shopify CLI OAuth

```bash
shopify store auth --store mystore.myshopify.com \
  --scopes read_orders,read_all_orders,read_products,read_inventory
```

Browser opens, user authorizes, credentials stored by the CLI. No token in `.env`. Our server detects CLI availability and uses `shopify store execute` for all queries.

**Fallback path (headless/CI/Docker):** Direct access token via env var

```bash
SHOPIFY_FORECAST_ACCESS_TOKEN=shpat_xxx
```

When set, bypasses the CLI and uses direct httpx calls (current behavior). Required for environments that can't do browser OAuth.

### Query Execution

New module: `src/shopify_forecast_mcp/core/shopify_exec.py`

```python
async def execute_graphql(
    store: str,
    query: str,
    variables: dict | None = None,
    allow_mutations: bool = False,
) -> dict:
    """Execute GraphQL via Shopify CLI subprocess."""
    cmd = [
        "shopify", "store", "execute",
        "--store", store,
        "--json",
        "--query", query,
    ]
    if variables:
        cmd += ["--variables", json.dumps(variables)]
    if allow_mutations:
        cmd += ["--allow-mutations"]

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise ShopifyCliError(stderr.decode())

    return json.loads(stdout)
```

### Backend Selection

At startup, the system selects one of two backends:

```
If SHOPIFY_FORECAST_ACCESS_TOKEN is set:
    → Use DirectClient (httpx, current behavior)
    → No Shopify CLI needed
    → For CI, Docker, headless environments

Else if `shopify` is on PATH:
    → Use CliClient (shopify store execute)
    → Requires prior `shopify store auth`
    → Default interactive path

Else:
    → Error with clear message:
      "No Shopify credentials found. Either:
       1. Install Shopify CLI and run: shopify store auth --store <store> --scopes read_orders,read_all_orders,read_products,read_inventory
       2. Set SHOPIFY_FORECAST_ACCESS_TOKEN in .env"
```

Both backends implement the same interface so the rest of the codebase doesn't care which is active:

```python
class ShopifyBackend(Protocol):
    async def post_graphql(self, query: str, variables: dict | None = None) -> dict: ...
    async def post_graphql_mutation(self, query: str, variables: dict | None = None) -> dict: ...
    async def download_url(self, url: str) -> bytes: ...
    async def close(self) -> None: ...
```

### Bulk Operations (144k+ orders/year)

The bulk operations flow uses the selected backend for GraphQL but always uses httpx for the JSONL download (the download URL is a signed link, no Shopify auth needed):

1. **Start:** `backend.post_graphql_mutation(BULK_ORDERS_MUTATION)` → operation ID
2. **Poll:** `backend.post_graphql(BULK_POLL_QUERY, {"id": op_id})` every 2s until COMPLETED
3. **Download:** `httpx.AsyncClient().get(url)` → raw JSONL bytes (unauthenticated signed URL)
4. **Parse:** Existing `__parentId` reconstruction (unchanged)

This means `httpx` stays as a dependency but only for the JSONL download step. All authenticated Shopify API calls go through the backend abstraction.

### Config Changes

```python
class Settings(BaseSettings):
    # --- Required ---
    shop: str  # mystore.myshopify.com (required for both paths)

    # --- Optional (headless fallback) ---
    access_token: SecretStr | None = None  # was required, now optional

    # --- Everything else unchanged ---
    api_version: str = "2026-04"
    timesfm_device: str = "cpu"
    timesfm_context_length: int = 1024
    timesfm_horizon: int = 90
    forecast_cache_ttl: int = 3600
    log_level: str = "INFO"
    hf_home: str | None = None
```

### CLI Auth Command

Add a convenience command to the CLI:

```bash
shopify-forecast auth --store mystore.myshopify.com
```

This wraps `shopify store auth --store <store> --scopes read_orders,read_all_orders,read_products,read_inventory` so users don't need to remember the scopes. It also verifies the auth worked by running a quick shop timezone query.

### File Changes

| File | Change |
|------|--------|
| `config.py` | `access_token` becomes `SecretStr \| None = None` |
| `core/shopify_exec.py` | **New.** `execute_graphql()` CLI subprocess wrapper |
| `core/shopify_backend.py` | **New.** `ShopifyBackend` protocol + `CliBackend` + `DirectBackend` implementations + `create_backend()` factory |
| `core/shopify_client.py` | Refactor to accept any `ShopifyBackend`. Remove httpx auth code, keep public API (`fetch_orders`, `fetch_products`, etc.) unchanged |
| `core/bulk_ops.py` | Use `backend.post_graphql_mutation()` for start, `backend.post_graphql()` for polling, keep httpx for JSONL download |
| `core/exceptions.py` | Add `ShopifyCliError`, `ShopifyCliNotFoundError` |
| `mcp/server.py` | Lifespan creates backend via `create_backend(settings)`, passes to ShopifyClient |
| `cli.py` | Add `auth` subcommand wrapping `shopify store auth` |
| `tests/conftest.py` | Add CLI subprocess mock fixtures alongside existing respx fixtures |
| `pyproject.toml` | Keep `httpx` (for JSONL download). No new Python deps. Document Node.js + `@shopify/cli` as a system prerequisite |
| `.env.example` | `ACCESS_TOKEN` moves to optional section |
| `README.md` | Setup becomes: "Install Shopify CLI → `shopify-forecast auth` → done" |

### What Does NOT Change

- `timeseries.py` — untouched
- `forecaster.py` — untouched
- `forecast_result.py` — untouched
- `normalize.py` — untouched
- `cache.py` — untouched
- `mcp/tools.py` — untouched (tools call `ShopifyClient` which abstracts the backend)
- All MCP tool schemas and responses — untouched
- All downstream tests for timeseries, forecaster, normalize — untouched

### Testing Strategy

- **CLI backend tests:** Mock `asyncio.create_subprocess_exec` to simulate `shopify store execute` output. Verify correct command construction, JSON parsing, error handling.
- **Direct backend tests:** Keep existing `respx` mocks (this is the fallback path).
- **Backend factory tests:** Verify correct backend selection based on Settings + CLI availability.
- **Integration test:** If `shopify` is on PATH and a store is configured, run a real shop timezone query as a smoke test (mark `@pytest.mark.integration`).
- **Auth CLI test:** Verify `shopify-forecast auth` constructs the correct `shopify store auth` command with all required scopes.

### Prerequisites for Users

**For interactive use (default):**
- Node.js (LTS) — most developers already have it
- Shopify CLI: `npm install -g @shopify/cli` or use via `npx`
- One-time: `shopify-forecast auth --store <store>` (or `shopify store auth` directly)

**For headless/CI/Docker:**
- No Node.js needed
- Set `SHOPIFY_FORECAST_ACCESS_TOKEN` and `SHOPIFY_FORECAST_SHOP` in environment
- Create a Shopify custom app manually (existing documentation applies)

### Implementation Order

This is a refactor of Phase 2's Shopify client layer. Insert as **Phase 4.5** (between current Phase 4 and Phase 5), or as a standalone phase. The public interface of `ShopifyClient` doesn't change, so Phases 3 and 4 code is unaffected. Only the internal wiring changes.

Estimated plans:
1. Backend protocol + CliBackend + DirectBackend + factory
2. Refactor ShopifyClient to accept backend, update bulk_ops
3. Auth CLI command + startup detection
4. Update tests (swap respx mocks for subprocess mocks on CLI path, keep respx for direct path)

### Risks

1. **Shopify CLI output format changes.** We parse `--json` stdout. If the CLI changes its JSON shape, our parser breaks. Mitigated by pinning to a minimum CLI version and testing against the actual output format.
2. **Subprocess overhead.** Each `shopify store execute` call spawns a Node.js process (~100-200ms overhead). For paginated queries (576 calls for 144k orders), this adds ~60-120s. Bulk operations avoid this — one mutation + a few polls. Recommendation: always use bulk for >1000 orders.
3. **CLI not installed.** Clear error message with install instructions. The direct backend fallback works without CLI.
