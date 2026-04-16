# Phase 2: Shopify Client — Plan Index

**Goal:** Given credentials, fetch a year of normalized orders (refund-aware, test-order-filtered, timezone-bucketed) via paginated OR bulk path.

**Depends on:** Phase 1 (scaffold + config)

## Wave Structure

| Wave | Plan | Objective | Autonomous |
|------|------|-----------|------------|
| 1 | 02-01 | HTTP client + auth + schema constants + test infra | yes |
| 2 | 02-02 | Paginated orders query with cursor pagination | yes |
| 2 | 02-03 | Bulk operations path with JSONL reconstruction | yes |
| 3 | 02-04 | Normalization, timezone bucketing, caching, wrappers | yes |

## Dependency Graph

```
02-01 (HTTP client)
  |         \
  v          v
02-02      02-03
(paginated) (bulk)
  \         /
   v       v
   02-04
   (normalize + cache)
```

## File Ownership (no overlap between same-wave plans)

| Plan | Files Modified |
|------|---------------|
| 02-01 | `src/shopify_forecast_mcp/core/shopify_client.py`, `tests/conftest.py`, `tests/test_shopify_client.py` (initial) |
| 02-02 | `src/shopify_forecast_mcp/core/shopify_client.py` (paginated method), `tests/test_paginated.py`, `tests/fixtures/mock_orders_paginated.json` |
| 02-03 | `src/shopify_forecast_mcp/core/bulk_ops.py`, `tests/test_bulk_ops.py`, `tests/fixtures/mock_bulk.jsonl` |
| 02-04 | `src/shopify_forecast_mcp/core/normalize.py`, `src/shopify_forecast_mcp/core/cache.py`, `src/shopify_forecast_mcp/core/shopify_client.py` (wrappers), `tests/test_normalize.py`, `tests/test_cache.py`, `tests/fixtures/mock_orders_paginated.json` (extend) |

**Note:** 02-02 and 02-03 are in Wave 2 and can run in parallel. 02-02 adds a method to `shopify_client.py`; 02-03 creates a separate `bulk_ops.py` module. This avoids file conflict in Wave 2.

## Requirements Coverage

| Req | Plan | Full |
|-----|------|------|
| R2.1 | 01 | Full |
| R2.2 | 03 | Full |
| R2.3 | 02 | Full |
| R2.4 | 01 | Full |
| R2.5 | 04 | Full |
| R2.6 | 04 | Full |
| R2.7 | 04 | Full |
| R2.8 | 01 | Full |
| R2.9 | 02 | Full |
| R2.10 | 01 | Full |
| R2.11 | 04 | Full |
| R2.12 | 04 | Full |
| R10.5 | 01 | Full |
