"""Tests for ShopifyClient wrapper methods: fetch_orders, fetch_products, fetch_collections.

Uses respx mocks for all HTTP calls. Tests verify normalization,
filtering, caching, and strategy selection.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from shopify_forecast_mcp.config import Settings
from shopify_forecast_mcp.core.shopify_client import ShopifyClient

FIXTURES = Path(__file__).parent / "fixtures"
SHOPIFY_GQL_URL = (
    "https://test-store.myshopify.com/admin/api/2026-04/graphql.json"
)


@pytest.fixture()
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.delenv("SHOPIFY_FORECAST_SHOP", raising=False)
    monkeypatch.delenv("SHOPIFY_FORECAST_ACCESS_TOKEN", raising=False)
    return Settings(
        shop="test-store.myshopify.com",
        access_token="shpat_test123",  # type: ignore[arg-type]
        _env_file=None,
    )


def _paginated_fixture() -> dict:
    return json.loads((FIXTURES / "mock_orders_paginated.json").read_text())


def _make_shop_tz_response() -> dict:
    return {
        "data": {
            "shop": {
                "ianaTimezone": "America/New_York",
                "currencyCode": "USD",
                "name": "Test Store",
            }
        },
        "extensions": {"cost": {"requestedQueryCost": 2, "actualQueryCost": 2, "throttleStatus": {"maximumAvailable": 2000.0, "currentlyAvailable": 1998.0, "restoreRate": 100.0}}},
    }


def _make_orders_dispatcher():
    """Return a dispatcher that serves paginated order pages then shop tz."""
    fixture = _paginated_fixture()
    call_count = {"n": 0}

    def dispatch(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        query = body.get("query", "")

        if "shop {" in query or "shop{" in query:
            return httpx.Response(200, json=_make_shop_tz_response())

        if "orders(" in query:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return httpx.Response(200, json=fixture["page1"])
            return httpx.Response(200, json=fixture["page2"])

        return httpx.Response(400, json={"errors": [{"message": "Unmatched"}]})

    return dispatch, call_count


def _make_products_response() -> dict:
    return {
        "data": {
            "products": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/Product/3001",
                            "title": "Classic T-Shirt",
                            "handle": "classic-t-shirt",
                            "productType": "Apparel",
                            "vendor": "TestBrand",
                            "tags": ["summer"],
                            "status": "ACTIVE",
                            "variants": {
                                "edges": [
                                    {
                                        "node": {
                                            "id": "gid://shopify/ProductVariant/4001",
                                            "sku": "TSHIRT-BLK-M",
                                            "title": "Black / Medium",
                                            "price": "50.00",
                                        }
                                    }
                                ]
                            },
                        }
                    }
                ],
            }
        },
        "extensions": {"cost": {"requestedQueryCost": 10, "actualQueryCost": 5, "throttleStatus": {"maximumAvailable": 2000.0, "currentlyAvailable": 1990.0, "restoreRate": 100.0}}},
    }


def _make_collections_response() -> dict:
    return {
        "data": {
            "collections": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/Collection/7001",
                            "title": "Summer Sale",
                            "handle": "summer-sale",
                            "productsCount": 15,
                        }
                    }
                ],
            }
        },
        "extensions": {"cost": {"requestedQueryCost": 5, "actualQueryCost": 3, "throttleStatus": {"maximumAvailable": 2000.0, "currentlyAvailable": 1995.0, "restoreRate": 100.0}}},
    }


# ---------------------------------------------------------------------------
# fetch_orders tests
# ---------------------------------------------------------------------------


class TestFetchOrders:
    @pytest.mark.asyncio
    async def test_fetch_orders_uses_paginated_for_small(self, settings, tmp_path):
        """Default (use_bulk=None) uses paginated path."""
        dispatch, call_count = _make_orders_dispatcher()

        with respx.mock:
            respx.post(SHOPIFY_GQL_URL).mock(side_effect=dispatch)
            client = ShopifyClient(settings, cache_dir=tmp_path)
            orders = await client.fetch_orders("2025-06-15", "2025-06-16")

        # Should have made order pagination calls
        assert call_count["n"] == 2  # page1 + page2
        assert len(orders) > 0

    @pytest.mark.asyncio
    async def test_fetch_orders_uses_bulk_when_forced(self, settings, tmp_path):
        """use_bulk=True routes through bulk operations."""
        bulk_jsonl = (FIXTURES / "mock_bulk.jsonl").read_text()

        call_log = []

        def dispatch(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            query = body.get("query", "")

            if "shop {" in query or "shop{" in query:
                return httpx.Response(200, json=_make_shop_tz_response())

            if "bulkOperationRunQuery" in query:
                call_log.append("bulk_start")
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "bulkOperationRunQuery": {
                                "bulkOperation": {
                                    "id": "gid://shopify/BulkOperation/123456",
                                    "status": "CREATED",
                                },
                                "userErrors": [],
                            }
                        },
                        "extensions": {"cost": {"requestedQueryCost": 10, "actualQueryCost": 10, "throttleStatus": {"maximumAvailable": 2000.0, "currentlyAvailable": 1990.0, "restoreRate": 100.0}}},
                    },
                )

            if "bulkOperation(" in query and "bulkOperationRunQuery" not in query:
                call_log.append("bulk_poll")
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "bulkOperation": {
                                "id": "gid://shopify/BulkOperation/123456",
                                "status": "COMPLETED",
                                "url": "https://storage.googleapis.com/fake-bulk.jsonl",
                                "objectCount": "10",
                                "errorCode": None,
                            }
                        },
                        "extensions": {"cost": {"requestedQueryCost": 2, "actualQueryCost": 2, "throttleStatus": {"maximumAvailable": 2000.0, "currentlyAvailable": 1998.0, "restoreRate": 100.0}}},
                    },
                )

            return httpx.Response(400, json={"errors": [{"message": "Unmatched"}]})

        with respx.mock:
            respx.post(SHOPIFY_GQL_URL).mock(side_effect=dispatch)
            respx.get("https://storage.googleapis.com/fake-bulk.jsonl").mock(
                return_value=httpx.Response(200, text=bulk_jsonl)
            )
            client = ShopifyClient(settings, cache_dir=tmp_path)
            orders = await client.fetch_orders("2025-06-15", "2025-06-16", use_bulk=True)

        assert "bulk_start" in call_log
        assert len(orders) > 0

    @pytest.mark.asyncio
    async def test_fetch_orders_returns_normalized(self, settings, tmp_path):
        """Returns list of normalized order dicts with local_date."""
        dispatch, _ = _make_orders_dispatcher()

        with respx.mock:
            respx.post(SHOPIFY_GQL_URL).mock(side_effect=dispatch)
            client = ShopifyClient(settings, cache_dir=tmp_path)
            orders = await client.fetch_orders("2025-06-15", "2025-06-16")

        # Check normalized shape
        order = orders[0]
        assert "local_date" in order
        assert "line_items" in order
        assert "id" in order
        # ID should be stripped (no gid:// prefix)
        assert not order["id"].startswith("gid://")

    @pytest.mark.asyncio
    async def test_fetch_orders_filters_test_orders(self, settings, tmp_path):
        """test:true orders are not in result."""
        dispatch, _ = _make_orders_dispatcher()

        with respx.mock:
            respx.post(SHOPIFY_GQL_URL).mock(side_effect=dispatch)
            client = ShopifyClient(settings, cache_dir=tmp_path)
            orders = await client.fetch_orders("2025-06-15", "2025-06-16")

        # Order 1005 is test=true in page2
        ids = [o["id"] for o in orders]
        assert "1005" not in ids

    @pytest.mark.asyncio
    async def test_fetch_orders_caches_result(self, settings, tmp_path):
        """Second call returns cached data without HTTP call."""
        dispatch, call_count = _make_orders_dispatcher()

        with respx.mock:
            respx.post(SHOPIFY_GQL_URL).mock(side_effect=dispatch)
            client = ShopifyClient(settings, cache_dir=tmp_path)

            # First call - hits API
            orders1 = await client.fetch_orders("2025-06-15", "2025-06-16")
            first_call_count = call_count["n"]

            # Second call - should use cache
            orders2 = await client.fetch_orders("2025-06-15", "2025-06-16")

        assert call_count["n"] == first_call_count  # No additional API calls
        assert orders1 == orders2


# ---------------------------------------------------------------------------
# fetch_products tests
# ---------------------------------------------------------------------------


class TestFetchProducts:
    @pytest.mark.asyncio
    async def test_fetch_products_returns_list(self, settings, tmp_path):
        """Returns list of product dicts with stripped GIDs."""

        def dispatch(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            query = body.get("query", "")
            if "products(" in query:
                return httpx.Response(200, json=_make_products_response())
            return httpx.Response(400, json={"errors": [{"message": "Unmatched"}]})

        with respx.mock:
            respx.post(SHOPIFY_GQL_URL).mock(side_effect=dispatch)
            client = ShopifyClient(settings, cache_dir=tmp_path)
            products = await client.fetch_products()

        assert len(products) == 1
        p = products[0]
        assert p["id"] == "3001"
        assert p["title"] == "Classic T-Shirt"
        assert len(p["variants"]) == 1
        assert p["variants"][0]["id"] == "4001"


# ---------------------------------------------------------------------------
# fetch_collections tests
# ---------------------------------------------------------------------------


class TestFetchCollections:
    @pytest.mark.asyncio
    async def test_fetch_collections_returns_list(self, settings, tmp_path):
        """Returns list of collection dicts with stripped GIDs."""

        def dispatch(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            query = body.get("query", "")
            if "collections(" in query:
                return httpx.Response(200, json=_make_collections_response())
            return httpx.Response(400, json={"errors": [{"message": "Unmatched"}]})

        with respx.mock:
            respx.post(SHOPIFY_GQL_URL).mock(side_effect=dispatch)
            client = ShopifyClient(settings, cache_dir=tmp_path)
            collections = await client.fetch_collections()

        assert len(collections) == 1
        c = collections[0]
        assert c["id"] == "7001"
        assert c["title"] == "Summer Sale"
