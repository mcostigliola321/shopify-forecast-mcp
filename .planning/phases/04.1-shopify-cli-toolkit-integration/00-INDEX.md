# Phase 04.1: Shopify CLI Toolkit Integration — Plan Index

**Goal:** Replace httpx-based Shopify client internals with dual-backend architecture (Shopify CLI primary, httpx fallback). Browser OAuth replaces manual token setup. Public API of ShopifyClient unchanged.

**Plans:** 4 plans, 3 waves

## Wave Structure

| Wave | Plans | Autonomous | Description |
|------|-------|------------|-------------|
| 1 | 04.1-01 | yes | Backend protocol + CliBackend + DirectBackend + factory |
| 2 | 04.1-02 | yes | Refactor ShopifyClient + bulk_ops to use backend |
| 3 | 04.1-03, 04.1-04 | yes, yes | Auth CLI + startup (parallel with test updates) |

## Dependency Graph

```
04.1-01 (backend protocol)
    |
    v
04.1-02 (refactor client + bulk_ops)
    |
    +-----+-----+
    v           v
04.1-03     04.1-04
(auth CLI)  (test updates)
```

## File Ownership Matrix

| File | Plan 01 | Plan 02 | Plan 03 | Plan 04 |
|------|---------|---------|---------|---------|
| `core/shopify_backend.py` | CREATE | | | |
| `core/shopify_exec.py` | CREATE | | | |
| `core/exceptions.py` | MODIFY | | | |
| `tests/test_backend.py` | CREATE | | | |
| `core/shopify_client.py` | | MODIFY | | |
| `core/bulk_ops.py` | | MODIFY | | |
| `config.py` | | MODIFY | | |
| `tests/test_shopify_client.py` | | MODIFY | | |
| `cli.py` | | | MODIFY | |
| `mcp/server.py` | | | MODIFY | |
| `.env.example` | | | MODIFY | |
| `tests/test_cli_auth.py` | | | CREATE | |
| `tests/conftest.py` | | | | MODIFY |
| `tests/test_bulk_ops.py` | | | | MODIFY |
| `tests/test_paginated.py` | | | | MODIFY |
| `tests/test_backend_integration.py` | | | | CREATE |

No file overlap between plans in the same wave.

## Decision Coverage

All decisions from CONTEXT.md are covered:

| Decision | Plan | Task | Coverage |
|----------|------|------|----------|
| ShopifyBackend Protocol | 01 | 1 | Full |
| CliBackend implementation | 01 | 1 | Full |
| DirectBackend implementation | 01 | 1 | Full |
| create_backend factory | 01 | 1 | Full |
| execute_graphql in shopify_exec.py | 01 | 2 | Full |
| CLI error exceptions | 01 | 2 | Full |
| Backend unit tests | 01 | 3 | Full |
| ShopifyClient accepts backend | 02 | 1 | Full |
| bulk_ops uses backend | 02 | 1 | Full |
| access_token optional | 02 | 2 | Full |
| Auth CLI subcommand | 03 | 1 | Full |
| Server lifespan update | 03 | 2 | Full |
| .env.example update | 03 | 2 | Full |
| conftest subprocess fixtures | 04 | 1 | Full |
| Existing test adaptation | 04 | 1-2 | Full |
| Integration smoke test | 04 | 2 | Full |
