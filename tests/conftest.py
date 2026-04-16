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
    return ShopifyClient(shopify_settings)


@pytest.fixture()
def mock_shopify():
    """Mock all Shopify GraphQL requests via the standard dispatcher."""
    with respx.mock:
        respx.post(SHOPIFY_GQL_URL).mock(side_effect=shopify_dispatcher)
        yield
