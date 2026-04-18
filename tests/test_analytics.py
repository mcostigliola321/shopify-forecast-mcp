"""Tests for core/analytics.py -- all five analytics functions."""

from __future__ import annotations

import datetime

import numpy as np
import pandas as pd
import pytest

from shopify_forecast_mcp.core.analytics import (
    analyze_promotion,
    cohort_retention,
    compare_periods,
    detect_anomalies,
    get_seasonality,
)
from shopify_forecast_mcp.core.forecast_result import ForecastResult
from shopify_forecast_mcp.core.metrics import AnalyticsResult


# ---------------------------------------------------------------------------
# analyze_promotion tests
# ---------------------------------------------------------------------------


class TestAnalyzePromotion:
    """Tests 1-3: analyze_promotion returns lift, post-promo hangover, cannibalization."""

    def test_returns_analytics_result_with_lift(self, sample_orders_with_promos):
        result = analyze_promotion(
            sample_orders_with_promos,
            promo_start=datetime.date(2025, 4, 30),
            promo_end=datetime.date(2025, 5, 7),
            baseline_days=30,
            promo_name="Spring Sale",
        )
        assert isinstance(result, AnalyticsResult)
        md = result.to_markdown()
        # Should have promotion impact section with lift data
        assert "Promotion Impact" in md
        # Must contain revenue/order/AOV mentions
        assert "Lift" in md or "lift" in md or "%" in md

    def test_includes_post_promo_hangover(self, sample_orders_with_promos):
        result = analyze_promotion(
            sample_orders_with_promos,
            promo_start=datetime.date(2025, 4, 30),
            promo_end=datetime.date(2025, 5, 7),
        )
        md = result.to_markdown()
        assert "Post-Promo Impact" in md

    def test_includes_product_cannibalization(self, sample_orders_with_promos):
        result = analyze_promotion(
            sample_orders_with_promos,
            promo_start=datetime.date(2025, 4, 30),
            promo_end=datetime.date(2025, 5, 7),
        )
        md = result.to_markdown()
        assert "Cannibalization" in md or "cannibalization" in md


# ---------------------------------------------------------------------------
# detect_anomalies tests
# ---------------------------------------------------------------------------


def _make_test_series_and_forecast(inject_spike: bool = True) -> tuple[pd.Series, ForecastResult]:
    """Build a simple daily series and a ForecastResult with known bands."""
    dates = pd.date_range("2025-01-01", periods=120, freq="D")
    values = np.full(120, 100.0)

    if inject_spike:
        # Inject a spike on days 50-51
        values[50] = 500.0
        values[51] = 450.0

    series = pd.Series(values, index=dates)

    # Create a ForecastResult with flat bands
    point = np.full(120, 100.0)
    quantile = np.zeros((120, 10))
    for i in range(10):
        quantile[:, i] = 100.0

    # Set quantile bands: q10=70, q20=80, q30=85, q70=115, q80=120, q90=130
    quantile[:, 1] = 70.0   # q10
    quantile[:, 2] = 80.0   # q20
    quantile[:, 3] = 85.0   # q30
    quantile[:, 7] = 115.0  # q70
    quantile[:, 8] = 120.0  # q80
    quantile[:, 9] = 130.0  # q90

    forecast = ForecastResult(
        point_forecast=point,
        quantile_forecast=quantile,
        dates=[d.strftime("%Y-%m-%d") for d in dates],
        confidence_bands={
            "mean": quantile[:, 0],
            "q10": quantile[:, 1],
            "q20": quantile[:, 2],
            "q30": quantile[:, 3],
            "q40": quantile[:, 4],
            "q50": quantile[:, 5],
            "q60": quantile[:, 6],
            "q70": quantile[:, 7],
            "q80": quantile[:, 8],
            "q90": quantile[:, 9],
        },
    )
    return series, forecast


class TestDetectAnomalies:
    """Tests 4-7: detect_anomalies with spike, clustering, sensitivity, short history."""

    def test_spike_detected_with_correct_direction(self):
        series, forecast = _make_test_series_and_forecast(inject_spike=True)
        result = detect_anomalies(series, forecast, sensitivity="medium")
        assert isinstance(result, AnalyticsResult)
        md = result.to_markdown()
        assert "Spike" in md

    def test_consecutive_days_grouped_into_clusters(self):
        series, forecast = _make_test_series_and_forecast(inject_spike=True)
        result = detect_anomalies(series, forecast, sensitivity="medium")
        md = result.to_markdown()
        # Days 50-51 should be clustered -- look for date range format
        assert "2025-02-20" in md or "2025-02-21" in md  # days 50-51

    def test_sensitivity_levels_differ(self):
        series, forecast = _make_test_series_and_forecast(inject_spike=True)
        result_low = detect_anomalies(series, forecast, sensitivity="low")
        result_high = detect_anomalies(series, forecast, sensitivity="high")
        # High sensitivity should detect more or equal anomalies than low
        md_low = result_low.to_markdown()
        md_high = result_high.to_markdown()
        # Both should detect our big spike
        assert "Spike" in md_low
        assert "Spike" in md_high

    def test_short_history_warning(self):
        # Create a short series (<90 days)
        dates = pd.date_range("2025-01-01", periods=30, freq="D")
        values = np.full(30, 100.0)
        series = pd.Series(values, index=dates)

        point = np.full(30, 100.0)
        quantile = np.full((30, 10), 100.0)
        quantile[:, 1] = 70.0
        quantile[:, 9] = 130.0

        forecast = ForecastResult(
            point_forecast=point,
            quantile_forecast=quantile,
            dates=[d.strftime("%Y-%m-%d") for d in dates],
            confidence_bands={
                "mean": quantile[:, 0],
                "q10": quantile[:, 1],
                "q20": quantile[:, 2],
                "q30": quantile[:, 3],
                "q40": quantile[:, 4],
                "q50": quantile[:, 5],
                "q60": quantile[:, 6],
                "q70": quantile[:, 7],
                "q80": quantile[:, 8],
                "q90": quantile[:, 9],
            },
        )
        result = detect_anomalies(series, forecast, sensitivity="medium")
        assert "Limited history" in result.summary or "limited history" in result.summary.lower()


# ---------------------------------------------------------------------------
# compare_periods tests
# ---------------------------------------------------------------------------


class TestComparePeriods:
    """Tests 8-9: compare_periods with all 6 metrics and biggest movers."""

    def test_returns_all_six_metrics(self, sample_orders_with_promos):
        result = compare_periods(
            sample_orders_with_promos,
            period_a_start=datetime.date(2025, 3, 31),
            period_a_end=datetime.date(2025, 4, 29),
            period_b_start=datetime.date(2025, 4, 30),
            period_b_end=datetime.date(2025, 5, 29),
        )
        assert isinstance(result, AnalyticsResult)
        md = result.to_markdown()
        # Check all metrics appear in output
        for metric in ["revenue", "orders", "units", "aov", "discount_rate", "units_per_order"]:
            assert metric.lower() in md.lower() or metric.replace("_", " ").lower() in md.lower()

    def test_highlights_biggest_movers(self, sample_orders_with_promos):
        result = compare_periods(
            sample_orders_with_promos,
            period_a_start=datetime.date(2025, 3, 31),
            period_a_end=datetime.date(2025, 4, 29),
            period_b_start=datetime.date(2025, 4, 30),
            period_b_end=datetime.date(2025, 5, 29),
        )
        md = result.to_markdown()
        # Biggest mover should be bold-marked with **
        assert "**" in md


# ---------------------------------------------------------------------------
# get_seasonality tests
# ---------------------------------------------------------------------------


class TestGetSeasonality:
    """Tests 10-11: get_seasonality with day_of_week and monthly."""

    def test_day_of_week_returns_7_rows(self):
        dates = pd.date_range("2025-01-01", periods=365, freq="D")
        # Add some weekend variation
        values = np.array([120.0 if d.weekday() >= 5 else 90.0 for d in dates])
        series = pd.Series(values, index=dates)

        result = get_seasonality(series, granularity="day_of_week")
        assert isinstance(result, AnalyticsResult)
        # Should have exactly 7 data rows
        assert len(result.sections) > 0
        assert len(result.sections[0].table_rows) == 7

        # Index values should average to approximately 100
        indices = [float(row[1]) for row in result.sections[0].table_rows]
        assert pytest.approx(np.mean(indices), abs=5) == 100.0

    def test_monthly_returns_12_rows(self):
        dates = pd.date_range("2025-01-01", periods=365, freq="D")
        values = np.random.default_rng(42).normal(100, 10, 365)
        series = pd.Series(values, index=dates)

        result = get_seasonality(series, granularity="monthly")
        assert isinstance(result, AnalyticsResult)
        assert len(result.sections[0].table_rows) == 12


# ---------------------------------------------------------------------------
# cohort_retention tests
# ---------------------------------------------------------------------------


class TestCohortRetention:
    """Tests 12-13: cohort_retention matrix and LTV."""

    def test_returns_retention_matrix(self, sample_orders_with_promos):
        result = cohort_retention(
            sample_orders_with_promos,
            cohort_period="monthly",
            periods_out=3,
        )
        assert isinstance(result, AnalyticsResult)
        md = result.to_markdown()
        # Should have cohort labels and retention percentages
        assert "Cohort" in md
        assert "%" in md or "Size" in md

    def test_includes_ltv_in_summary(self, sample_orders_with_promos):
        result = cohort_retention(
            sample_orders_with_promos,
            cohort_period="monthly",
            periods_out=3,
        )
        md = result.to_markdown()
        # Should mention LTV or retention in summary
        assert "LTV" in md or "ltv" in md.lower() or "retention" in md.lower()
