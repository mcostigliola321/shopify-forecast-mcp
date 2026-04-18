"""Tests for core/metrics.py -- AnalyticsResult, SUPPORTED_METRICS, aggregation functions."""

from __future__ import annotations

import pytest

from shopify_forecast_mcp.core.metrics import (
    SUPPORTED_METRICS,
    AnalyticsResult,
    AnalyticsSection,
    aggregate_metrics,
    compute_discount_rate,
    compute_units_per_order,
)


class TestAnalyticsResult:
    """Test 1: AnalyticsResult.to_markdown() produces markdown with title, sections, summary, recommendations."""

    def test_to_markdown_renders_title_sections_summary_recommendations(self):
        section = AnalyticsSection(
            heading="Test Section",
            table_headers=["Col A", "Col B"],
            table_rows=[["val1", "val2"], ["val3", "val4"]],
        )
        result = AnalyticsResult(
            title="Test Report",
            sections=[section],
            summary="This is the summary.",
            recommendations=["Do thing A.", "Do thing B."],
        )
        md = result.to_markdown()

        assert "# Test Report" in md
        assert "## Test Section" in md
        assert "| Col A | Col B |" in md
        assert "| val1 | val2 |" in md
        assert "This is the summary." in md
        assert "**Recommendations:**" in md
        assert "- Do thing A." in md
        assert "- Do thing B." in md


class TestSupportedMetrics:
    """Test 2: SUPPORTED_METRICS contains all 6 metrics."""

    def test_contains_all_six_metrics(self):
        expected = {"revenue", "orders", "units", "aov", "discount_rate", "units_per_order"}
        assert set(SUPPORTED_METRICS) == expected
        assert len(SUPPORTED_METRICS) == 6


class TestComputeDiscountRate:
    """Tests 3-4: compute_discount_rate."""

    def test_returns_percentage_of_discounted_orders(self, sample_orders_with_promos):
        # Filter to promo period where all orders have discount codes
        promo_orders = [o for o in sample_orders_with_promos if len(o["discount_codes"]) > 0]
        rate = compute_discount_rate(promo_orders)
        assert rate == pytest.approx(100.0)

        # Mix: half with, half without
        no_discount = [o for o in sample_orders_with_promos if len(o["discount_codes"]) == 0]
        mixed = promo_orders[:5] + no_discount[:5]
        rate_mixed = compute_discount_rate(mixed)
        assert 0.0 < rate_mixed < 100.0
        assert rate_mixed == pytest.approx(50.0)

    def test_empty_list_returns_zero(self):
        assert compute_discount_rate([]) == 0.0


class TestComputeUnitsPerOrder:
    """Tests 5-6: compute_units_per_order."""

    def test_returns_average_units(self, sample_orders_with_promos):
        # Take a small slice for predictable testing
        subset = sample_orders_with_promos[:3]
        result = compute_units_per_order(subset)
        total_units = sum(
            li["net_quantity"] for o in subset for li in o["line_items"]
        )
        expected = total_units / len(subset)
        assert result == pytest.approx(expected)

    def test_empty_list_returns_zero(self):
        assert compute_units_per_order([]) == 0.0


class TestAggregateMetrics:
    """Tests 7: aggregate_metrics returns dict with all 6 metrics."""

    def test_returns_all_six_metrics(self, sample_orders_with_promos):
        result = aggregate_metrics(
            sample_orders_with_promos,
            start_date="2025-04-30",
            end_date="2025-05-07",
        )
        assert isinstance(result, dict)
        for metric_name in SUPPORTED_METRICS:
            assert metric_name in result, f"Missing metric: {metric_name}"
            assert isinstance(result[metric_name], (int, float))


class TestNormalizeOrderCustomerId:
    """Tests 8-9: normalize_order includes customer_id."""

    def test_customer_id_extracted(self):
        from shopify_forecast_mcp.core.normalize import normalize_order

        order_node = {
            "id": "gid://shopify/Order/999",
            "createdAt": "2025-06-01T10:00:00Z",
            "displayFinancialStatus": "PAID",
            "subtotalPriceSet": {"shopMoney": {"amount": "50.0", "currencyCode": "USD"}},
            "currentSubtotalPriceSet": {"shopMoney": {"amount": "50.0", "currencyCode": "USD"}},
            "totalDiscountsSet": {"shopMoney": {"amount": "0.0", "currencyCode": "USD"}},
            "totalRefundedSet": {"shopMoney": {"amount": "0.0", "currencyCode": "USD"}},
            "netPaymentSet": {"shopMoney": {"amount": "50.0", "currencyCode": "USD"}},
            "discountCodes": [],
            "tags": [],
            "sourceName": "web",
            "test": False,
            "cancelledAt": None,
            "customer": {"id": "gid://shopify/Customer/12345"},
            "lineItems": {"edges": []},
        }
        result = normalize_order(order_node, "America/New_York", source="paginated")
        assert result["customer_id"] == "12345"

    def test_missing_customer_returns_unknown(self):
        from shopify_forecast_mcp.core.normalize import normalize_order

        order_node = {
            "id": "gid://shopify/Order/998",
            "createdAt": "2025-06-01T10:00:00Z",
            "displayFinancialStatus": "PAID",
            "subtotalPriceSet": {"shopMoney": {"amount": "50.0", "currencyCode": "USD"}},
            "currentSubtotalPriceSet": {"shopMoney": {"amount": "50.0", "currencyCode": "USD"}},
            "totalDiscountsSet": {"shopMoney": {"amount": "0.0", "currencyCode": "USD"}},
            "totalRefundedSet": {"shopMoney": {"amount": "0.0", "currencyCode": "USD"}},
            "netPaymentSet": {"shopMoney": {"amount": "50.0", "currencyCode": "USD"}},
            "discountCodes": [],
            "tags": [],
            "sourceName": "web",
            "test": False,
            "cancelledAt": None,
            "lineItems": {"edges": []},
        }
        result = normalize_order(order_node, "America/New_York", source="paginated")
        assert result["customer_id"] == "unknown"
