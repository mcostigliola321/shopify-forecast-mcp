---
phase: 02-shopify-client
plan: 03
subsystem: api
tags: [shopify, bulk-operations, jsonl, graphql, async]

# Dependency graph
requires:
  - phase: 02-shopify-client/02-01
    provides: "ShopifyClient._post_graphql, BULK_RUN_MUTATION, BULK_STATUS_QUERY, BULK_ORDERS_INNER_QUERY, BulkOperationError"
provides:
  - "fetch_orders_bulk() -- full bulk operation lifecycle"
  - "parse_bulk_jsonl() -- JSONL __parentId tree reconstruction"
  - "_poll_bulk_operation() -- exponential backoff polling"
  - "_download_bulk_result() -- GCS download + parse"
affects: [02-shopify-client/02-04, 03-timeseries]

# Tech tracking
tech-stack:
  added: []
  patterns: ["__parentId tree reconstruction from flat JSONL", "exponential backoff polling with max attempts cap"]

key-files:
  created:
    - src/shopify_forecast_mcp/core/bulk_ops.py
    - tests/test_bulk_ops.py
    - tests/fixtures/mock_bulk.jsonl
    - tests/fixtures/mock_bulk_responses.json
  modified: []

key-decisions:
  - "Batch download (not streaming) for JSONL -- sufficient for v1, streaming is future optimization"
  - "Max 1800 poll attempts (~1hr) as safety net against infinite polling (T-02-08)"
  - "$QUERY_FILTER placeholder replacement in BULK_ORDERS_INNER_QUERY for date/status injection"

patterns-established:
  - "JSONL __parentId reconstruction: objects without __parentId are parents, with __parentId are children"
  - "Malformed JSONL lines logged and skipped, orphan children discarded with warning"
  - "Exponential backoff: 2s initial, 1.5x factor, 30s cap"

requirements-completed: [R2.2]

# Metrics
duration: 2min
completed: 2026-04-16
---

# Phase 2 Plan 3: Bulk Operations Summary

**Bulk operation lifecycle with JSONL __parentId tree reconstruction -- start mutation, exponential backoff polling, GCS download, Order->LineItem grouping**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-16T02:39:35Z
- **Completed:** 2026-04-16T02:41:55Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- JSONL fixture with 4 orders and 5 line items linked via __parentId, plus 4 bulk response lifecycle variants
- parse_bulk_jsonl() reconstructs Order->LineItem trees from flat JSONL, with malformed-line and orphan-child safety
- Full async bulk operation lifecycle: start mutation -> poll with exponential backoff -> download from GCS -> parse
- Threat mitigations: malformed JSONL handling (T-02-07), max poll attempts cap (T-02-08)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create JSONL fixture and bulk response fixtures** - `90e6bf2` (test)
2. **Task 2: Implement bulk_ops module with tests (RED)** - `3c23bfc` (test)
3. **Task 2: Implement bulk_ops module with tests (GREEN)** - `637c99c` (feat)

## Files Created/Modified
- `tests/fixtures/mock_bulk.jsonl` - 4 orders, 5 line items with __parentId links for JSONL parsing tests
- `tests/fixtures/mock_bulk_responses.json` - Mock bulk operation lifecycle responses (start/running/completed/failed)
- `src/shopify_forecast_mcp/core/bulk_ops.py` - Bulk operations module: parse_bulk_jsonl, _poll_bulk_operation, _download_bulk_result, fetch_orders_bulk
- `tests/test_bulk_ops.py` - 8 tests covering JSONL parsing, polling, error handling, full lifecycle, query safety

## Decisions Made
- Batch download instead of streaming for JSONL -- sufficient for v1, streaming is a future optimization
- $QUERY_FILTER placeholder replacement approach for injecting date/status filters into the inner query
- Max 1800 poll attempts as safety net (~1 hour at 2s average) -- Shopify also enforces 10-day hard timeout

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Bulk operations module ready for integration with order normalization (Plan 02-04)
- fetch_orders_bulk returns raw order dicts with line_items -- normalization layer will strip GIDs, extract shopMoney amounts, filter test/cancelled orders

---
*Phase: 02-shopify-client*
*Completed: 2026-04-16*
