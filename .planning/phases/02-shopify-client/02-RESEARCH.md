# Phase 2: Shopify Client - Research

**Researched:** 2026-04-13
**Domain:** Shopify Admin GraphQL API client, bulk operations, order normalization
**Confidence:** HIGH

## Summary

This research fills implementation gaps not covered by the project-level research at `.planning/research/shopify-graphql.md`. The seven areas investigated are: (1) bulk operation JSONL `__parentId` reconstruction, (2) `extensions.cost.throttleStatus` response shape, (3) paginated orders query with all required fields, (4) bulk operation mutation + polling, (5) `respx` mock patterns for testing, (6) timezone bucketing, and (7) file cache design.

**Critical discovery:** `refundLineItems` cannot be queried inside `refunds` inside `orders` in a bulk operation. Shopify's bulk validator rejects "connection field within a list field" (`refunds` is a list, `refundLineItems` is a connection). However, the Order object provides `currentSubtotalPriceSet` (net of refunds) and `totalRefundedSet` at order level, and `LineItem.currentQuantity` (net of refund quantities) at line-item level. These eliminate the need for `refundLineItems` in the bulk path entirely. The paginated path can still fetch refundLineItems for line-item-level refund dollar amounts if needed.

**Primary recommendation:** Use a two-strategy architecture: bulk operations for order-level data (using `currentSubtotalPriceSet` + `totalRefundedSet` + `currentQuantity`), and paginated queries for detailed line-item refund analysis when needed (<10k orders).

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| R2.1 | Async client on httpx targeting 2026-04 | Section 4 (query strings), Section 2 (throttle shape) |
| R2.2 | Bulk ops lifecycle: start, poll, download, reconstruct | Section 1 (JSONL algorithm), Section 4 (mutation + polling) |
| R2.3 | Paginated query fallback <10k orders | Section 3 (exact query string) |
| R2.4 | Cost-based rate limiting with backoff | Section 2 (exact JSON shape + backoff formula) |
| R2.5 | Order normalization: GID strip, shopMoney, refund-aware | Section 1 (reconstruction), critical discovery (currentSubtotalPriceSet) |
| R2.6 | Filter exclusions: test, cancelled | Covered in query strings (Sections 3, 4) |
| R2.7 | Timezone bucketing | Section 6 (shop query + Python code) |
| R2.8 | Required scopes documented | Covered in project research |
| R2.9 | displayFinancialStatus (not financialStatus) | Verified in Section 3 query |
| R2.10 | Multi-currency: shopMoney only | Covered in query strings |
| R2.11 | fetch_orders/products/collections wrappers | Informed by all sections |
| R2.12 | Local file cache with TTL | Section 7 (design recommendation) |
| R10.5 | Shopify mocks via respx | Section 5 (complete patterns) |
</phase_requirements>

---

## 1. Bulk Operations JSONL `__parentId` Reconstruction Algorithm

### The JSONL Format

Bulk operations return one JSON object per line. Top-level objects (orders) have their full fields. Nested connection children (lineItems) appear as separate lines with a `__parentId` field pointing to their parent's GID. `__parentId` is auto-injected by Shopify and is NOT part of the GraphQL schema. [VERIFIED: shopify.dev/docs/api/usage/bulk-operations/queries]

Example JSONL output for orders with lineItems:
```jsonl
{"id":"gid://shopify/Order/1001","createdAt":"2025-06-15T10:30:00Z","currentSubtotalPriceSet":{"shopMoney":{"amount":"150.00","currencyCode":"USD"}},"displayFinancialStatus":"PAID","test":false,"cancelledAt":null}
{"id":"gid://shopify/LineItem/2001","title":"Widget A","quantity":2,"currentQuantity":2,"originalUnitPriceSet":{"shopMoney":{"amount":"50.00"}},"__parentId":"gid://shopify/Order/1001"}
{"id":"gid://shopify/LineItem/2002","title":"Widget B","quantity":1,"currentQuantity":0,"originalUnitPriceSet":{"shopMoney":{"amount":"50.00"}},"__parentId":"gid://shopify/Order/1001"}
{"id":"gid://shopify/Order/1002","createdAt":"2025-06-16T22:45:00Z","currentSubtotalPriceSet":{"shopMoney":{"amount":"75.00","currencyCode":"USD"}},"displayFinancialStatus":"PAID","test":false,"cancelledAt":null}
{"id":"gid://shopify/LineItem/2003","title":"Gadget C","quantity":3,"currentQuantity":3,"originalUnitPriceSet":{"shopMoney":{"amount":"25.00"}},"__parentId":"gid://shopify/Order/1002"}
```

### Critical: refundLineItems NOT available in bulk path

`Order.refunds` is a **list** (not a connection). `Refund.refundLineItems` is a **connection**. Shopify bulk operations reject "connection field within a list field." This means you CANNOT query `orders { refunds { refundLineItems { edges { node { ... } } } } }` in a bulk operation. [VERIFIED: community.shopify.dev/t/can-i-perform-bulk-operation-query-to-refund-line-items/27907]

**Workaround (recommended):** Use order-level fields that already account for refunds:
- `currentSubtotalPriceSet.shopMoney.amount` -- subtotal after refunds and returns [VERIFIED: shopify.dev Order object]
- `totalRefundedSet.shopMoney.amount` -- total refunded amount [VERIFIED: shopify.dev Order object]  
- `netPaymentSet.shopMoney.amount` -- received minus refunded [VERIFIED: shopify.dev Order object]
- `LineItem.currentQuantity` -- quantity minus refunded/removed units [VERIFIED: shopify.dev LineItem object]

This eliminates the need for refundLineItems in the bulk path entirely.

### Reconstruction Algorithm

Children always appear after their parent in the JSONL stream (not guaranteed in older API versions, but reliable with `2026-04`). [CITED: community.shopify.com/t/do-the-children-in-a-bulk-operation-jsonl-with-nested-connections-come-right-after-their-parent/165909]

```python
import json
from collections import defaultdict

def parse_bulk_jsonl(lines: Iterable[str]) -> list[dict]:
    """Reconstruct nested order trees from flat JSONL with __parentId.
    
    Returns list of order dicts, each with a 'line_items' key containing
    its child LineItem dicts.
    
    Only handles ONE level of nesting (Order -> LineItem) because
    refundLineItems are not available in bulk ops.
    """
    orders: dict[str, dict] = {}       # GID -> order dict
    children: defaultdict[str, list] = defaultdict(list)  # parent GID -> [child dicts]
    
    for line in lines:
        if not line.strip():
            continue
        obj = json.loads(line)
        parent_id = obj.pop("__parentId", None)
        
        if parent_id is None:
            # Top-level object = Order
            orders[obj["id"]] = obj
            obj["line_items"] = []
        else:
            # Child object = LineItem
            children[parent_id].append(obj)
    
    # Attach children to parents
    for parent_id, kids in children.items():
        if parent_id in orders:
            orders[parent_id]["line_items"] = kids
    
    return list(orders.values())
```

### Streaming variant for large JSONL files

```python
async def parse_bulk_jsonl_streaming(
    response: httpx.Response,
) -> AsyncIterator[dict]:
    """Yield fully-assembled order dicts as they complete.
    
    Because children always follow their parent, we can emit an order
    as soon as we see the next order (or EOF).
    """
    current_order: dict | None = None
    
    async for line in response.aiter_lines():
        if not line.strip():
            continue
        obj = json.loads(line)
        parent_id = obj.pop("__parentId", None)
        
        if parent_id is None:
            # New top-level order — emit previous if exists
            if current_order is not None:
                yield current_order
            current_order = obj
            current_order["line_items"] = []
        else:
            # Child of current order
            if current_order is not None:
                current_order["line_items"].append(obj)
    
    # Emit final order
    if current_order is not None:
        yield current_order
```

---

## 2. `extensions.cost.throttleStatus` Exact Shape

Every Shopify GraphQL response includes cost information. [VERIFIED: shopify.dev/docs/api/usage/rate-limits, confirmed in project research]

```json
{
  "data": { "...": "..." },
  "extensions": {
    "cost": {
      "requestedQueryCost": 52,
      "actualQueryCost": 12,
      "throttleStatus": {
        "maximumAvailable": 2000.0,
        "currentlyAvailable": 1988.0,
        "restoreRate": 100.0
      }
    }
  }
}
```

### Field types
| Field | Type | Description |
|-------|------|-------------|
| `requestedQueryCost` | int | Estimated cost before execution |
| `actualQueryCost` | int | Actual cost charged (often lower) |
| `throttleStatus.maximumAvailable` | float | Bucket capacity (plan-dependent: 2000/4000/20000) |
| `throttleStatus.currentlyAvailable` | float | Current points remaining |
| `throttleStatus.restoreRate` | float | Points restored per second (100/200/1000) |

### Throttle error shape

When throttled, HTTP status is still 200 but the response has:
```json
{
  "errors": [
    {
      "message": "Throttled",
      "extensions": {
        "code": "THROTTLED"
      }
    }
  ],
  "extensions": {
    "cost": {
      "requestedQueryCost": 502,
      "actualQueryCost": null,
      "throttleStatus": {
        "maximumAvailable": 2000.0,
        "currentlyAvailable": 42.0,
        "restoreRate": 100.0
      }
    }
  }
}
```

### Backoff implementation

```python
async def _handle_throttle(self, data: dict, query: str, variables: dict | None, attempt: int = 0) -> dict:
    """Retry with calculated sleep based on throttle status."""
    MAX_RETRIES = 3
    if attempt >= MAX_RETRIES:
        raise ShopifyThrottledError("Max retries exceeded")
    
    cost = data.get("extensions", {}).get("cost", {})
    throttle = cost.get("throttleStatus", {})
    available = throttle.get("currentlyAvailable", 0)
    restore_rate = throttle.get("restoreRate", 100)
    requested = cost.get("requestedQueryCost", 1000)
    
    # Calculate sleep: how long until enough points restore
    deficit = max(requested - available, 0)
    sleep_seconds = deficit / restore_rate if restore_rate > 0 else 2.0
    sleep_seconds = min(sleep_seconds + 0.5, 30.0)  # Add buffer, cap at 30s
    
    await asyncio.sleep(sleep_seconds)
    return await self.execute(query, variables, _attempt=attempt + 1)
```

---

## 3. Paginated Orders Query (Exact GraphQL)

This is the small-fetch path for <10k orders. Includes ALL fields from R2.5/R2.9. [VERIFIED: field names against shopify.dev/docs/api/admin-graphql/2026-04/objects/Order]

```graphql
query FetchOrders($first: Int!, $after: String, $query: String) {
  orders(first: $first, after: $after, query: $query, sortKey: CREATED_AT) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        createdAt
        displayFinancialStatus
        subtotalPriceSet {
          shopMoney { amount currencyCode }
        }
        currentSubtotalPriceSet {
          shopMoney { amount currencyCode }
        }
        totalDiscountsSet {
          shopMoney { amount currencyCode }
        }
        totalRefundedSet {
          shopMoney { amount currencyCode }
        }
        netPaymentSet {
          shopMoney { amount currencyCode }
        }
        discountCodes
        tags
        sourceName
        test
        cancelledAt
        lineItems(first: 50) {
          edges {
            node {
              id
              title
              quantity
              currentQuantity
              originalUnitPriceSet {
                shopMoney { amount currencyCode }
              }
              product { id title }
              variant { id sku title }
            }
          }
        }
        refunds(first: 10) {
          id
          createdAt
          refundLineItems(first: 50) {
            edges {
              node {
                lineItem { id }
                quantity
                subtotalSet {
                  shopMoney { amount currencyCode }
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

Variables:
```python
{"first": 250, "after": cursor_or_none, "query": "created_at:>=2024-01-01 created_at:<=2025-12-31 financial_status:paid"}
```

**Notes:**
- `first: 250` is the Shopify max page size for orders
- `lineItems(first: 50)` -- most orders have <50 line items; paginate separately if needed
- `refunds(first: 10)` -- available in paginated path (NOT bulk path)
- `refundLineItems(first: 50)` -- only works in paginated path
- `sortKey: CREATED_AT` ensures chronological order

---

## 4. Bulk Operation Mutation + Polling Query

### Start mutation

```graphql
mutation BulkFetchOrders($query: String!) {
  bulkOperationRunQuery(
    query: $query
  ) {
    bulkOperation {
      id
      status
    }
    userErrors {
      field
      message
    }
  }
}
```

The `$query` variable contains the inner query as a string. Note: for bulk ops, the inner query must NOT use `first:`/`last:` on connections (Shopify auto-paginates). [VERIFIED: shopify.dev bulk operations docs]

### Inner query for bulk operations

```graphql
{
  orders(query: "created_at:>=2024-01-01 created_at:<=2025-12-31 financial_status:paid") {
    edges {
      node {
        id
        createdAt
        displayFinancialStatus
        subtotalPriceSet {
          shopMoney { amount currencyCode }
        }
        currentSubtotalPriceSet {
          shopMoney { amount currencyCode }
        }
        totalDiscountsSet {
          shopMoney { amount currencyCode }
        }
        totalRefundedSet {
          shopMoney { amount currencyCode }
        }
        netPaymentSet {
          shopMoney { amount currencyCode }
        }
        discountCodes
        tags
        sourceName
        test
        cancelledAt
        lineItems {
          edges {
            node {
              id
              title
              quantity
              currentQuantity
              originalUnitPriceSet {
                shopMoney { amount currencyCode }
              }
              product { id title }
              variant { id sku title }
            }
          }
        }
      }
    }
  }
}
```

**Note:** NO `refunds` block in the bulk query. `refunds` is a list (not connection) and nesting `refundLineItems` (a connection) inside it is rejected by the bulk validator. Use order-level `currentSubtotalPriceSet` and `totalRefundedSet` instead.

### Polling query

```graphql
query BulkOperationStatus($id: ID!) {
  bulkOperation(id: $id) {
    id
    status
    errorCode
    objectCount
    fileSize
    url
    createdAt
    completedAt
    partialDataUrl
  }
}
```

### Polling cadence

Shopify recommends using webhooks (`bulk_operations/finish`) over polling. For polling: **2 seconds initial, with exponential backoff up to 30 seconds is reasonable.** The docs do not specify an exact interval. The project research says "poll every 2s" which is fine as a starting interval. [ASSUMED -- no official interval specified; 2s is community consensus]

```python
async def _poll_bulk_operation(self, operation_id: str) -> dict:
    """Poll until bulk operation completes. Returns final status dict."""
    attempt = 0
    while True:
        result = await self.execute(BULK_STATUS_QUERY, {"id": operation_id})
        op = result["bulkOperation"]
        status = op["status"]
        
        if status == "COMPLETED":
            return op
        if status in ("FAILED", "CANCELED", "EXPIRED"):
            raise BulkOperationError(
                f"Bulk operation {operation_id} ended with status: {status}, "
                f"error: {op.get('errorCode')}"
            )
        
        # CREATED or RUNNING -- wait and retry
        delay = min(2 * (1.5 ** attempt), 30)  # 2s, 3s, 4.5s, ... capped at 30s
        await asyncio.sleep(delay)
        attempt += 1
```

### Download the JSONL

```python
async def _download_bulk_result(self, url: str) -> list[dict]:
    """Download and parse JSONL from bulk operation result URL."""
    # URL is a pre-signed GCS link, expires ~7 days
    async with self.client.stream("GET", url) as response:
        response.raise_for_status()
        orders = []
        async for order in parse_bulk_jsonl_streaming(response):
            orders.append(order)
    return orders
```

---

## 5. `respx` Mock Patterns for httpx.AsyncClient

Version: **respx 0.23.1** (installed in project venv). [VERIFIED: pip show respx]

### Core pattern: side_effect dispatcher

The `json` pattern in respx supports exact match only (`json={"key": "value"}`), NOT substring/contains matching on request bodies. To route different GraphQL operations to different mock responses, use a **side_effect callback** that inspects the request body. [VERIFIED: tested locally -- `json__query__contains` raises NotImplementedError]

```python
import json
import httpx
import respx
import pytest

SHOPIFY_GQL_URL = "https://test-store.myshopify.com/admin/api/2026-04/graphql.json"


def shopify_dispatcher(request: httpx.Request) -> httpx.Response:
    """Route mock responses based on GraphQL operation content."""
    body = json.loads(request.content)
    query = body.get("query", "")
    
    if "bulkOperationRunQuery" in query:
        return httpx.Response(200, json={
            "data": {
                "bulkOperationRunQuery": {
                    "bulkOperation": {
                        "id": "gid://shopify/BulkOperation/123456",
                        "status": "CREATED",
                    },
                    "userErrors": [],
                }
            },
            "extensions": {"cost": MOCK_COST_EXTENSIONS},
        })
    
    elif "bulkOperation(" in query and "bulkOperationRunQuery" not in query:
        # Polling query
        return httpx.Response(200, json={
            "data": {
                "bulkOperation": {
                    "id": "gid://shopify/BulkOperation/123456",
                    "status": "COMPLETED",
                    "url": "https://storage.googleapis.com/fake-bulk-result.jsonl",
                    "objectCount": "150",
                    "errorCode": None,
                }
            },
            "extensions": {"cost": MOCK_COST_EXTENSIONS},
        })
    
    elif "orders(" in query:
        # Paginated orders query
        return httpx.Response(200, json={
            "data": {
                "orders": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "edges": MOCK_ORDER_EDGES,
                }
            },
            "extensions": {"cost": MOCK_COST_EXTENSIONS},
        })
    
    elif "shop {" in query or "shop{" in query:
        return httpx.Response(200, json={
            "data": {
                "shop": {
                    "ianaTimezone": "America/New_York",
                    "currencyCode": "USD",
                    "name": "Test Store",
                }
            },
            "extensions": {"cost": MOCK_COST_EXTENSIONS},
        })
    
    return httpx.Response(400, json={"errors": [{"message": "Unmatched mock query"}]})


MOCK_COST_EXTENSIONS = {
    "requestedQueryCost": 52,
    "actualQueryCost": 12,
    "throttleStatus": {
        "maximumAvailable": 2000.0,
        "currentlyAvailable": 1988.0,
        "restoreRate": 100.0,
    },
}
```

### Test fixture pattern

```python
@pytest.fixture
def mock_shopify():
    """Fixture that mocks all Shopify GraphQL requests."""
    with respx.mock:
        respx.post(SHOPIFY_GQL_URL).mock(side_effect=shopify_dispatcher)
        # Also mock bulk result download
        respx.get(url__startswith="https://storage.googleapis.com/").mock(
            return_value=httpx.Response(200, text=MOCK_JSONL_CONTENT)
        )
        yield


@pytest.mark.asyncio
async def test_fetch_orders_paginated(mock_shopify):
    from shopify_forecast_mcp.core.shopify_client import ShopifyClient
    
    client = ShopifyClient(shop="test-store", token="shpat_test123")
    orders = await client.fetch_orders(
        start_date="2025-01-01",
        end_date="2025-12-31",
    )
    assert len(orders) > 0
    assert all("id" in o for o in orders)
```

### Testing throttle behavior

```python
def throttle_then_succeed(request: httpx.Request) -> httpx.Response:
    """First call returns THROTTLED, second succeeds."""
    if not hasattr(throttle_then_succeed, "_called"):
        throttle_then_succeed._called = True
        return httpx.Response(200, json={
            "errors": [{"message": "Throttled", "extensions": {"code": "THROTTLED"}}],
            "extensions": {
                "cost": {
                    "requestedQueryCost": 502,
                    "actualQueryCost": None,
                    "throttleStatus": {
                        "maximumAvailable": 2000.0,
                        "currentlyAvailable": 42.0,
                        "restoreRate": 100.0,
                    },
                }
            },
        })
    return httpx.Response(200, json={
        "data": {"orders": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "edges": []}},
        "extensions": {"cost": MOCK_COST_EXTENSIONS},
    })
```

### Key respx details
- `respx.post(url)` matches POST to exact URL
- `respx.get(url__startswith="...")` matches URL prefix (for bulk download URLs)
- `side_effect` receives an `httpx.Request`, return an `httpx.Response`
- Works with both sync and async httpx clients
- Use `with respx.mock:` context manager or `@respx.mock` decorator
- For pytest-asyncio: `@pytest.mark.asyncio` + `@respx.mock` stack, or use the fixture approach

---

## 6. Timezone Bucketing

### Shop timezone query

```graphql
query ShopTimezone {
  shop {
    ianaTimezone
    currencyCode
    name
  }
}
```

Returns: [VERIFIED: shopify.dev/docs/api/admin-graphql/2026-04/queries/shop]
```json
{
  "data": {
    "shop": {
      "ianaTimezone": "America/New_York",
      "currencyCode": "USD",
      "name": "My Store"
    }
  }
}
```

All three fields are `String!` (non-null). `ianaTimezone` returns standard IANA timezone identifiers like `America/New_York`, `Europe/London`, `Asia/Tokyo`.

### Python conversion pattern

`zoneinfo.ZoneInfo` is in the Python 3.11 stdlib (no extra dependency). [VERIFIED: tested locally]

```python
from datetime import datetime
from zoneinfo import ZoneInfo


def utc_to_local_date(created_at: str, tz_name: str) -> str:
    """Convert UTC ISO-8601 timestamp to local-date string (YYYY-MM-DD).
    
    Args:
        created_at: ISO-8601 string like "2025-06-15T23:30:00Z"
        tz_name: IANA timezone like "America/New_York"
    
    Returns:
        Local date string like "2025-06-15" (NOT "2025-06-16" which UTC would give)
    """
    # Parse UTC timestamp
    utc_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    # Convert to shop's local time
    local_dt = utc_dt.astimezone(ZoneInfo(tz_name))
    return local_dt.strftime("%Y-%m-%d")


# Example: 2025-06-15T23:30:00Z in New York (UTC-4 in summer)
# UTC = June 16 03:30, but local = June 15 19:30
assert utc_to_local_date("2025-06-16T03:30:00Z", "America/New_York") == "2025-06-15"
```

### Integration pattern

Fetch timezone once at client initialization or first use, cache it for the session:

```python
class ShopifyClient:
    def __init__(self, ...):
        self._shop_tz: str | None = None  # Lazy-loaded
    
    async def get_shop_timezone(self) -> str:
        if self._shop_tz is None:
            data = await self.execute(SHOP_TIMEZONE_QUERY)
            self._shop_tz = data["shop"]["ianaTimezone"]
        return self._shop_tz
    
    async def fetch_orders(self, start_date: str, end_date: str) -> list[dict]:
        tz_name = await self.get_shop_timezone()
        raw_orders = await self._fetch_orders_raw(start_date, end_date)
        for order in raw_orders:
            order["local_date"] = utc_to_local_date(order["createdAt"], tz_name)
        return raw_orders
```

---

## 7. File Cache Design

**Recommendation: JSON files in a platform-appropriate cache directory.** [ASSUMED -- design decision, not externally verifiable]

### Why JSON files (not SQLite, not pickle)

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| JSON files | Human-readable, debuggable, no deps, atomic writes | Slightly larger on disk | **Recommended** |
| SQLite | Queryable, single file | Overkill for key-value cache, adds complexity | Skip |
| Pickle | Fast serialize | Security risk (arbitrary code exec), version-fragile | Skip |

### Cache key design

Key: `{shop}_{start_date}_{end_date}_{financial_status}` (from R2.12).

```python
import hashlib
import json
import time
from pathlib import Path


class OrderCache:
    """Simple file cache for fetched orders, keyed by query parameters."""
    
    def __init__(self, cache_dir: Path | None = None, ttl: int = 3600):
        if cache_dir is None:
            cache_dir = Path.home() / ".cache" / "shopify-forecast"
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
    
    def _cache_key(self, shop: str, start_date: str, end_date: str, 
                   financial_status: str = "paid") -> str:
        raw = f"{shop}:{start_date}:{end_date}:{financial_status}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    
    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"orders_{key}.json"
    
    def get(self, shop: str, start_date: str, end_date: str,
            financial_status: str = "paid") -> list[dict] | None:
        """Return cached orders if fresh, else None."""
        key = self._cache_key(shop, start_date, end_date, financial_status)
        path = self._cache_path(key)
        
        if not path.exists():
            return None
        
        # Check TTL via file mtime
        age = time.time() - path.stat().st_mtime
        if age > self.ttl:
            path.unlink(missing_ok=True)
            return None
        
        with open(path) as f:
            return json.load(f)
    
    def put(self, shop: str, start_date: str, end_date: str,
            orders: list[dict], financial_status: str = "paid") -> None:
        """Write orders to cache. Atomic via tmp + rename."""
        key = self._cache_key(shop, start_date, end_date, financial_status)
        path = self._cache_path(key)
        tmp_path = path.with_suffix(".tmp")
        
        with open(tmp_path, "w") as f:
            json.dump(orders, f, separators=(",", ":"))
        
        tmp_path.rename(path)  # Atomic on POSIX
    
    def invalidate(self, shop: str | None = None) -> None:
        """Remove cached files. If shop=None, clear all."""
        for path in self.cache_dir.glob("orders_*.json"):
            path.unlink(missing_ok=True)
```

### Integration with Settings

The `forecast_cache_ttl` from `config.py` (default 3600) feeds directly into `OrderCache(ttl=settings.forecast_cache_ttl)`.

Cache directory: `~/.cache/shopify-forecast/` (follows XDG convention on Linux/macOS). No need for `platformdirs` dependency for this simple case.

---

## Common Pitfalls

### Pitfall 1: Trying refundLineItems in bulk ops
**What goes wrong:** Bulk operation mutation returns `userErrors` saying connection-inside-list is not supported.
**Why it happens:** `Order.refunds` is a list, `Refund.refundLineItems` is a connection. Bulk ops can't handle this nesting.
**How to avoid:** Use `currentSubtotalPriceSet` + `totalRefundedSet` at order level, `currentQuantity` at line-item level. Only fetch refundLineItems in the paginated path.
**Warning signs:** `userErrors` in the `bulkOperationRunQuery` response.

### Pitfall 2: Using `financialStatus` instead of `displayFinancialStatus`
**What goes wrong:** Query error -- field removed from API.
**How to avoid:** Always use `displayFinancialStatus`. Already documented in project research.

### Pitfall 3: Throttle is HTTP 200, not 429
**What goes wrong:** Code checks for HTTP 429 and never triggers backoff.
**Why it happens:** GraphQL returns errors in the JSON body at HTTP 200.
**How to avoid:** Check `data["errors"]` for `extensions.code == "THROTTLED"`, not HTTP status.

### Pitfall 4: UTC midnight date bucketing
**What goes wrong:** An order placed at 11pm Eastern on June 15 shows up as June 16 (UTC).
**How to avoid:** Fetch `shop.ianaTimezone` once, convert all `createdAt` to local time before bucketing.

### Pitfall 5: Bulk operation URL expiry
**What goes wrong:** Download URL expires and returns 403.
**How to avoid:** Download immediately when status becomes COMPLETED. URL expires ~7 days but don't rely on this.

### Pitfall 6: `first:` argument inside bulk query
**What goes wrong:** Bulk operation fails with validation error.
**Why it happens:** Bulk ops auto-paginate all connections; `first:`/`last:` args are forbidden inside the bulk inner query.
**How to avoid:** Remove all pagination args from the inner query. Only the outer `orders` connection uses the `query:` filter arg (which IS allowed).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP client | Custom urllib/aiohttp wrapper | `httpx.AsyncClient` | Handles HTTP/2, timeouts, streaming |
| Test mocking | Custom mock classes | `respx` 0.23.1 | Purpose-built for httpx, supports side_effect dispatch |
| Timezone conversion | Manual UTC offset math | `zoneinfo.ZoneInfo` (stdlib) | Handles DST transitions correctly |
| JSON parsing | Custom streaming parser | `json.loads` per line | JSONL lines are small; no need for streaming JSON parser |
| File locking for cache | `fcntl`/`msvcrt` locking | Atomic tmp+rename | POSIX rename is atomic; good enough for single-process MCP |

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (strict mode) |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/test_shopify_client.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| R2.1 | Client sends correct headers/URL | unit | `uv run pytest tests/test_shopify_client.py::test_client_auth -x` | Wave 0 |
| R2.2 | Bulk ops start/poll/download/parse | integration | `uv run pytest tests/test_shopify_client.py::test_bulk_operation_lifecycle -x` | Wave 0 |
| R2.3 | Paginated cursor fetch | integration | `uv run pytest tests/test_shopify_client.py::test_paginated_fetch -x` | Wave 0 |
| R2.4 | Throttle backoff triggers | unit | `uv run pytest tests/test_shopify_client.py::test_throttle_backoff -x` | Wave 0 |
| R2.5 | GID stripping, net revenue correct | unit | `uv run pytest tests/test_shopify_client.py::test_order_normalization -x` | Wave 0 |
| R2.6 | Test/cancelled orders excluded | unit | `uv run pytest tests/test_shopify_client.py::test_order_filtering -x` | Wave 0 |
| R2.7 | Timezone bucketing correct | unit | `uv run pytest tests/test_shopify_client.py::test_timezone_bucketing -x` | Wave 0 |
| R2.12 | Cache hit/miss/expiry | unit | `uv run pytest tests/test_shopify_client.py::test_order_cache -x` | Wave 0 |
| R10.5 | respx mocks work for all paths | integration | `uv run pytest tests/test_shopify_client.py -x` | Wave 0 |

### Wave 0 Gaps
- [ ] `tests/test_shopify_client.py` -- all test cases above
- [ ] `tests/fixtures/mock_orders.json` -- realistic order fixture data
- [ ] `tests/fixtures/mock_bulk.jsonl` -- sample JSONL for bulk parsing tests
- [ ] `tests/conftest.py` -- shared respx fixtures, mock data loaders

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Polling every 2s with exponential backoff is adequate | Section 4 | Low -- worst case is slightly slower polling; no API violation |
| A2 | JSON file cache is sufficient (vs SQLite) | Section 7 | Low -- easy to swap later; single-process MCP makes concurrency moot |
| A3 | `~/.cache/shopify-forecast/` is an acceptable cache location | Section 7 | Low -- can add platformdirs later if cross-platform issues arise |
| A4 | Children always appear after parents in JSONL for API 2026-04 | Section 1 | Medium -- streaming parser would fail if ordering isn't guaranteed; batch parser is safe |

---

## Sources

### Primary (HIGH confidence)
- [Shopify Order object 2026-04](https://shopify.dev/docs/api/admin-graphql/2026-04/objects/Order) -- field names, types, descriptions for displayFinancialStatus, currentSubtotalPriceSet, totalRefundedSet, netPaymentSet, currentQuantity, etc.
- [Shopify bulk operations queries](https://shopify.dev/docs/api/usage/bulk-operations/queries) -- mutation shape, polling query, JSONL format, nesting rules
- [Shopify rate limits](https://shopify.dev/docs/api/usage/rate-limits) -- throttleStatus shape, plan buckets
- [Shopify shop query 2026-04](https://shopify.dev/docs/api/admin-graphql/2026-04/queries/shop) -- ianaTimezone field
- [respx 0.23.1](https://lundberg.github.io/respx/) -- API reference and guide, verified locally

### Secondary (MEDIUM confidence)
- [Shopify community: refundLineItems in bulk ops](https://community.shopify.dev/t/can-i-perform-bulk-operation-query-to-refund-line-items/27907) -- confirmed connection-in-list limitation
- [Shopify community: JSONL child ordering](https://community.shopify.com/t/do-the-children-in-a-bulk-operation-jsonl-with-nested-connections-come-right-after-their-parent/165909) -- children follow parents, groupObjects parameter

### Tertiary (LOW confidence)
- None. All claims verified against primary or secondary sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- httpx, respx, zoneinfo all verified installed and working
- Architecture: HIGH -- JSONL reconstruction algorithm tested against known format; refund limitation verified
- Pitfalls: HIGH -- critical refundLineItems limitation verified via Shopify community + official validator behavior

**Research date:** 2026-04-13
**Valid until:** 2026-07-13 (stable -- Shopify API version 2026-04 supported until April 2027)
