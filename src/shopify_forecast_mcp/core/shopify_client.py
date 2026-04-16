"""Shopify Admin GraphQL API client with pluggable backend execution.

Delegates all GraphQL execution to a :class:`ShopifyBackend` instance,
decoupling transport (httpx vs CLI) from query logic.

**Required scopes:** ``read_orders``, ``read_all_orders``,
``read_products``, ``read_inventory``.  The ``read_all_orders`` scope
is mandatory -- without it Shopify only returns the last 60 days of
order history.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from shopify_forecast_mcp.config import Settings
from shopify_forecast_mcp.core.cache import OrderCache
from shopify_forecast_mcp.core.normalize import (
    filter_orders,
    normalize_order,
    strip_gid,
)
from shopify_forecast_mcp.core.shopify_backend import ShopifyBackend

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Required Shopify API access scopes
# ---------------------------------------------------------------------------

REQUIRED_SCOPES: tuple[str, ...] = (
    "read_orders",
    "read_all_orders",
    "read_products",
    "read_inventory",
)
"""Required Shopify Admin API access scopes.

``read_all_orders`` is mandatory -- without it the API only returns
orders from the last 60 days, which is insufficient for forecasting.
"""

# ---------------------------------------------------------------------------
# GraphQL query constants
# ---------------------------------------------------------------------------

SHOP_TIMEZONE_QUERY = """\
{
  shop {
    ianaTimezone
    currencyCode
    name
  }
}
"""

PAGINATED_ORDERS_QUERY = """\
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
"""

BULK_ORDERS_INNER_QUERY = """\
{
  orders(query: "$QUERY_FILTER") {
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
"""

BULK_RUN_MUTATION = """\
mutation BulkFetchOrders($query: String!) {
  bulkOperationRunQuery(query: $query) {
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
"""

BULK_STATUS_QUERY = """\
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
"""

PRODUCTS_QUERY = """\
query FetchProducts($after: String) {
  products(first: 250, after: $after) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        title
        handle
        productType
        vendor
        tags
        status
        variants(first: 100) {
          edges {
            node {
              id
              sku
              title
              price
            }
          }
        }
      }
    }
  }
}
"""

COLLECTIONS_QUERY = """\
query FetchCollections($after: String) {
  collections(first: 250, after: $after) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        title
        handle
        productsCount
      }
    }
  }
}
"""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class ShopifyClient:
    """Async Shopify Admin GraphQL client with pluggable backend.

    Usage::

        backend = create_backend(settings)
        async with ShopifyClient(backend, settings) as client:
            tz = await client.fetch_shop_timezone()
    """

    def __init__(
        self,
        backend: ShopifyBackend,
        settings: Settings,
        cache_dir: Path | None = None,
    ) -> None:
        self._backend = backend
        self._settings = settings
        self._shop_tz: str | None = None
        self._cache = OrderCache(
            cache_dir=cache_dir,
            ttl=settings.forecast_cache_ttl,
        )

    # -- Context manager -----------------------------------------------------

    async def __aenter__(self) -> ShopifyClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying backend."""
        await self._backend.close()

    # -- Core GraphQL transport -----------------------------------------------

    async def _post_graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Delegate GraphQL queries to the backend.

        The ``**kwargs`` absorbs the legacy ``_attempt`` keyword so any
        lingering internal callers do not break.
        """
        return await self._backend.post_graphql(query, variables)

    # -- High-level helpers ---------------------------------------------------

    async def fetch_orders_paginated(
        self,
        start_date: str,
        end_date: str,
        financial_status: str = "paid",
    ) -> list[dict]:
        """Fetch orders via cursor pagination. Best for <10k orders.

        Returns raw order dicts from GraphQL (not yet normalized).
        Includes full refund detail via refundLineItems.

        Args:
            start_date: ISO date string (YYYY-MM-DD)
            end_date: ISO date string (YYYY-MM-DD)
            financial_status: Shopify financial status filter (default: "paid")
        """
        query_filter = (
            f"created_at:>='{start_date}' created_at:<='{end_date}' "
            f"financial_status:{financial_status}"
        )

        orders: list[dict] = []
        cursor: str | None = None
        max_pages = 1000  # Safety counter: 1000 pages x 250 = 250k orders (T-02-06)

        for _ in range(max_pages):
            variables = {"first": 250, "after": cursor, "query": query_filter}
            result = await self._post_graphql(PAGINATED_ORDERS_QUERY, variables)
            data = result["data"]["orders"]

            for edge in data["edges"]:
                orders.append(edge["node"])

            if not data["pageInfo"]["hasNextPage"]:
                break
            cursor = data["pageInfo"]["endCursor"]
        else:
            logger.warning(
                "Pagination safety limit reached (%d pages). "
                "Consider using bulk operations.",
                max_pages,
            )

        return orders

    async def fetch_shop_timezone(self) -> str:
        """Return the shop's IANA timezone string (e.g. ``America/New_York``).

        The result is cached after the first call so subsequent calls
        do not hit the API.
        """
        if self._shop_tz is not None:
            return self._shop_tz

        data = await self._post_graphql(SHOP_TIMEZONE_QUERY)
        self._shop_tz = data["data"]["shop"]["ianaTimezone"]
        return self._shop_tz

    async def fetch_orders(
        self,
        start_date: str,
        end_date: str,
        *,
        use_bulk: bool | None = None,
    ) -> list[dict]:
        """Fetch, normalize, filter, and cache orders for a date range.

        Auto-selects paginated (default) or bulk path. Results are
        normalized to a consistent dict shape, test/cancelled orders
        are excluded, and the result is cached for ``forecast_cache_ttl``
        seconds.

        Args:
            start_date: ISO date string (YYYY-MM-DD), inclusive.
            end_date: ISO date string (YYYY-MM-DD), inclusive.
            use_bulk: Force bulk (True) or paginated (False). None defaults
                to paginated (bulk is opt-in for MVP).
        """
        # Check cache first
        cached = self._cache.get(self._settings.shop, start_date, end_date)
        if cached is not None:
            logger.debug("Cache hit for %s..%s (%d orders)", start_date, end_date, len(cached))
            return cached

        # Determine fetch strategy
        if use_bulk is True:
            # Lazy import to avoid circular dependency (bulk_ops imports constants from this module)
            from shopify_forecast_mcp.core.bulk_ops import fetch_orders_bulk

            logger.info("Fetching orders via bulk path for %s..%s", start_date, end_date)
            raw_orders = await fetch_orders_bulk(self, start_date, end_date)
            source = "bulk"
        else:
            logger.info("Fetching orders via paginated path for %s..%s", start_date, end_date)
            raw_orders = await self.fetch_orders_paginated(start_date, end_date)
            source = "paginated"

        # Normalize
        tz_name = await self.fetch_shop_timezone()
        normalized = [
            normalize_order(o, tz_name, source=source) for o in raw_orders
        ]

        # Filter test and cancelled orders
        filtered = filter_orders(normalized)

        # Cache the result
        self._cache.put(self._settings.shop, start_date, end_date, filtered)

        return filtered

    async def fetch_products(self) -> list[dict]:
        """Fetch all products via cursor pagination.

        Returns a list of product dicts with stripped GIDs.
        """
        products: list[dict] = []
        cursor: str | None = None

        for _ in range(100):  # Safety limit
            variables: dict[str, Any] = {"after": cursor}
            result = await self._post_graphql(PRODUCTS_QUERY, variables)
            data = result["data"]["products"]

            for edge in data["edges"]:
                node = edge["node"]
                product = {
                    "id": strip_gid(node["id"]),
                    "title": node.get("title", ""),
                    "handle": node.get("handle", ""),
                    "product_type": node.get("productType", ""),
                    "vendor": node.get("vendor", ""),
                    "tags": node.get("tags", []),
                    "status": node.get("status", ""),
                    "variants": [
                        {
                            "id": strip_gid(v["node"]["id"]),
                            "sku": v["node"].get("sku", ""),
                            "title": v["node"].get("title", ""),
                            "price": v["node"].get("price", "0"),
                        }
                        for v in node.get("variants", {}).get("edges", [])
                    ],
                }
                products.append(product)

            if not data["pageInfo"]["hasNextPage"]:
                break
            cursor = data["pageInfo"]["endCursor"]

        return products

    async def fetch_collections(self) -> list[dict]:
        """Fetch all collections via cursor pagination.

        Returns a list of collection dicts with stripped GIDs.
        """
        collections: list[dict] = []
        cursor: str | None = None

        for _ in range(100):  # Safety limit
            variables: dict[str, Any] = {"after": cursor}
            result = await self._post_graphql(COLLECTIONS_QUERY, variables)
            data = result["data"]["collections"]

            for edge in data["edges"]:
                node = edge["node"]
                collection = {
                    "id": strip_gid(node["id"]),
                    "title": node.get("title", ""),
                    "handle": node.get("handle", ""),
                    "products_count": node.get("productsCount", 0),
                }
                collections.append(collection)

            if not data["pageInfo"]["hasNextPage"]:
                break
            cursor = data["pageInfo"]["endCursor"]

        return collections
