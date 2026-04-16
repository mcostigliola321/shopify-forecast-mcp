---
phase: 02-shopify-client
plan: 01
subsystem: shopify-client
tags: [httpx, graphql, throttle, respx, async]
dependency_graph:
  requires: [shopify_forecast_mcp.config.Settings]
  provides: [ShopifyClient, ShopifyGraphQLError, ShopifyThrottledError, BulkOperationError, PAGINATED_ORDERS_QUERY, BULK_ORDERS_INNER_QUERY, BULK_RUN_MUTATION, BULK_STATUS_QUERY, SHOP_TIMEZONE_QUERY, PRODUCTS_QUERY, COLLECTIONS_QUERY, REQUIRED_SCOPES]
  affects: [tests/conftest.py]
tech_stack:
  added: [httpx, respx]
  patterns: [cost-based-throttle-backoff, respx-side-effect-dispatcher, async-context-manager]
key_files:
  created:
    - src/shopify_forecast_mcp/core/exceptions.py
    - src/shopify_forecast_mcp/core/shopify_client.py
    - tests/conftest.py
    - tests/test_shopify_client.py
  modified: []
decisions:
  - Used class-based dispatchers (ThrottleThenSucceedDispatcher, AlwaysThrottledDispatcher) for stateful throttle test mocks instead of function attributes
  - Return full response dict from _post_graphql (not just data) so callers can inspect extensions.cost
  - BULK_ORDERS_INNER_QUERY uses $QUERY_FILTER placeholder string for callers to substitute
metrics:
  duration: 149s
  completed: 2026-04-16
  tasks_completed: 2
  tasks_total: 2
  test_count: 7
  files_created: 4
---

# Phase 02 Plan 01: ShopifyClient Foundation Summary

Async Shopify GraphQL client with cost-based throttle backoff (deficit/restoreRate + 0.5s, capped at 30s), 7 query constants, 3 custom exceptions, and respx-based test infrastructure with dispatcher routing.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create ShopifyClient class, exceptions, and query constants | 51ef287 | exceptions.py, shopify_client.py |
| 2 | Create test infrastructure and client tests | 7c2f25f | conftest.py, test_shopify_client.py |

## Implementation Details

### ShopifyClient (`src/shopify_forecast_mcp/core/shopify_client.py`)

- Constructor takes `Settings`, builds `httpx.AsyncClient` with `X-Shopify-Access-Token` header
- `_post_graphql(query, variables)` POSTs to `/graphql.json`, parses throttle status, handles THROTTLED errors
- `_handle_throttle()` calculates sleep: `(requestedCost - currentlyAvailable) / restoreRate + 0.5`, capped at 30s, max 3 retries
- `fetch_shop_timezone()` returns and caches the shop IANA timezone string
- Context manager support (`async with ShopifyClient(settings) as client:`)

### Query Constants

7 module-level GraphQL strings: `SHOP_TIMEZONE_QUERY`, `PAGINATED_ORDERS_QUERY`, `BULK_ORDERS_INNER_QUERY`, `BULK_RUN_MUTATION`, `BULK_STATUS_QUERY`, `PRODUCTS_QUERY`, `COLLECTIONS_QUERY`. All use `displayFinancialStatus` and `shopMoney` (never `financialStatus` or `presentmentMoney`).

### Exceptions (`src/shopify_forecast_mcp/core/exceptions.py`)

- `ShopifyGraphQLError` -- stores errors list, joins messages in `__str__`
- `ShopifyThrottledError(ShopifyGraphQLError)` -- raised on max retries exceeded
- `BulkOperationError` -- stores operation_id, status, error_code

### Test Infrastructure (`tests/conftest.py`)

- `shopify_dispatcher()` routes GraphQL operations by query content
- `ThrottleThenSucceedDispatcher` / `AlwaysThrottledDispatcher` for throttle testing
- Fixtures: `shopify_settings`, `shopify_client`, `mock_shopify`
- Constants: `SHOPIFY_GQL_URL`, `MOCK_COST_EXTENSIONS`, `MOCK_THROTTLE_COST`

## Test Results

14 tests pass (7 config from Phase 1 + 7 new client tests):
- `test_client_auth` -- verifies auth header and URL
- `test_post_graphql_success` -- verifies parsed response
- `test_throttle_backoff` -- verifies sleep calculation (5.1s) and retry
- `test_throttle_max_retries` -- verifies ShopifyThrottledError after 4 calls
- `test_graphql_error` -- verifies ShopifyGraphQLError on non-throttle errors
- `test_fetch_shop_timezone` -- verifies timezone extraction
- `test_fetch_shop_timezone_cached` -- verifies single HTTP call on repeated access

## Decisions Made

1. **Class-based throttle dispatchers** instead of function-attribute hacks -- cleaner state tracking for call counts.
2. **Full response dict returned from `_post_graphql`** -- callers (pagination, bulk ops) need `extensions.cost` for monitoring.
3. **`BULK_ORDERS_INNER_QUERY` uses `$QUERY_FILTER` placeholder** -- Plan 02-02 will substitute actual date/status filters before passing to `BULK_RUN_MUTATION`.

## Deviations from Plan

None -- plan executed exactly as written.

## Threat Mitigations Applied

- **T-02-01 (Spoofing):** Token accessed via `SecretStr.get_secret_value()` only in header construction; never logged.
- **T-02-02 (Tampering):** `raise_for_status()` for HTTP errors; explicit `errors` parsing before trusting `data`.
- **T-02-03 (DoS):** Max 3 retries, 30s sleep cap, `ShopifyThrottledError` on exhaustion.
- **T-02-04 (Info Disclosure):** Logger never logs token or full headers; only cost metadata logged at DEBUG level.
