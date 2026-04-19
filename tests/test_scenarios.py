"""Tests for scenario comparison core module.

Covers ScenarioResult dataclass, run_scenarios async function,
and format_scenario_comparison formatter.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from shopify_forecast_mcp.core.forecaster import COVARIATES_DISCLAIMER
from shopify_forecast_mcp.core.scenarios import (
    ScenarioResult,
    format_scenario_comparison,
    run_scenarios,
)


# ---------------------------------------------------------------------------
# Mock engine that returns deterministic, distinguishable forecasts
# ---------------------------------------------------------------------------


class MockEngine:
    """Returns different forecasts based on call count to distinguish scenarios."""

    def __init__(self) -> None:
        self.call_count = 0

    def forecast_with_covariates(
        self,
        series: np.ndarray | list[np.ndarray],
        covariates: dict,
        horizon: int | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        self.call_count += 1
        h = horizon or 30
        # Each call returns different values so scenarios are distinguishable
        base = 100.0 * self.call_count
        point = np.array([[base + i for i in range(h)]])
        quantile = np.ones((1, h, 10)) * (base - 10.0)
        quantile[:, :, 1] = base - 20.0  # q10
        quantile[:, :, 9] = base + 20.0  # q90
        return point, quantile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scenario(name: str, start: str, end: str, depth: float) -> dict:
    return {
        "name": name,
        "promo_start": start,
        "promo_end": end,
        "discount_depth": depth,
    }


def _make_fake_orders(n_days: int = 30) -> list[dict]:
    """Build minimal fake orders for testing."""
    orders = []
    for i in range(n_days):
        d = f"2025-06-{i + 1:02d}"
        orders.append(
            {
                "id": str(1000 + i),
                "created_at": f"{d}T10:00:00Z",
                "local_date": d,
                "financial_status": "PAID",
                "subtotal": 100.0,
                "current_subtotal": 100.0,
                "total_discounts": 0.0,
                "total_refunded": 0.0,
                "net_payment": 100.0,
                "currency": "USD",
                "discount_codes": [],
                "tags": [],
                "source_name": "",
                "test": False,
                "cancelled_at": None,
                "customer_id": "C1",
                "line_items": [
                    {
                        "id": str(5000 + i),
                        "title": "Widget",
                        "quantity": 1,
                        "current_quantity": 1,
                        "unit_price": 100.0,
                        "gross_revenue": 100.0,
                        "refund_quantity": 0,
                        "refund_amount": 0.0,
                        "net_quantity": 1,
                        "net_revenue": 100.0,
                        "product_id": "P1",
                        "product_title": "Widget",
                        "variant_id": "V1",
                        "sku": "SKU-A",
                        "variant_title": "Default",
                    }
                ],
            }
        )
    return orders


# ---------------------------------------------------------------------------
# Test ScenarioResult dataclass
# ---------------------------------------------------------------------------


class TestScenarioResult:
    def test_scenario_result_dataclass(self) -> None:
        r = ScenarioResult(
            name="Test",
            total_revenue=1500.0,
            peak_day="2025-07-05",
            peak_value=200.0,
            q10_total=1200.0,
            q90_total=1800.0,
            daily_forecast=[100.0, 150.0, 200.0],
        )
        assert r.name == "Test"
        assert r.total_revenue == 1500.0
        assert r.peak_day == "2025-07-05"
        assert r.peak_value == 200.0
        assert r.q10_total == 1200.0
        assert r.q90_total == 1800.0
        assert r.daily_forecast == [100.0, 150.0, 200.0]


# ---------------------------------------------------------------------------
# Test run_scenarios
# ---------------------------------------------------------------------------


class TestRunScenarios:
    @pytest.mark.asyncio()
    async def test_run_scenarios_returns_list(self) -> None:
        orders = _make_fake_orders(30)
        scenarios = [
            _make_scenario("A", "2025-07-01", "2025-07-07", 0.2),
            _make_scenario("B", "2025-07-01", "2025-07-07", 0.3),
        ]
        engine = MockEngine()

        with patch(
            "shopify_forecast_mcp.core.scenarios.orders_to_daily_series"
        ) as mock_ots, patch(
            "shopify_forecast_mcp.core.scenarios.clean_series"
        ) as mock_cs:
            fake_series = pd.Series(
                [100.0] * 30,
                index=pd.date_range("2025-06-01", periods=30, freq="D"),
            )
            mock_ots.return_value = {"store": fake_series}
            mock_cs.return_value = fake_series

            results = await run_scenarios(orders, scenarios, 30, engine)

        assert isinstance(results, list)
        assert len(results) == 2
        assert all(isinstance(r, ScenarioResult) for r in results)

    @pytest.mark.asyncio()
    async def test_run_scenarios_validates_count_too_few(self) -> None:
        with pytest.raises(ValueError, match="2.*4"):
            await run_scenarios([], [_make_scenario("A", "2025-07-01", "2025-07-07", 0.2)], 30, MockEngine())

    @pytest.mark.asyncio()
    async def test_run_scenarios_validates_count_too_many(self) -> None:
        scenarios = [
            _make_scenario(f"S{i}", "2025-07-01", "2025-07-07", 0.1 * i)
            for i in range(5)
        ]
        with pytest.raises(ValueError, match="2.*4"):
            await run_scenarios([], scenarios, 30, MockEngine())

    @pytest.mark.asyncio()
    async def test_run_scenarios_distinguishes_scenarios(self) -> None:
        orders = _make_fake_orders(30)
        scenarios = [
            _make_scenario("Conservative", "2025-07-01", "2025-07-07", 0.1),
            _make_scenario("Aggressive", "2025-07-01", "2025-07-14", 0.4),
        ]
        engine = MockEngine()

        with patch(
            "shopify_forecast_mcp.core.scenarios.orders_to_daily_series"
        ) as mock_ots, patch(
            "shopify_forecast_mcp.core.scenarios.clean_series"
        ) as mock_cs:
            fake_series = pd.Series(
                [100.0] * 30,
                index=pd.date_range("2025-06-01", periods=30, freq="D"),
            )
            mock_ots.return_value = {"store": fake_series}
            mock_cs.return_value = fake_series

            results = await run_scenarios(orders, scenarios, 30, engine)

        # Different call counts mean different base values
        assert results[0].total_revenue != results[1].total_revenue
        assert results[0].name == "Conservative"
        assert results[1].name == "Aggressive"


# ---------------------------------------------------------------------------
# Test format_scenario_comparison
# ---------------------------------------------------------------------------


class TestFormatScenarioComparison:
    def _make_results(self) -> list[ScenarioResult]:
        return [
            ScenarioResult(
                name="Conservative",
                total_revenue=3000.0,
                peak_day="2025-07-15",
                peak_value=150.0,
                q10_total=2500.0,
                q90_total=3500.0,
                daily_forecast=[100.0] * 30,
            ),
            ScenarioResult(
                name="Aggressive",
                total_revenue=5000.0,
                peak_day="2025-07-10",
                peak_value=250.0,
                q10_total=4000.0,
                q90_total=6000.0,
                daily_forecast=[166.67] * 30,
            ),
        ]

    def test_format_comparison_table(self) -> None:
        results = self._make_results()
        output = format_scenario_comparison(results, 30)
        assert "| Metric |" in output
        assert "| Total Revenue |" in output
        assert "| Peak Day |" in output
        assert "| Low Estimate (10%) |" in output
        assert "| High Estimate (90%) |" in output

    def test_format_comparison_recommendation(self) -> None:
        results = self._make_results()
        output = format_scenario_comparison(results, 30)
        assert "**Recommendation:**" in output
        # Should recommend the highest-revenue scenario
        assert "Aggressive" in output

    def test_format_comparison_disclaimer(self) -> None:
        results = self._make_results()
        output = format_scenario_comparison(results, 30)
        assert output.rstrip().endswith(COVARIATES_DISCLAIMER)

    def test_format_comparison_has_header(self) -> None:
        results = self._make_results()
        output = format_scenario_comparison(results, 30)
        assert "Scenario Comparison" in output
        assert "30-day" in output
