"""Shared pytest fixtures for shopify-forecast-mcp test suite.

Provides mock Shopify GraphQL infrastructure via ``respx`` and
reusable ``Settings`` / ``ShopifyClient`` factory fixtures.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from shopify_forecast_mcp.config import Settings
from shopify_forecast_mcp.core.shopify_backend import DirectBackend
from shopify_forecast_mcp.core.shopify_client import ShopifyClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SHOPIFY_GQL_URL = (
    "https://test-store.myshopify.com/admin/api/2026-04/graphql.json"
)

MOCK_COST_EXTENSIONS: dict = {
    "requestedQueryCost": 52,
    "actualQueryCost": 12,
    "throttleStatus": {
        "maximumAvailable": 2000.0,
        "currentlyAvailable": 1988.0,
        "restoreRate": 100.0,
    },
}

MOCK_THROTTLE_COST: dict = {
    "requestedQueryCost": 502,
    "actualQueryCost": None,
    "throttleStatus": {
        "maximumAvailable": 2000.0,
        "currentlyAvailable": 42.0,
        "restoreRate": 100.0,
    },
}


# ---------------------------------------------------------------------------
# Dispatcher: routes GraphQL operations to correct mock responses
# ---------------------------------------------------------------------------


def shopify_dispatcher(request: httpx.Request) -> httpx.Response:
    """Route mock responses based on GraphQL operation content."""
    body = json.loads(request.content)
    query = body.get("query", "")

    if "bulkOperationRunQuery" in query:
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
                "extensions": {"cost": MOCK_COST_EXTENSIONS},
            },
        )

    if "bulkOperation(" in query and "bulkOperationRunQuery" not in query:
        return httpx.Response(
            200,
            json={
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
            },
        )

    if "orders(" in query:
        return httpx.Response(
            200,
            json={
                "data": {
                    "orders": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "edges": [],
                    }
                },
                "extensions": {"cost": MOCK_COST_EXTENSIONS},
            },
        )

    if "shop {" in query or "shop{" in query:
        return httpx.Response(
            200,
            json={
                "data": {
                    "shop": {
                        "ianaTimezone": "America/New_York",
                        "currencyCode": "USD",
                        "name": "Test Store",
                    }
                },
                "extensions": {"cost": MOCK_COST_EXTENSIONS},
            },
        )

    return httpx.Response(
        400, json={"errors": [{"message": "Unmatched mock query"}]}
    )


# ---------------------------------------------------------------------------
# Throttle dispatchers
# ---------------------------------------------------------------------------


class ThrottleThenSucceedDispatcher:
    """Returns THROTTLED on first call, success on subsequent calls."""

    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1
        if self.call_count == 1:
            return httpx.Response(
                200,
                json={
                    "errors": [
                        {
                            "message": "Throttled",
                            "extensions": {"code": "THROTTLED"},
                        }
                    ],
                    "extensions": {"cost": MOCK_THROTTLE_COST},
                },
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "shop": {
                        "ianaTimezone": "America/New_York",
                        "currencyCode": "USD",
                        "name": "Test Store",
                    }
                },
                "extensions": {"cost": MOCK_COST_EXTENSIONS},
            },
        )


class AlwaysThrottledDispatcher:
    """Always returns THROTTLED -- for max-retry testing."""

    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1
        return httpx.Response(
            200,
            json={
                "errors": [
                    {
                        "message": "Throttled",
                        "extensions": {"code": "THROTTLED"},
                    }
                ],
                "extensions": {"cost": MOCK_THROTTLE_COST},
            },
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def shopify_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Return a Settings instance configured for the test mock store."""
    monkeypatch.delenv("SHOPIFY_FORECAST_SHOP", raising=False)
    monkeypatch.delenv("SHOPIFY_FORECAST_ACCESS_TOKEN", raising=False)
    return Settings(
        shop="test-store.myshopify.com",
        access_token="shpat_test123",  # type: ignore[arg-type]
        _env_file=None,
    )


@pytest.fixture()
def shopify_client(shopify_settings: Settings) -> ShopifyClient:
    """Return a ShopifyClient wired to the test mock store."""
    backend = DirectBackend(
        store=shopify_settings.shop,
        access_token=shopify_settings.access_token,
        api_version=shopify_settings.api_version,
    )
    return ShopifyClient(backend, shopify_settings)


@pytest.fixture()
def mock_shopify():
    """Mock all Shopify GraphQL requests via the standard dispatcher."""
    with respx.mock:
        respx.post(SHOPIFY_GQL_URL).mock(side_effect=shopify_dispatcher)
        yield


# ---------------------------------------------------------------------------
# Normalized orders fixture for timeseries tests
# ---------------------------------------------------------------------------


def _make_order(
    order_id: str,
    created_at: str,
    local_date: str,
    line_items: list[dict],
) -> dict:
    """Helper to build a normalized order dict with sensible defaults."""
    return {
        "id": order_id,
        "created_at": created_at,
        "local_date": local_date,
        "financial_status": "PAID",
        "subtotal": sum(li["gross_revenue"] for li in line_items),
        "current_subtotal": sum(li["net_revenue"] for li in line_items),
        "total_discounts": 0.0,
        "total_refunded": sum(li["refund_amount"] for li in line_items),
        "net_payment": sum(li["net_revenue"] for li in line_items),
        "currency": "USD",
        "discount_codes": [],
        "tags": [],
        "source_name": "",
        "test": False,
        "cancelled_at": None,
        "line_items": line_items,
    }


def _make_line_item(
    li_id: str,
    product_id: str,
    sku: str,
    quantity: int,
    unit_price: float,
    refund_quantity: int = 0,
    refund_amount: float = 0.0,
) -> dict:
    """Helper to build a normalized line item dict."""
    net_quantity = quantity - refund_quantity
    gross_revenue = quantity * unit_price
    net_revenue = gross_revenue - refund_amount
    return {
        "id": li_id,
        "title": f"Product {product_id}",
        "quantity": quantity,
        "current_quantity": net_quantity,
        "unit_price": unit_price,
        "gross_revenue": gross_revenue,
        "refund_quantity": refund_quantity,
        "refund_amount": refund_amount,
        "net_quantity": net_quantity,
        "net_revenue": net_revenue,
        "product_id": product_id,
        "product_title": f"Product {product_id}",
        "variant_id": f"v{li_id}",
        "sku": sku,
        "variant_title": "Default",
    }


@pytest.fixture()
def normalized_orders() -> list[dict]:
    """Realistic normalized orders spanning 5 non-consecutive days.

    Timeline: 2025-06-10, 2025-06-11, 2025-06-13, 2025-06-16, 2025-06-17
    (gaps on 2025-06-12, 2025-06-14, 2025-06-15)

    Products: P1 (SKU-A), P2 (SKU-B), P3 (SKU-C)
    Some orders have refunds (refund_quantity > 0).
    """
    return [
        # Day 1: 2025-06-10 -- 2 orders
        _make_order("1001", "2025-06-10T10:00:00Z", "2025-06-10", [
            _make_line_item("5001", "P1", "SKU-A", 3, 10.0),           # net_rev=30, net_qty=3
            _make_line_item("5002", "P2", "SKU-B", 2, 25.0),           # net_rev=50, net_qty=2
        ]),
        _make_order("1002", "2025-06-10T14:00:00Z", "2025-06-10", [
            _make_line_item("5003", "P1", "SKU-A", 1, 10.0),           # net_rev=10, net_qty=1
        ]),
        # Day 2: 2025-06-11 -- 1 order with a refund
        _make_order("1003", "2025-06-11T09:00:00Z", "2025-06-11", [
            _make_line_item("5004", "P2", "SKU-B", 4, 25.0, refund_quantity=1, refund_amount=25.0),
            # gross=100, refund_amt=25 => net_rev=75, net_qty=3
            _make_line_item("5005", "P3", "SKU-C", 2, 15.0),           # net_rev=30, net_qty=2
        ]),
        # Day 3: 2025-06-13 -- 2 orders (gap on 06-12)
        _make_order("1004", "2025-06-13T11:00:00Z", "2025-06-13", [
            _make_line_item("5006", "P1", "SKU-A", 2, 10.0),           # net_rev=20, net_qty=2
        ]),
        _make_order("1005", "2025-06-13T16:00:00Z", "2025-06-13", [
            _make_line_item("5007", "P3", "SKU-C", 5, 15.0, refund_quantity=2, refund_amount=30.0),
            # gross=75, refund_amt=30 => net_rev=45, net_qty=3
        ]),
        # Day 4: 2025-06-16 -- 1 order (gap on 06-14, 06-15)
        _make_order("1006", "2025-06-16T08:00:00Z", "2025-06-16", [
            _make_line_item("5008", "P1", "SKU-A", 1, 10.0),           # net_rev=10, net_qty=1
            _make_line_item("5009", "P2", "SKU-B", 3, 25.0),           # net_rev=75, net_qty=3
        ]),
        # Day 5: 2025-06-17 -- 2 orders
        _make_order("1007", "2025-06-17T12:00:00Z", "2025-06-17", [
            _make_line_item("5010", "P2", "SKU-B", 1, 25.0),           # net_rev=25, net_qty=1
        ]),
        _make_order("1008", "2025-06-17T18:00:00Z", "2025-06-17", [
            _make_line_item("5011", "P3", "SKU-C", 4, 15.0),           # net_rev=60, net_qty=4
            _make_line_item("5012", "P1", "SKU-A", 2, 10.0),           # net_rev=20, net_qty=2
        ]),
    ]
