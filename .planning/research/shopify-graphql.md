# Shopify Admin GraphQL API — Research for shopify-forecast-mcp

**Researched:** 2026-04-13
**Confidence:** HIGH (verified against shopify.dev official docs)
**Scope:** Order-history extraction for TimesFM forecasting
**PRD reviewed:** `./shopify-forecast-mcp-PRD.md` (lines 267–332 especially)

---

## TL;DR — Decisions

| Decision | Answer |
|---|---|
| API version | **`2026-04`** (current latest stable). `2026-01` is still stable but pin to `2026-04` for new build. |
| Python client | **Raw `httpx.AsyncClient`** + hand-written bulk-op helper. Do NOT use `shopify-python-api` (sync, session-based, GraphQL support is thin). |
| Auth model | **Custom app** created in Shopify admin → admin API access token (`shpat_…`). Offline token (no expiry) required for bulk ops. |
| Scopes | `read_orders` **+ `read_all_orders`**, `read_products`, `read_inventory`. Drop `read_reports` (not needed). |
| Bulk ops polling | Use **`bulkOperation(id:)`** query (new in `2026-01`), not legacy `currentBulkOperation`. |
| Concurrency | Up to **5 concurrent bulk operations per shop** (new in `2026-01`). |

---

## 1. API Version Calendar (as of April 2026)

Shopify ships quarterly. Currently available:

| Version | Status |
|---|---|
| `unstable` | dev |
| `2026-07` | release candidate |
| **`2026-04`** | **latest stable** ← recommend |
| `2026-01` | stable |
| `2025-10` | stable (oldest supported) |

Versions are supported for 12 months, so `2025-10` sunsets ~October 2026. PRD says `2026-01` — **upgrade to `2026-04`** to maximize supported lifetime. Differences between `2026-01` and `2026-04` are small for orders; no breaking changes in the query we need.

Source: <https://shopify.dev/docs/api/admin-graphql>

---

## 2. Bulk Operations — Lifecycle

### Flow
1. **Start:** `mutation { bulkOperationRunQuery(query: "...") { bulkOperation { id status } userErrors { field message } } }`
2. **Poll:** `query { bulkOperation(id: "gid://shopify/BulkOperation/…") { status objectCount url errorCode } }`
   - **IMPORTANT CHANGE in 2026-01:** use `bulkOperation(id:)` with the explicit ID. `currentBulkOperation` still works but is single-slot-per-shop and incompatible with the new 5-concurrent limit.
3. **Download:** when `status == COMPLETED`, fetch `url` (pre-signed GCS link). **URL expires ~7 days** — download immediately.
4. **Parse:** JSONL, one object per line. Nested connections are flattened: children appear as sibling lines with `__parentId` pointing to parent's `id`. You must reconstruct the tree client-side.

### Status enum
`CREATED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELED`, `EXPIRED`

### Limits
- **Max 5 concurrent bulk queries per shop** (was 1 before 2026-01). Our use case only needs 1–2 so we're safe.
- Hard timeout: **10 days**, after which status flips to `FAILED`.
- Bulk queries **cannot use `first:` / `last:` arguments** on connections inside the bulk query (Shopify auto-paginates). If PRD query has `first:` anywhere inside the bulk body, it will fail — **our PRD query is clean on this** (no `first:` used inside the bulk).

### Auth note
Because operations can run for hours, use an **offline access token**. Online tokens expire in 24h. Custom-app tokens are always offline — good.

Source: <https://shopify.dev/docs/api/usage/bulk-operations/queries>

---

## 3. PRD GraphQL Query — Verification

Verified each field against the `2026-01` schema (equivalent in `2026-04`):

| PRD field | Status | Notes |
|---|---|---|
| `orders(query: "...")` | OK | Search-syntax filter supported |
| `id`, `createdAt` | OK | |
| `totalPriceSet { shopMoney { amount currencyCode } }` | OK | `MoneyBag` type |
| `subtotalPriceSet` | OK | Still present |
| `totalDiscountsSet` | OK | |
| **`financialStatus`** | **BROKEN** | **Removed/replaced by `displayFinancialStatus`**. This is a `String`/enum representing current financial state. Filter syntax `financial_status:paid` in the `query:` arg still works. |
| `discountCodes` | OK | Returns `[String!]!` |
| `tags` | OK | Array of strings (changed from CSV string years ago) |
| `sourceName` | OK | |
| `lineItems { edges { node { ... } } }` | OK | |
| `product { id }` | OK | Note: can be null for deleted products |
| `variant { id sku }` | OK | Can be null for deleted variants — **handle None** |
| `quantity`, `title` | OK | |
| `originalUnitPriceSet { shopMoney { amount } }` | OK | |
| `refunds { refundLineItems { edges { node { ... } } } }` | OK | `refunds` is a plain list (not a connection), no `edges` needed on the outer `refunds` ← PRD already correct |
| `refundLineItems { lineItem { variant { id } } quantity subtotalSet }` | OK | All fields confirmed on `RefundLineItem` |

### Required fixes to PRD query

```graphql
# CHANGE: financialStatus -> displayFinancialStatus
displayFinancialStatus

# ADD (strongly recommended): filter out test/cancelled orders at line-item level
test
cancelledAt
displayFulfillmentStatus
currencyCode          # order's presentment currency
presentmentCurrencyCode

# ADD to lineItems.node for better variant matching
currentQuantity       # quantity after refunds/restocks (Shopify-computed)
```

Also consider `returns` (new return API) — but for historical forecasting, `refunds` remains the source of truth.

### Bulk-op caveat on nested connections

Inside a bulk query you **cannot paginate connections**. `lineItems { edges { node {...} } }` and `refunds { refundLineItems { edges { node {...} } } }` are fine because bulk ops auto-flatten them into parent-linked JSONL rows. But when you parse the JSONL, line items and refund-line-items come as separate lines with `__parentId = <order-id or refund-id>`. Our client must group them. **The PRD does not mention this** — add a `parse_bulk_jsonl()` helper.

---

## 4. Rate Limiting — Reality Check

PRD says "1000 points/sec leaky bucket." **This is Plus-tier only.** Actual limits:

| Plan | Bucket max | Restore rate |
|---|---|---|
| Standard Shopify | 2,000 | 100 pts/sec |
| Advanced | 4,000 | 200 pts/sec |
| **Shopify Plus** | **20,000** | **1,000 pts/sec** |

- Max single query cost: **1,000 points** regardless of plan.
- Good news: **bulk operations don't consume rate-limit budget** the same way — they take minimal points to start and then run server-side. This is the primary reason to use bulk ops for historical backfill.
- Regular (non-bulk) queries for small recent pulls still need throttle handling.

### Reading cost

Every response includes:
```json
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
```

### Throttle response
Error code `THROTTLED` in `errors[].extensions.code` (HTTP 200, not 429 — GraphQL returns errors in body). Retry strategy: read `currentlyAvailable`, sleep `(cost - currentlyAvailable) / restoreRate`, retry. Cap at 3 retries.

Debug header: `Shopify-GraphQL-Cost-Debug: 1` for field-level breakdown.

Source: <https://shopify.dev/docs/api/usage/rate-limits>

---

## 5. Scopes — PRD Has a Gap

PRD lists: `read_orders`, `read_products`, `read_inventory`, `read_reports`.

**Corrections:**
- **ADD `read_all_orders`** — critical. `read_orders` alone only exposes orders from the **last 60 days**. For forecasting we need years of history. Shopify requires `read_all_orders` in addition to `read_orders`. For custom apps this is granted without Shopify review; for public apps it requires approval.
- **DROP `read_reports`** — that's for ShopifyQL / analytics reports, unrelated to orders GraphQL.
- `read_products` — keep (for the products query).
- `read_inventory` — only needed if forecasting inventory levels. Optional for Phase 1.

**Final scope list:** `read_orders`, `read_all_orders`, `read_products` (+`read_inventory` if Phase 2 inventory forecasting).

---

## 6. Custom App Authentication

Recommend custom app (not public app) because this MCP is self-hosted per-user:

1. Merchant: **Settings → Apps and sales channels → Develop apps → Create an app**.
2. Configure Admin API scopes (see above).
3. Install the app → generates **Admin API access token** prefixed `shpat_…`.
4. Token is **offline** (never expires unless revoked) — perfect for bulk ops.
5. Base URL: `https://{shop}.myshopify.com/admin/api/2026-04/graphql.json`
6. Header: `X-Shopify-Access-Token: shpat_…`

No OAuth flow needed. User pastes token into MCP config. For the eventual public-app path (multi-tenant SaaS), wrap OAuth later.

Source: <https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens/generate-app-access-tokens-admin>

---

## 7. Multi-Currency — `shopMoney` vs `presentmentMoney`

Every money field returns a `MoneyBag`:
```graphql
totalPriceSet {
  shopMoney { amount currencyCode }        # store's home currency, FX-converted at order time
  presentmentMoney { amount currencyCode } # what the customer actually paid
}
```

For forecasting revenue:
- **Use `shopMoney`** — gives a single consistent currency across all orders. PRD does this correctly.
- Drop `presentmentMoney` unless you're doing per-market analysis.
- `shopMoney.currencyCode` is constant for a given store, so you can discard it after the first order.

---

## 8. Gotchas / Domain Pitfalls

### Critical
1. **GIDs everywhere.** All `id` fields return `gid://shopify/Order/12345`, not bare integers. Store as-is; parse integer suffix only when needed for display. Never hard-code types in regex — use URL parsing.
2. **Test orders.** `order.test == true` must be filtered OUT for forecasting. Currently PRD does **not** filter. Add `AND NOT test:true` equivalent → actually Shopify query syntax uses `-test:true` or filter client-side (safer).
3. **Draft orders.** `DraftOrder` is a separate type — `orders` query does NOT return them. Good, no action needed.
4. **Cancelled orders.** `cancelledAt != null` → exclude from revenue, include in order-count analysis optionally. PRD filter `financial_status:paid` already excludes most but not all (partially-paid-then-cancelled). Add explicit `cancelledAt` check.
5. **Refund timing mismatch.** Refunds are timestamped independently of the order. For daily revenue series, you can either:
   - (a) **Order-date attribution:** subtract refund from the original order's day → cleaner trend, matches PRD formula `net_revenue = subtotal - sum(refunds)`.
   - (b) Refund-date attribution: negative entry on refund day → more accurate cash flow.
   - PRD uses (a) — fine for forecasting, document the choice.
6. **Deleted products/variants.** `lineItem.variant` can be `null` for products deleted post-order. Don't crash; bucket as "unknown SKU."
7. **`read_all_orders` install trap.** Without it, you'll silently only see 60 days and think the store has barely any history. Validate on first call: count orders > 60 days ago.

### Moderate
8. **Line-item refund resolution.** A refund's `refundLineItems[].lineItem.id` matches the original order's line-item `id`. Match by line-item ID, not by variant ID (multiple lines can share a variant).
9. **Discount allocation.** `subtotalPriceSet` is already post-discount. Don't double-subtract `totalDiscountsSet`.
10. **Tax.** `subtotalPriceSet` is typically pre-tax. For net revenue, tax handling depends on market (US tax-exclusive, EU tax-inclusive). Document that "revenue" means subtotal after discounts, before tax.
11. **Time zones.** `createdAt` is ISO-8601 UTC. Aggregation by "day" must use the shop's time zone (query `shop { ianaTimezone }` once at startup). Otherwise midnight-UTC orders land on the wrong day for the merchant.
12. **`query:` search syntax** uses `created_at:>=2024-01-01` (colon, no quotes around date in this form). Single quotes shown in PRD (`'2024-01-01'`) work but are unnecessary.

### Minor
13. `tags` is returned as `[String!]!` on Order (not comma-delimited anymore — API docs lag here).
14. `discountCodes` is an array of strings (historical codes; empty for orders with automatic discounts).

---

## 9. Python Client Recommendation

### Option comparison

| Library | Async | GraphQL | Maintained | Verdict |
|---|---|---|---|---|
| `shopify-python-api` (official) | ❌ sync | ✅ via `.execute()` | Active but REST-oriented | **Skip.** Sync only, session-based, adds weight for no async benefit. |
| `gql` | ✅ | ✅ | Active | Overkill — schema introspection, transports abstractions we don't need. |
| `basic-shopify-api` (gnikyt) | ✅ | ✅ | Community | Reasonable, but another dep for thin value. |
| **Raw `httpx.AsyncClient`** | ✅ | Manual | — | **Recommended.** ~80 lines of code total. |

### Why raw httpx
- Single POST endpoint `/admin/api/2026-04/graphql.json` with JSON body `{"query": "...", "variables": {...}}`.
- Full control of retry/throttle handling (reads `extensions.cost` directly).
- No sync/async bridge, no extra deps, trivially unit-testable with `respx`.
- Bulk-op polling is 30 lines.

### Sketch
```python
class ShopifyClient:
    def __init__(self, shop: str, token: str, version: str = "2026-04"):
        self.url = f"https://{shop}.myshopify.com/admin/api/{version}/graphql.json"
        self.client = httpx.AsyncClient(
            headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
            timeout=60.0,
        )

    async def execute(self, query: str, variables: dict | None = None) -> dict:
        resp = await self.client.post(self.url, json={"query": query, "variables": variables or {}})
        resp.raise_for_status()
        data = resp.json()
        if errs := data.get("errors"):
            if any(e.get("extensions", {}).get("code") == "THROTTLED" for e in errs):
                await self._sleep_for_throttle(data)
                return await self.execute(query, variables)
            raise ShopifyGraphQLError(errs)
        return data["data"]

    async def bulk_query(self, inner: str) -> AsyncIterator[dict]:
        op = await self.execute(BULK_RUN_MUTATION, {"query": inner})
        op_id = op["bulkOperationRunQuery"]["bulkOperation"]["id"]
        while True:
            status = await self.execute(BULK_STATUS_QUERY, {"id": op_id})
            s = status["bulkOperation"]
            if s["status"] == "COMPLETED": break
            if s["status"] in ("FAILED", "CANCELED", "EXPIRED"):
                raise BulkOpError(s)
            await asyncio.sleep(min(2 ** attempt, 30))
        async with self.client.stream("GET", s["url"]) as r:
            async for line in r.aiter_lines():
                if line: yield json.loads(line)
```

Then a separate `parse_bulk_jsonl()` function groups child records by `__parentId`.

---

## 10. Roadmap Implications

Phases that need to land first:
1. **Auth + client scaffold** — httpx client, cost/throttle handling, error types.
2. **Bulk op lifecycle** — start, poll, download, JSONL parse, parent-id grouping.
3. **Order query (corrected)** — fix `displayFinancialStatus`, add `test`/`cancelledAt`, time-zone fetch.
4. **Shop metadata** — one-time query for `shop { ianaTimezone currencyCode }`.
5. **Then** aggregation → TimesFM.

Research flags for later phases:
- Returns API (`returns` field) vs legacy `refunds` — may matter for stores using new return workflows (2023+).
- Webhook subscriptions for incremental updates post-backfill (out of Phase 1 scope).

---

## Sources

- [Admin GraphQL API overview](https://shopify.dev/docs/api/admin-graphql)
- [Bulk operation queries](https://shopify.dev/docs/api/usage/bulk-operations/queries)
- [Rate limits](https://shopify.dev/docs/api/usage/rate-limits)
- [Order object — 2026-01](https://shopify.dev/docs/api/admin-graphql/2026-01/objects/Order)
- [RefundLineItem — 2026-01](https://shopify.dev/docs/api/admin-graphql/2026-01/objects/RefundLineItem)
- [Custom app access tokens](https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens/generate-app-access-tokens-admin)
- [shopify_python_api (official)](https://github.com/Shopify/shopify_python_api)
- [basic_shopify_api (httpx-based)](https://github.com/gnikyt/basic_shopify_api)
