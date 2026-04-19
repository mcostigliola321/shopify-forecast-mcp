"""Tests for inventory fetch and reorder alert logic.

Covers:
- ShopifyClient.fetch_inventory parsing, filtering, pagination
- compute_reorder_alerts formula and edge cases
- format_reorder_alerts markdown output
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock

import pytest

from shopify_forecast_mcp.config import Settings
from shopify_forecast_mcp.core.shopify_client import ShopifyClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graphql_inventory_response(
    variants: list[dict],
    has_next_page: bool = False,
    end_cursor: str | None = "cursor1",
) -> dict:
    """Build a mock GraphQL response for INVENTORY_QUERY."""
    edges = []
    for v in variants:
        inv_levels = []
        for loc in v.get("locations", []):
            inv_levels.append({
                "node": {
                    "location": {"id": f"gid://shopify/Location/{loc['id']}", "name": loc["name"]},
                    "quantities": [{"name": "available", "quantity": loc["available"]}],
                }
            })
        edges.append({
            "node": {
                "id": f"gid://shopify/ProductVariant/{v['variant_id']}",
                "sku": v.get("sku", ""),
                "product": {
                    "id": f"gid://shopify/Product/{v['product_id']}",
                    "title": v.get("product_title", ""),
                },
                "inventoryItem": {
                    "id": f"gid://shopify/InventoryItem/{v['variant_id']}",
                    "tracked": v.get("tracked", True),
                    "inventoryLevels": {"edges": inv_levels},
                },
            }
        })
    return {
        "data": {
            "productVariants": {
                "pageInfo": {"hasNextPage": has_next_page, "endCursor": end_cursor},
                "edges": edges,
            }
        }
    }


def _make_backend(responses: list[dict]) -> AsyncMock:
    """Create a mock backend that returns responses in sequence."""
    backend = AsyncMock()
    backend.post_graphql = AsyncMock(side_effect=responses)
    backend.close = AsyncMock()
    return backend


def _make_settings() -> MagicMock:
    """Minimal Settings mock."""
    settings = MagicMock(spec=Settings)
    settings.shop = "test.myshopify.com"
    settings.forecast_cache_ttl = 0
    return settings


# ---------------------------------------------------------------------------
# fetch_inventory tests
# ---------------------------------------------------------------------------


class TestFetchInventory:
    """Tests for ShopifyClient.fetch_inventory."""

    @pytest.mark.asyncio()
    async def test_fetch_inventory_parses_response(self) -> None:
        """Mock backend returns 2 variants at 2 locations -> 4 inventory dicts."""
        response = _make_graphql_inventory_response([
            {
                "variant_id": "100",
                "sku": "SKU-A",
                "product_id": "10",
                "product_title": "Widget A",
                "tracked": True,
                "locations": [
                    {"id": "1", "name": "Warehouse 1", "available": 50},
                    {"id": "2", "name": "Warehouse 2", "available": 30},
                ],
            },
            {
                "variant_id": "200",
                "sku": "SKU-B",
                "product_id": "20",
                "product_title": "Widget B",
                "tracked": True,
                "locations": [
                    {"id": "1", "name": "Warehouse 1", "available": 100},
                    {"id": "2", "name": "Warehouse 2", "available": 0},
                ],
            },
        ])
        backend = _make_backend([response])
        client = ShopifyClient(backend, _make_settings())

        inventory = await client.fetch_inventory()

        assert len(inventory) == 4
        # Check first entry
        assert inventory[0]["variant_id"] == "100"
        assert inventory[0]["sku"] == "SKU-A"
        assert inventory[0]["product_id"] == "10"
        assert inventory[0]["product_title"] == "Widget A"
        assert inventory[0]["available"] == 50
        assert inventory[0]["location_id"] == "1"
        assert inventory[0]["location_name"] == "Warehouse 1"
        # Check second variant, first location
        assert inventory[2]["variant_id"] == "200"
        assert inventory[2]["available"] == 100

    @pytest.mark.asyncio()
    async def test_fetch_inventory_skips_untracked(self) -> None:
        """Variants with tracked=False are excluded."""
        response = _make_graphql_inventory_response([
            {
                "variant_id": "100",
                "sku": "SKU-A",
                "product_id": "10",
                "product_title": "Widget A",
                "tracked": True,
                "locations": [{"id": "1", "name": "WH1", "available": 50}],
            },
            {
                "variant_id": "200",
                "sku": "SKU-B",
                "product_id": "20",
                "product_title": "Widget B",
                "tracked": False,
                "locations": [{"id": "1", "name": "WH1", "available": 100}],
            },
        ])
        backend = _make_backend([response])
        client = ShopifyClient(backend, _make_settings())

        inventory = await client.fetch_inventory()

        assert len(inventory) == 1
        assert inventory[0]["variant_id"] == "100"

    @pytest.mark.asyncio()
    async def test_fetch_inventory_paginates(self) -> None:
        """When hasNextPage=True, fetch_inventory calls execute again."""
        page1 = _make_graphql_inventory_response(
            [{"variant_id": "100", "sku": "S1", "product_id": "10",
              "product_title": "P1", "tracked": True,
              "locations": [{"id": "1", "name": "WH1", "available": 10}]}],
            has_next_page=True, end_cursor="cursor_abc",
        )
        page2 = _make_graphql_inventory_response(
            [{"variant_id": "200", "sku": "S2", "product_id": "20",
              "product_title": "P2", "tracked": True,
              "locations": [{"id": "1", "name": "WH1", "available": 20}]}],
            has_next_page=False,
        )
        backend = _make_backend([page1, page2])
        client = ShopifyClient(backend, _make_settings())

        inventory = await client.fetch_inventory()

        assert len(inventory) == 2
        assert backend.post_graphql.call_count == 2
        assert inventory[0]["variant_id"] == "100"
        assert inventory[1]["variant_id"] == "200"


# ---------------------------------------------------------------------------
# compute_reorder_alerts tests
# ---------------------------------------------------------------------------


class TestComputeReorderAlerts:
    """Tests for compute_reorder_alerts."""

    def test_basic_alert_fires(self) -> None:
        """Alert fires when days_to_stockout < lead_time_days."""
        from shopify_forecast_mcp.core.inventory import compute_reorder_alerts

        inventory = [
            {"product_id": "p1", "available": 100, "sku": "S1",
             "product_title": "Product 1", "location_name": "WH1"},
        ]
        forecasts = {"p1": 10.0}
        alerts = compute_reorder_alerts(inventory, forecasts, lead_time_days=14)

        assert len(alerts) == 1
        assert alerts[0]["days_to_stockout"] == 10.0
        # suggested_qty = round(14 * 10 * 1.2) = 168
        assert alerts[0]["suggested_reorder_qty"] == 168

    def test_no_alert_when_sufficient_stock(self) -> None:
        """No alert when days_to_stockout > lead_time_days."""
        from shopify_forecast_mcp.core.inventory import compute_reorder_alerts

        inventory = [
            {"product_id": "p1", "available": 200, "sku": "S1",
             "product_title": "Product 1", "location_name": "WH1"},
        ]
        forecasts = {"p1": 5.0}
        alerts = compute_reorder_alerts(inventory, forecasts, lead_time_days=14)

        assert len(alerts) == 0

    def test_custom_safety_factor(self) -> None:
        """Custom safety_factor changes suggested qty."""
        from shopify_forecast_mcp.core.inventory import compute_reorder_alerts

        inventory = [
            {"product_id": "p1", "available": 100, "sku": "S1",
             "product_title": "Product 1", "location_name": "WH1"},
        ]
        forecasts = {"p1": 10.0}
        alerts = compute_reorder_alerts(
            inventory, forecasts, lead_time_days=14, safety_factor=1.5
        )

        assert len(alerts) == 1
        # suggested_qty = round(14 * 10 * 1.5) = 210
        assert alerts[0]["suggested_reorder_qty"] == 210


# ---------------------------------------------------------------------------
# format_reorder_alerts tests
# ---------------------------------------------------------------------------


class TestFormatReorderAlerts:
    """Tests for format_reorder_alerts."""

    def test_markdown_table_headers(self) -> None:
        """format_reorder_alerts returns markdown with correct headers."""
        from shopify_forecast_mcp.core.inventory import format_reorder_alerts

        alerts = [
            {
                "product_title": "Widget A",
                "sku": "SKU-A",
                "current_stock": 50,
                "daily_demand": 10.0,
                "days_to_stockout": 5.0,
                "suggested_reorder_qty": 168,
                "location": "WH1",
            }
        ]
        result = format_reorder_alerts(alerts)

        assert "## Reorder Alerts" in result
        assert "Product" in result
        assert "SKU" in result
        assert "Stock" in result
        assert "Daily Demand" in result
        assert "Days to Stockout" in result
        assert "Reorder Qty" in result
        assert "Location" in result
        assert "Widget A" in result
        assert "SKU-A" in result

    def test_empty_alerts_returns_empty(self) -> None:
        """Empty alerts list returns empty string."""
        from shopify_forecast_mcp.core.inventory import format_reorder_alerts

        assert format_reorder_alerts([]) == ""
