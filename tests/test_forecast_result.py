"""Unit tests for ForecastResult dataclass.

These tests do NOT require TimesFM -- they use synthetic numpy arrays.
"""

from __future__ import annotations

import numpy as np
import pytest

from shopify_forecast_mcp.core.forecast_result import ForecastResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(horizon: int = 30, metric: str = "revenue") -> ForecastResult:
    """Build a ForecastResult from fake batch arrays."""
    rng = np.random.default_rng(123)
    point = rng.uniform(3000, 6000, size=(1, horizon))
    quantile = rng.uniform(2000, 7000, size=(1, horizon, 10))
    # Ensure channel 0 (mean) is close to point forecast
    quantile[0, :, 0] = point[0, :] + rng.normal(0, 10, size=horizon)
    return ForecastResult.from_forecast(
        point, quantile, start_date="2026-01-01", freq="D", metric=metric
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFromForecast:
    def test_extracts_single_series(self) -> None:
        point = np.random.rand(1, 30) * 5000
        quantile = np.random.rand(1, 30, 10) * 5000
        result = ForecastResult.from_forecast(
            point, quantile, start_date="2026-01-01", freq="D", metric="revenue"
        )
        assert result.point_forecast.shape == (30,)
        assert result.quantile_forecast is not None
        assert result.quantile_forecast.shape == (30, 10)
        assert len(result.dates) == 30
        assert "mean" in result.confidence_bands

    def test_generates_correct_dates(self) -> None:
        point = np.ones((1, 7))
        result = ForecastResult.from_forecast(
            point, None, start_date="2026-03-28", freq="D", metric="orders"
        )
        assert result.dates[0] == "2026-03-28"
        assert result.dates[-1] == "2026-04-03"

    def test_none_quantile_handled(self) -> None:
        point = np.ones((1, 14))
        result = ForecastResult.from_forecast(
            point, None, start_date="2026-01-01", freq="D", metric="revenue"
        )
        assert result.quantile_forecast is None
        assert result.confidence_bands == {}

    def test_metadata_populated(self) -> None:
        point = np.ones((1, 10))
        result = ForecastResult.from_forecast(
            point, None, start_date="2026-01-01", freq="D",
            metric="revenue", context_days=365, device="cpu"
        )
        assert result.metadata["metric"] == "revenue"
        assert result.metadata["horizon"] == 10
        assert result.metadata["context_days"] == 365
        assert result.metadata["device"] == "cpu"


class TestChannelZeroRegression:
    """Channel 0 of quantile output MUST be mean, not q10."""

    def test_channel_zero_is_mean(self) -> None:
        rng = np.random.default_rng(99)
        point = rng.uniform(100, 200, size=(1, 20))
        quantile = rng.uniform(50, 300, size=(1, 20, 10))
        # Make channel 0 distinctly different from channel 1
        quantile[0, :, 0] = point[0, :] * 1.01  # close to point
        quantile[0, :, 1] = point[0, :] * 0.5   # q10 much lower

        result = ForecastResult.from_forecast(
            point, quantile, start_date="2026-01-01", freq="D", metric="revenue"
        )
        assert np.allclose(
            result.confidence_bands["mean"],
            result.quantile_forecast[:, 0],
        ), "Channel 0 must map to 'mean' in confidence_bands"
        assert not np.allclose(
            result.confidence_bands["q10"],
            result.confidence_bands["mean"],
        ), "q10 and mean should be different channels"


class TestToTable:
    def test_returns_markdown(self) -> None:
        result = _make_result(30)
        table = result.to_table(period="weekly")
        assert table.startswith("|")
        assert "Period" in table or "Week" in table
        lines = table.strip().split("\n")
        # header + separator + at least 4 week rows + 1 partial
        assert len(lines) >= 6, f"Expected >= 6 lines, got {len(lines)}"

    def test_weekly_has_correct_buckets(self) -> None:
        result = _make_result(14)
        table = result.to_table(period="weekly")
        assert "Week 1" in table
        assert "Week 2" in table

    def test_monthly_period(self) -> None:
        result = _make_result(60)
        table = result.to_table(period="monthly")
        assert "Month 1" in table
        assert "Month 2" in table

    def test_currency_formatting(self) -> None:
        result = _make_result(7, metric="revenue")
        table = result.to_table()
        assert "$" in table

    def test_non_currency_metric(self) -> None:
        result = _make_result(7, metric="orders")
        table = result.to_table()
        # orders should not have $ prefix
        assert "$" not in table


class TestSummary:
    def test_includes_projection_and_ci(self) -> None:
        result = _make_result(30)
        summary = result.summary()
        assert "$" in summary
        assert "projected" in summary.lower()
        assert "90% CI" in summary

    def test_summary_with_trend(self) -> None:
        result = _make_result(30)
        summary = result.summary(prior_period_value=100000.0)
        assert "%" in summary
        assert "Trend" in summary or "trend" in summary

    def test_summary_no_trend_without_prior(self) -> None:
        result = _make_result(30)
        summary = result.summary()
        assert "Trend" not in summary

    def test_summary_non_empty(self) -> None:
        result = _make_result(7)
        summary = result.summary()
        assert len(summary) > 20

    def test_summary_with_zero_prior_omits_trend(self) -> None:
        result = _make_result(30)
        summary = result.summary(prior_period_value=0.0)
        assert "Trend" not in summary
