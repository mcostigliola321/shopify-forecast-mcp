"""Shopify Admin GraphQL API client with cost-based throttle handling.

Wraps :class:`httpx.AsyncClient` to provide authenticated access to
Shopify's Admin GraphQL endpoint.  The ``_post_graphql`` helper
automatically parses ``extensions.cost.throttleStatus`` and retries
on ``THROTTLED`` errors with a calculated backoff.

**Required scopes:** ``read_orders``, ``read_all_orders``,
``read_products``, ``read_inventory``.  The ``read_all_orders`` scope
is mandatory -- without it Shopify only returns the last 60 days of
order history.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from shopify_forecast_mcp.config import Settings
from shopify_forecast_mcp.core.exceptions import (
    ShopifyGraphQLError,
    ShopifyThrottledError,
)

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
    """Async Shopify Admin GraphQL client with cost-based throttle handling.

    Usage::

        async with ShopifyClient(settings) as client:
            tz = await client.fetch_shop_timezone()
    """

    _MAX_RETRIES: int = 3

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._shop_tz: str | None = None
        self._client = httpx.AsyncClient(
            base_url=f"https://{settings.shop}/admin/api/{settings.api_version}",
            headers={
                "X-Shopify-Access-Token": settings.access_token.get_secret_value(),
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(60.0, connect=10.0),
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
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # -- Core GraphQL transport -----------------------------------------------

    async def _post_graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        *,
        _attempt: int = 0,
    ) -> dict[str, Any]:
        """POST a GraphQL query and return the parsed JSON response.

        Automatically retries on Shopify THROTTLED errors (HTTP 200 with
        ``errors[].extensions.code == "THROTTLED"``) using a calculated
        backoff based on ``extensions.cost.throttleStatus``.

        Returns the **full** response dict (including ``extensions``) so
        callers can inspect cost metadata.

        Raises:
            ShopifyThrottledError: After ``_MAX_RETRIES`` throttle retries.
            ShopifyGraphQLError: On non-throttle GraphQL errors.
            httpx.HTTPStatusError: On HTTP-level errors (4xx/5xx).
        """
        resp = await self._client.post(
            "/graphql.json",
            json={"query": query, "variables": variables or {}},
        )
        resp.raise_for_status()

        data: dict[str, Any] = resp.json()

        # Log cost metadata when available
        cost = data.get("extensions", {}).get("cost")
        if cost:
            throttle = cost.get("throttleStatus", {})
            logger.debug(
                "GraphQL cost: requested=%s actual=%s available=%.0f/%.0f",
                cost.get("requestedQueryCost"),
                cost.get("actualQueryCost"),
                throttle.get("currentlyAvailable", 0),
                throttle.get("maximumAvailable", 0),
            )

        # Check for GraphQL-level errors
        errors = data.get("errors")
        if errors:
            # Detect THROTTLED -- HTTP 200 with errors[].extensions.code
            is_throttled = any(
                e.get("extensions", {}).get("code") == "THROTTLED"
                for e in errors
            )
            if is_throttled:
                return await self._handle_throttle(data, query, variables, _attempt)
            raise ShopifyGraphQLError(errors)

        return data

    async def _handle_throttle(
        self,
        data: dict[str, Any],
        query: str,
        variables: dict[str, Any] | None,
        attempt: int,
    ) -> dict[str, Any]:
        """Sleep based on throttle status and retry the query.

        Sleep formula: ``(requestedCost - currentlyAvailable) / restoreRate + 0.5``
        capped at 30 seconds.

        Raises:
            ShopifyThrottledError: After ``_MAX_RETRIES`` attempts.
        """
        if attempt >= self._MAX_RETRIES:
            raise ShopifyThrottledError(data.get("errors", []))

        cost = data.get("extensions", {}).get("cost", {})
        throttle = cost.get("throttleStatus", {})
        available = throttle.get("currentlyAvailable", 0)
        restore_rate = throttle.get("restoreRate", 100)
        requested = cost.get("requestedQueryCost", 1000)

        deficit = max(requested - available, 0)
        sleep_seconds = (
            (deficit / restore_rate + 0.5) if restore_rate > 0 else 2.0
        )
        sleep_seconds = min(sleep_seconds, 30.0)

        logger.info(
            "Throttled. Sleeping %.1fs (attempt %d/%d)",
            sleep_seconds,
            attempt + 1,
            self._MAX_RETRIES,
        )

        await asyncio.sleep(sleep_seconds)
        return await self._post_graphql(query, variables, _attempt=attempt + 1)

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
