"""Tests for order normalization: GID stripping, timezone bucketing, refund math.

Covers both paginated and bulk source normalization paths to verify
identical output shapes with correct refund handling.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shopify_forecast_mcp.core.normalize import (
    filter_orders,
    normalize_line_item,
    normalize_order,
    strip_gid,
    utc_to_local_date,
)

# ---------------------------------------------------------------------------
# Fixture loading helpers
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures"


def _load_paginated_orders() -> list[dict]:
    """Load page1 orders from the paginated fixture."""
    data = json.loads((FIXTURES / "mock_orders_paginated.json").read_text())
    return [edge["node"] for edge in data["page1"]["data"]["orders"]["edges"]]


def _load_paginated_page2_orders() -> list[dict]:
    """Load page2 orders from the paginated fixture."""
    data = json.loads((FIXTURES / "mock_orders_paginated.json").read_text())
    return [edge["node"] for edge in data["page2"]["data"]["orders"]["edges"]]


def _load_bulk_orders() -> list[dict]:
    """Load orders from the bulk JSONL fixture via parse_bulk_jsonl."""
    from shopify_forecast_mcp.core.bulk_ops import parse_bulk_jsonl

    lines = (FIXTURES / "mock_bulk.jsonl").read_text().strip().splitlines()
    return parse_bulk_jsonl(lines)


# ---------------------------------------------------------------------------
# strip_gid tests
# ---------------------------------------------------------------------------


class TestStripGid:
    def test_strip_gid(self):
        assert strip_gid("gid://shopify/Order/1234") == "1234"

    def test_strip_gid_no_prefix(self):
        assert strip_gid("1234") == "1234"

    def test_strip_gid_line_item(self):
        assert strip_gid("gid://shopify/LineItem/5678") == "5678"

    def test_strip_gid_empty(self):
        assert strip_gid("") == ""


# ---------------------------------------------------------------------------
# utc_to_local_date tests
# ---------------------------------------------------------------------------


class TestUtcToLocalDate:
    def test_utc_to_local_date_same_day(self):
        """14:30 UTC -> 10:30 EDT -> still June 15."""
        assert utc_to_local_date("2025-06-15T14:30:00Z", "America/New_York") == "2025-06-15"

    def test_utc_to_local_date_day_shift(self):
        """03:30 UTC -> 23:30 EDT June 15 (critical timezone test)."""
        assert utc_to_local_date("2025-06-16T03:30:00Z", "America/New_York") == "2025-06-15"

    def test_utc_to_local_date_2330_utc(self):
        """23:30 UTC -> 19:30 EDT -> still June 15."""
        assert utc_to_local_date("2025-06-15T23:30:00Z", "America/New_York") == "2025-06-15"

    def test_utc_to_local_date_utc_timezone(self):
        """UTC timezone: no shift."""
        assert utc_to_local_date("2025-06-15T23:30:00Z", "UTC") == "2025-06-15"

    def test_utc_to_local_date_positive_offset(self):
        """Tokyo is UTC+9: 23:30 UTC = 08:30 next day."""
        assert utc_to_local_date("2025-06-15T23:30:00Z", "Asia/Tokyo") == "2025-06-16"


# ---------------------------------------------------------------------------
# normalize_line_item tests
# ---------------------------------------------------------------------------


class TestNormalizeLineItem:
    def test_normalize_line_item_refund_aware_paginated(self):
        """Paginated: refund_map provides quantity and amount reductions."""
        li_node = {
            "id": "gid://shopify/LineItem/2003",
            "title": "Premium Hoodie",
            "quantity": 2,
            "currentQuantity": 1,
            "originalUnitPriceSet": {
                "shopMoney": {"amount": "50.00", "currencyCode": "USD"}
            },
            "product": {"id": "gid://shopify/Product/3003", "title": "Premium Hoodie"},
            "variant": {
                "id": "gid://shopify/ProductVariant/4003",
                "sku": "HOODIE-GRY-L",
                "title": "Grey / Large",
            },
        }
        refund_map = {
            "gid://shopify/LineItem/2003": {"quantity": 1, "amount": 25.00},
        }
        result = normalize_line_item(li_node, refund_map=refund_map)

        assert result["id"] == "2003"
        assert result["quantity"] == 2
        assert result["refund_quantity"] == 1
        assert result["net_quantity"] == 1
        assert result["gross_revenue"] == 100.00  # 2 * 50
        assert result["refund_amount"] == 25.00
        assert result["net_revenue"] == 75.00  # 100 - 25

    def test_normalize_line_item_bulk_uses_current_quantity(self):
        """Bulk: no refund_map, uses currentQuantity directly."""
        li_node = {
            "id": "gid://shopify/LineItem/2003",
            "title": "Gadget C",
            "quantity": 2,
            "currentQuantity": 1,
            "originalUnitPriceSet": {
                "shopMoney": {"amount": "50.00", "currencyCode": "USD"}
            },
            "product": {"id": "gid://shopify/Product/3003", "title": "Gadget C Product"},
            "variant": {
                "id": "gid://shopify/ProductVariant/4003",
                "sku": "GADGET-C",
                "title": "Default",
            },
        }
        result = normalize_line_item(li_node, refund_map=None)

        assert result["net_quantity"] == 1  # currentQuantity
        assert result["refund_quantity"] == 1  # quantity - currentQuantity
        assert result["net_revenue"] == 50.00  # 1 * 50

    def test_normalize_line_item_no_refund(self):
        """Paginated with no refunds: refund_quantity and refund_amount are 0."""
        li_node = {
            "id": "gid://shopify/LineItem/2001",
            "title": "Classic T-Shirt",
            "quantity": 2,
            "currentQuantity": 2,
            "originalUnitPriceSet": {
                "shopMoney": {"amount": "50.00", "currencyCode": "USD"}
            },
            "product": {"id": "gid://shopify/Product/3001", "title": "Classic T-Shirt"},
            "variant": {
                "id": "gid://shopify/ProductVariant/4001",
                "sku": "TSHIRT-BLK-M",
                "title": "Black / Medium",
            },
        }
        result = normalize_line_item(li_node, refund_map={})

        assert result["refund_quantity"] == 0
        assert result["refund_amount"] == 0.0
        assert result["net_quantity"] == 2
        assert result["net_revenue"] == 100.00


# ---------------------------------------------------------------------------
# normalize_order tests
# ---------------------------------------------------------------------------


class TestNormalizeOrder:
    def test_normalize_order_from_paginated(self):
        """Paginated order produces correct normalized shape."""
        orders = _load_paginated_orders()
        order_1001 = orders[0]  # Order 1001
        result = normalize_order(order_1001, "America/New_York", source="paginated")

        assert result["id"] == "1001"
        assert result["created_at"] == "2025-06-15T14:30:00Z"
        assert result["local_date"] == "2025-06-15"
        assert result["financial_status"] == "PAID"
        assert result["subtotal"] == 150.00
        assert result["current_subtotal"] == 150.00
        assert result["currency"] == "USD"
        assert result["test"] is False
        assert result["cancelled_at"] is None
        assert len(result["line_items"]) == 2

    def test_normalize_order_from_bulk(self):
        """Bulk order produces same dict shape as paginated."""
        orders = _load_bulk_orders()
        order_1001 = orders[0]  # Order 1001
        result = normalize_order(order_1001, "America/New_York", source="bulk")

        assert result["id"] == "1001"
        assert result["local_date"] == "2025-06-15"
        assert result["current_subtotal"] == 150.00
        assert len(result["line_items"]) == 2
        # Verify all expected keys present
        expected_keys = {
            "id", "created_at", "local_date", "financial_status",
            "subtotal", "current_subtotal", "total_discounts",
            "total_refunded", "net_payment", "currency",
            "discount_codes", "tags", "source_name", "test",
            "cancelled_at", "line_items",
        }
        assert set(result.keys()) == expected_keys

    def test_normalize_order_shape_identical(self):
        """Paginated and bulk normalization produce identical key sets."""
        pag_orders = _load_paginated_orders()
        bulk_orders = _load_bulk_orders()

        pag_result = normalize_order(pag_orders[0], "America/New_York", source="paginated")
        bulk_result = normalize_order(bulk_orders[0], "America/New_York", source="bulk")

        assert set(pag_result.keys()) == set(bulk_result.keys())
        # Line item shapes should also match
        assert set(pag_result["line_items"][0].keys()) == set(bulk_result["line_items"][0].keys())

    def test_normalize_order_refund_math_paginated(self):
        """Order 1002: subtotal=$100, refund=$25 -> current_subtotal=$75."""
        orders = _load_paginated_orders()
        order_1002 = orders[1]  # Order 1002
        result = normalize_order(order_1002, "America/New_York", source="paginated")

        assert result["subtotal"] == 100.00
        assert result["current_subtotal"] == 75.00
        assert result["total_refunded"] == 25.00

        # Line item refund math
        li = result["line_items"][0]
        assert li["quantity"] == 2
        assert li["refund_quantity"] == 1
        assert li["net_quantity"] == 1
        assert li["refund_amount"] == 25.00
        assert li["net_revenue"] == 75.00  # 100 - 25

    def test_normalize_order_refund_math_bulk(self):
        """Order 1002 bulk: currentSubtotalPriceSet=$75, currentQuantity=1."""
        orders = _load_bulk_orders()
        order_1002 = orders[1]  # Order 1002
        result = normalize_order(order_1002, "America/New_York", source="bulk")

        assert result["current_subtotal"] == 75.00
        li = result["line_items"][0]
        assert li["net_quantity"] == 1
        assert li["refund_quantity"] == 1  # quantity(2) - currentQuantity(1)

    def test_normalize_order_timezone_day_shift(self):
        """Order 1003: 03:30 UTC -> 23:30 EDT June 15."""
        orders = _load_paginated_orders()
        order_1003 = orders[2]  # Order 1003
        result = normalize_order(order_1003, "America/New_York", source="paginated")
        assert result["local_date"] == "2025-06-15"

    def test_normalize_order_2330_utc(self):
        """Order 1002: 23:30 UTC -> 19:30 EDT -> still June 15."""
        orders = _load_paginated_orders()
        order_1002 = orders[1]  # Order 1002
        result = normalize_order(order_1002, "America/New_York", source="paginated")
        assert result["local_date"] == "2025-06-15"

    def test_deleted_product_variant(self):
        """Null product/variant handled as 'unknown'."""
        order_node = {
            "id": "gid://shopify/Order/9999",
            "createdAt": "2025-06-15T14:30:00Z",
            "displayFinancialStatus": "PAID",
            "subtotalPriceSet": {"shopMoney": {"amount": "50.00", "currencyCode": "USD"}},
            "currentSubtotalPriceSet": {"shopMoney": {"amount": "50.00", "currencyCode": "USD"}},
            "totalDiscountsSet": {"shopMoney": {"amount": "0.00", "currencyCode": "USD"}},
            "totalRefundedSet": {"shopMoney": {"amount": "0.00", "currencyCode": "USD"}},
            "netPaymentSet": {"shopMoney": {"amount": "50.00", "currencyCode": "USD"}},
            "discountCodes": [],
            "tags": [],
            "sourceName": "web",
            "test": False,
            "cancelledAt": None,
            "lineItems": {
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/LineItem/9999",
                            "title": "Deleted Product",
                            "quantity": 1,
                            "currentQuantity": 1,
                            "originalUnitPriceSet": {
                                "shopMoney": {"amount": "50.00", "currencyCode": "USD"}
                            },
                            "product": None,
                            "variant": None,
                        }
                    }
                ]
            },
            "refunds": [],
        }
        result = normalize_order(order_node, "UTC", source="paginated")
        li = result["line_items"][0]
        assert li["product_id"] == "unknown"
        assert li["product_title"] == "Unknown Product"
        assert li["variant_id"] == "unknown"
        assert li["sku"] == ""
        assert li["variant_title"] == ""


# ---------------------------------------------------------------------------
# filter_orders tests
# ---------------------------------------------------------------------------


class TestFilterOrders:
    def test_filter_orders_excludes_test(self):
        """Test orders (test: true) are excluded."""
        orders = [
            {"test": True, "cancelled_at": None, "id": "1"},
            {"test": False, "cancelled_at": None, "id": "2"},
        ]
        result = filter_orders(orders)
        assert len(result) == 1
        assert result[0]["id"] == "2"

    def test_filter_orders_excludes_cancelled(self):
        """Cancelled orders are excluded."""
        orders = [
            {"test": False, "cancelled_at": "2025-06-17T10:00:00Z", "id": "1"},
            {"test": False, "cancelled_at": None, "id": "2"},
        ]
        result = filter_orders(orders)
        assert len(result) == 1
        assert result[0]["id"] == "2"

    def test_filter_orders_keeps_valid(self):
        """Valid orders are kept."""
        orders = [
            {"test": False, "cancelled_at": None, "id": "1"},
            {"test": False, "cancelled_at": None, "id": "2"},
        ]
        result = filter_orders(orders)
        assert len(result) == 2

    def test_filter_orders_empty_input(self):
        """Empty list produces empty list."""
        assert filter_orders([]) == []

    def test_filter_orders_mixed(self):
        """Mix of test, cancelled, and valid orders: only valid survive."""
        pag_orders = _load_paginated_orders()
        page2_orders = _load_paginated_page2_orders()
        all_raw = pag_orders + page2_orders

        # Normalize all
        normalized = [
            normalize_order(o, "America/New_York", source="paginated")
            for o in all_raw
        ]
        # page2 has order 1005 with test=true
        result = filter_orders(normalized)
        # Should exclude order 1005 (test=true)
        ids = [o["id"] for o in result]
        assert "1005" not in ids
        assert "1001" in ids
