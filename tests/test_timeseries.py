"""Tests for orders_to_daily_series daily aggregation.

TDD RED phase: all tests call the stub and expect specific numeric results.
They will fail with NotImplementedError until Task 2 implements the function.
"""

from __future__ import annotations

import pandas as pd
import pytest

from shopify_forecast_mcp.core.timeseries import (
    GroupBy,
    Metric,
    orders_to_daily_series,
)


# ---------------------------------------------------------------------------
# Store-level metric tests (group_by=None)
# ---------------------------------------------------------------------------


class TestRevenueMetric:
    """metric='revenue' sums net_revenue per local_date."""

    def test_revenue_per_day(self, normalized_orders: list[dict]) -> None:
        result = orders_to_daily_series(normalized_orders, metric="revenue")
        assert "store" in result
        s = result["store"]
        assert isinstance(s, pd.Series)
        assert isinstance(s.index, pd.DatetimeIndex)

        # Day 2025-06-10: 30 + 50 + 10 = 90
        assert s.loc["2025-06-10"] == pytest.approx(90.0)
        # Day 2025-06-11: 75 + 30 = 105
        assert s.loc["2025-06-11"] == pytest.approx(105.0)
        # Day 2025-06-13: 20 + 45 = 65
        assert s.loc["2025-06-13"] == pytest.approx(65.0)
        # Day 2025-06-16: 10 + 75 = 85
        assert s.loc["2025-06-16"] == pytest.approx(85.0)
        # Day 2025-06-17: 25 + 60 + 20 = 105
        assert s.loc["2025-06-17"] == pytest.approx(105.0)


class TestOrdersMetric:
    """metric='orders' counts distinct orders per local_date."""

    def test_orders_per_day(self, normalized_orders: list[dict]) -> None:
        result = orders_to_daily_series(normalized_orders, metric="orders")
        s = result["store"]

        # Day 2025-06-10: 2 orders (1001, 1002)
        assert s.loc["2025-06-10"] == pytest.approx(2.0)
        # Day 2025-06-11: 1 order (1003)
        assert s.loc["2025-06-11"] == pytest.approx(1.0)
        # Day 2025-06-13: 2 orders (1004, 1005)
        assert s.loc["2025-06-13"] == pytest.approx(2.0)
        # Day 2025-06-16: 1 order (1006)
        assert s.loc["2025-06-16"] == pytest.approx(1.0)
        # Day 2025-06-17: 2 orders (1007, 1008)
        assert s.loc["2025-06-17"] == pytest.approx(2.0)


class TestUnitsMetric:
    """metric='units' sums net_quantity from line items per day."""

    def test_units_per_day(self, normalized_orders: list[dict]) -> None:
        result = orders_to_daily_series(normalized_orders, metric="units")
        s = result["store"]

        # Day 2025-06-10: 3 + 2 + 1 = 6
        assert s.loc["2025-06-10"] == pytest.approx(6.0)
        # Day 2025-06-11: 3 + 2 = 5
        assert s.loc["2025-06-11"] == pytest.approx(5.0)
        # Day 2025-06-13: 2 + 3 = 5
        assert s.loc["2025-06-13"] == pytest.approx(5.0)
        # Day 2025-06-16: 1 + 3 = 4
        assert s.loc["2025-06-16"] == pytest.approx(4.0)
        # Day 2025-06-17: 1 + 4 + 2 = 7
        assert s.loc["2025-06-17"] == pytest.approx(7.0)


class TestAovMetric:
    """metric='aov' computes revenue/orders per day; 0 for zero-order days."""

    def test_aov_per_day(self, normalized_orders: list[dict]) -> None:
        result = orders_to_daily_series(normalized_orders, metric="aov")
        s = result["store"]

        # Day 2025-06-10: revenue=90, orders=2 -> aov=45
        assert s.loc["2025-06-10"] == pytest.approx(45.0)
        # Day 2025-06-11: revenue=105, orders=1 -> aov=105
        assert s.loc["2025-06-11"] == pytest.approx(105.0)
        # Gap day 2025-06-12: 0 orders -> aov=0.0 (not NaN)
        assert s.loc["2025-06-12"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Zero-fill / gap tests
# ---------------------------------------------------------------------------


class TestZeroFill:
    """Date range with gaps between orders -> gap days have 0.0, not NaN."""

    def test_gap_days_are_zero_filled(self, normalized_orders: list[dict]) -> None:
        result = orders_to_daily_series(normalized_orders, metric="revenue")
        s = result["store"]

        # Full range: 2025-06-10 to 2025-06-17 = 8 days
        assert len(s) == 8

        # Gap days should be 0.0
        assert s.loc["2025-06-12"] == pytest.approx(0.0)
        assert s.loc["2025-06-14"] == pytest.approx(0.0)
        assert s.loc["2025-06-15"] == pytest.approx(0.0)

        # No NaN anywhere
        assert not s.isna().any()


# ---------------------------------------------------------------------------
# group_by=None -> single key "store"
# ---------------------------------------------------------------------------


class TestGroupByNone:
    """group_by=None -> dict with single key 'store'."""

    def test_single_store_key(self, normalized_orders: list[dict]) -> None:
        result = orders_to_daily_series(normalized_orders, metric="revenue")
        assert list(result.keys()) == ["store"]


# ---------------------------------------------------------------------------
# group_by="product_id"
# ---------------------------------------------------------------------------


class TestGroupByProductId:
    """group_by='product_id' -> dict keyed by product_id."""

    def test_product_id_keys(self, normalized_orders: list[dict]) -> None:
        result = orders_to_daily_series(
            normalized_orders, metric="revenue", group_by="product_id"
        )
        assert set(result.keys()) == {"P1", "P2", "P3"}

    def test_product_revenue(self, normalized_orders: list[dict]) -> None:
        result = orders_to_daily_series(
            normalized_orders, metric="revenue", group_by="product_id"
        )
        p1 = result["P1"]
        # P1 on 2025-06-10: 30 + 10 = 40
        assert p1.loc["2025-06-10"] == pytest.approx(40.0)
        # P1 on 2025-06-13: 20
        assert p1.loc["2025-06-13"] == pytest.approx(20.0)
        # P1 on gap day 2025-06-12: 0
        assert p1.loc["2025-06-12"] == pytest.approx(0.0)
        # No NaN
        assert not p1.isna().any()


# ---------------------------------------------------------------------------
# group_by="sku"
# ---------------------------------------------------------------------------


class TestGroupBySku:
    """group_by='sku' -> dict keyed by SKU."""

    def test_sku_keys(self, normalized_orders: list[dict]) -> None:
        result = orders_to_daily_series(
            normalized_orders, metric="units", group_by="sku"
        )
        assert set(result.keys()) == {"SKU-A", "SKU-B", "SKU-C"}

    def test_sku_units(self, normalized_orders: list[dict]) -> None:
        result = orders_to_daily_series(
            normalized_orders, metric="units", group_by="sku"
        )
        sku_b = result["SKU-B"]
        # SKU-B on 2025-06-10: net_qty=2 (order 1001)
        assert sku_b.loc["2025-06-10"] == pytest.approx(2.0)
        # SKU-B on 2025-06-11: net_qty=3 (order 1003, refunded 1 of 4)
        assert sku_b.loc["2025-06-11"] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# group_by="collection_id" with product_collection_map
# ---------------------------------------------------------------------------


class TestGroupByCollectionId:
    """group_by='collection_id' with product_collection_map."""

    def test_collection_fan_out(self, normalized_orders: list[dict]) -> None:
        """Product in 2 collections contributes to both series."""
        coll_map = {
            "P1": ["C1", "C2"],  # P1 in both C1 and C2
            "P2": ["C1"],
            "P3": ["C2"],
        }
        result = orders_to_daily_series(
            normalized_orders,
            metric="revenue",
            group_by="collection_id",
            product_collection_map=coll_map,
        )
        assert set(result.keys()) == {"C1", "C2"}

        c1 = result["C1"]
        # C1 gets P1 + P2
        # Day 2025-06-10: P1=40, P2=50 -> 90
        assert c1.loc["2025-06-10"] == pytest.approx(90.0)
        # Day 2025-06-11: P2=75 -> 75
        assert c1.loc["2025-06-11"] == pytest.approx(75.0)

        c2 = result["C2"]
        # C2 gets P1 + P3
        # Day 2025-06-10: P1=40 -> 40
        assert c2.loc["2025-06-10"] == pytest.approx(40.0)
        # Day 2025-06-11: P3=30 -> 30
        assert c2.loc["2025-06-11"] == pytest.approx(30.0)

    def test_collection_requires_map(self, normalized_orders: list[dict]) -> None:
        """Raises ValueError when product_collection_map is None."""
        with pytest.raises(ValueError, match="product_collection_map"):
            orders_to_daily_series(
                normalized_orders,
                metric="revenue",
                group_by="collection_id",
            )


# ---------------------------------------------------------------------------
# Empty orders
# ---------------------------------------------------------------------------


class TestEmptyOrders:
    """Empty orders list -> dict with empty Series or empty dict."""

    def test_empty_store_level(self) -> None:
        result = orders_to_daily_series([], metric="revenue")
        assert "store" in result
        assert len(result["store"]) == 0

    def test_empty_grouped(self) -> None:
        result = orders_to_daily_series(
            [], metric="revenue", group_by="product_id"
        )
        assert result == {}


# ---------------------------------------------------------------------------
# Refund-adjusted values
# ---------------------------------------------------------------------------


class TestRefundAdjusted:
    """Orders with refunds use net_quantity and net_revenue, not gross."""

    def test_refund_uses_net_values(self, normalized_orders: list[dict]) -> None:
        result = orders_to_daily_series(
            normalized_orders, metric="revenue", group_by="product_id"
        )
        p2 = result["P2"]
        # P2 on 2025-06-11: gross=100, refund_amount=25 => net_revenue=75
        assert p2.loc["2025-06-11"] == pytest.approx(75.0)

        units = orders_to_daily_series(
            normalized_orders, metric="units", group_by="product_id"
        )
        p3_units = units["P3"]
        # P3 on 2025-06-13: quantity=5, refund_quantity=2 => net_quantity=3
        assert p3_units.loc["2025-06-13"] == pytest.approx(3.0)
