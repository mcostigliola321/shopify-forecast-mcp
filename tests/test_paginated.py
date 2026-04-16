"""Tests for ShopifyClient.fetch_orders_paginated().

Covers single-page, multi-page, empty results, query string validation,
and raw structure verification using fixture data from
``tests/fixtures/mock_orders_paginated.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from shopify_forecast_mcp.core.shopify_backend import DirectBackend
from shopify_forecast_mcp.core.shopify_client import ShopifyClient
from tests.conftest import MOCK_COST_EXTENSIONS, SHOPIFY_GQL_URL


def _make_client(settings):
    """Create a ShopifyClient with DirectBackend for testing."""
    backend = DirectBackend(
        store=settings.shop,
        access_token=settings.access_token,
        api_version=settings.api_version,
    )
    return ShopifyClient(backend, settings)

# ---------------------------------------------------------------------------
# Load fixture data
# ---------------------------------------------------------------------------

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "mock_orders_paginated.json"
FIXTURE_DATA = json.loads(FIXTURE_PATH.read_text())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_page_response() -> dict:
    """Return a GraphQL response with zero orders and hasNextPage=false."""
    return {
        "data": {
            "orders": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "edges": [],
            }
        },
        "extensions": {"cost": MOCK_COST_EXTENSIONS},
    }


class PaginatedDispatcher:
    """Return page1 on first call, page2 on second call."""

    def __init__(self, pages: list[dict]) -> None:
        self._pages = pages
        self._call_index = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        page = self._pages[self._call_index]
        self._call_index += 1
        return httpx.Response(200, json=page)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="function")
async def test_paginated_single_page(shopify_settings):
    """Single page of results (hasNextPage=false) returns all orders."""
    with respx.mock:
        respx.post(SHOPIFY_GQL_URL).mock(
            side_effect=PaginatedDispatcher([FIXTURE_DATA["page2"]])
        )
        async with _make_client(shopify_settings) as client:
            orders = await client.fetch_orders_paginated("2025-06-15", "2025-06-16")

    assert len(orders) == 2
    assert orders[0]["id"] == "gid://shopify/Order/1004"
    assert orders[1]["id"] == "gid://shopify/Order/1005"


@pytest.mark.asyncio(loop_scope="function")
async def test_paginated_multi_page(shopify_settings):
    """Two pages correctly accumulated into one list of 5 orders."""
    with respx.mock:
        respx.post(SHOPIFY_GQL_URL).mock(
            side_effect=PaginatedDispatcher(
                [FIXTURE_DATA["page1"], FIXTURE_DATA["page2"]]
            )
        )
        async with _make_client(shopify_settings) as client:
            orders = await client.fetch_orders_paginated("2025-06-15", "2025-06-16")

    assert len(orders) == 5
    ids = [o["id"] for o in orders]
    assert ids == [
        "gid://shopify/Order/1001",
        "gid://shopify/Order/1002",
        "gid://shopify/Order/1003",
        "gid://shopify/Order/1004",
        "gid://shopify/Order/1005",
    ]


@pytest.mark.asyncio(loop_scope="function")
async def test_paginated_empty(shopify_settings):
    """Empty result returns empty list."""
    with respx.mock:
        respx.post(SHOPIFY_GQL_URL).mock(
            side_effect=PaginatedDispatcher([_empty_page_response()])
        )
        async with _make_client(shopify_settings) as client:
            orders = await client.fetch_orders_paginated("2025-01-01", "2025-01-02")

    assert orders == []


@pytest.mark.asyncio(loop_scope="function")
async def test_paginated_query_string(shopify_settings):
    """Query string includes date range and financial_status:paid."""
    captured_bodies: list[dict] = []

    def capture_dispatcher(request: httpx.Request) -> httpx.Response:
        captured_bodies.append(json.loads(request.content))
        return httpx.Response(200, json=_empty_page_response())

    with respx.mock:
        respx.post(SHOPIFY_GQL_URL).mock(side_effect=capture_dispatcher)
        async with _make_client(shopify_settings) as client:
            await client.fetch_orders_paginated("2025-01-01", "2025-12-31")

    assert len(captured_bodies) == 1
    variables = captured_bodies[0]["variables"]
    query_filter = variables["query"]
    assert "created_at:>='2025-01-01'" in query_filter
    assert "created_at:<='" in query_filter
    assert "2025-12-31" in query_filter
    assert "financial_status:paid" in query_filter
    assert variables["first"] == 250
    assert variables["after"] is None


@pytest.mark.asyncio(loop_scope="function")
async def test_paginated_returns_raw_structure(shopify_settings):
    """Each returned order dict has expected keys from the GraphQL query."""
    with respx.mock:
        respx.post(SHOPIFY_GQL_URL).mock(
            side_effect=PaginatedDispatcher(
                [FIXTURE_DATA["page1"], FIXTURE_DATA["page2"]]
            )
        )
        async with _make_client(shopify_settings) as client:
            orders = await client.fetch_orders_paginated("2025-06-15", "2025-06-16")

    assert len(orders) == 5
    expected_keys = {
        "id",
        "createdAt",
        "displayFinancialStatus",
        "subtotalPriceSet",
        "currentSubtotalPriceSet",
        "totalDiscountsSet",
        "totalRefundedSet",
        "netPaymentSet",
        "discountCodes",
        "tags",
        "sourceName",
        "test",
        "cancelledAt",
        "lineItems",
        "refunds",
    }
    for order in orders:
        assert expected_keys.issubset(order.keys()), (
            f"Missing keys: {expected_keys - order.keys()}"
        )
        # lineItems has edges structure
        assert "edges" in order["lineItems"]
        assert len(order["lineItems"]["edges"]) > 0
