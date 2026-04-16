---
phase: 02-shopify-client
plan: 04
subsystem: shopify-client
tags: [normalization, timezone, cache, wrappers]
dependency_graph:
  requires: [02-02, 02-03]
  provides: [normalize_order, filter_orders, OrderCache, fetch_orders, fetch_products, fetch_collections]
  affects: [03-timeseries]
tech_stack:
  added: [zoneinfo]
  patterns: [lazy-import-circular-avoidance, atomic-file-write, tdd-red-green]
key_files:
  created:
    - src/shopify_forecast_mcp/core/normalize.py
    - src/shopify_forecast_mcp/core/cache.py
    - tests/test_normalize.py
    - tests/test_cache.py
    - tests/test_fetch_wrappers.py
  modified:
    - src/shopify_forecast_mcp/core/shopify_client.py
decisions:
  - Lazy import of bulk_ops in fetch_orders() to avoid circular dependency
  - Default to paginated path (bulk opt-in via use_bulk=True) for MVP simplicity
  - Cache invalidation deletes all JSON files (no shop-level prefix scheme for hashed keys)
metrics:
  duration: 273s
  completed: 2026-04-16T02:49:00Z
  tasks: 2/2
  tests_added: 39
  total_tests: 66
---

# Phase 02 Plan 04: Order Normalization, Cache & Wrappers Summary

Unified normalization layer producing identical dict shapes from paginated and bulk Shopify sources, with timezone-aware day bucketing via zoneinfo.ZoneInfo, file-based caching with TTL, and high-level fetch_orders/products/collections wrappers on ShopifyClient.

## Task 1: normalize.py and cache.py

**Commits:**
- `fcd3763` test(02-04): add failing tests for normalize and cache modules
- `fd5a36e` feat(02-04): implement normalize.py and cache.py modules

### normalize.py (205 lines)
- `strip_gid()`: Extracts numeric ID from `gid://shopify/Order/1234` format
- `utc_to_local_date()`: Timezone bucketing using `zoneinfo.ZoneInfo` -- correctly handles EDT day-shift cases
- `normalize_line_item()`: Dual-path refund handling:
  - Paginated: uses `_build_refund_map()` from `refundLineItems` detail
  - Bulk: uses `currentQuantity` directly (already refund-adjusted by Shopify)
- `normalize_order()`: Produces consistent 16-key dict from either source
- `filter_orders()`: Excludes `test: true` and `cancelledAt != null` orders
- `_safe_float()`: Malformed monetary amount handling (T-02-11 mitigation)

### cache.py (128 lines)
- `OrderCache` class with SHA-256 hashed keys from `(shop, start_date, end_date, financial_status)`
- TTL enforcement via file mtime comparison
- Atomic writes via `tempfile.mkstemp()` + `os.replace()`
- `invalidate()` clears all cache files in directory

### Key verifications
- Timezone: `2025-06-16T03:30:00Z` in `America/New_York` -> `2025-06-15` (23:30 EDT)
- Timezone: `2025-06-15T23:30:00Z` in `America/New_York` -> `2025-06-15` (19:30 EDT)
- Refund math: Order 1002 paginated: qty=2, refund_qty=1, net_qty=1, refund_amount=$25, net_revenue=$75
- Null product/variant handled as "unknown" / empty strings

## Task 2: ShopifyClient Wrappers

**Commits:**
- `ef900be` test(02-04): add failing tests for fetch_orders/products/collections wrappers
- `ff6690c` feat(02-04): add fetch_orders/products/collections wrappers to ShopifyClient

### fetch_orders()
- Checks `OrderCache` before API call
- Auto-selects paginated (default) or bulk (`use_bulk=True`)
- Normalizes all results via `normalize_order()`
- Filters test/cancelled via `filter_orders()`
- Caches normalized+filtered result

### fetch_products() / fetch_collections()
- Cursor-paginate through respective GraphQL queries
- Return dicts with stripped GIDs

### Circular import resolution
- `bulk_ops.py` imports constants from `shopify_client.py` at module level
- `shopify_client.py` lazy-imports `fetch_orders_bulk` inside `fetch_orders()` method only

## Deviations from Plan

None -- plan executed exactly as written.

## Test Results

66 tests total (39 added in this plan):
- `test_normalize.py`: 25 tests (GID, timezone, line item, order, filter)
- `test_cache.py`: 7 tests (miss, hit, expiry, invalidation, dir creation)
- `test_fetch_wrappers.py`: 7 tests (paginated/bulk selection, normalization, filtering, caching, products, collections)

## Self-Check: PASSED

All 5 created files verified on disk. All 4 commit hashes verified in git log.
