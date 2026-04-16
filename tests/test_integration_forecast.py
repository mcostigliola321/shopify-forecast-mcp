"""Integration tests for the full forecast pipeline.

All tests in this module require TimesFM (~400MB model download)
and are marked ``@pytest.mark.slow``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from shopify_forecast_mcp.core.forecast_result import ForecastResult
from shopify_forecast_mcp.core.forecaster import get_engine
from shopify_forecast_mcp.core.timeseries import orders_to_daily_series

FIXTURES = Path(__file__).resolve().parent / "fixtures"

pytestmark = pytest.mark.slow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_orders() -> list[dict]:
    return json.loads((FIXTURES / "sample_orders.json").read_text())


def _load_revenue_series() -> pd.Series:
    df = pd.read_csv(FIXTURES / "sample_daily_revenue.csv", parse_dates=["date"])
    return pd.Series(df["revenue"].values, index=df["date"], name="revenue")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOrdersToForecastPipeline:
    """End-to-end: orders -> daily series -> forecast -> ForecastResult."""

    def test_orders_to_forecast_pipeline(self) -> None:
        orders = _load_orders()
        series_dict = orders_to_daily_series(orders, metric="revenue")
        series = series_dict["store"]

        # Validate series properties
        assert isinstance(series.index, pd.DatetimeIndex)
        assert not series.isna().any(), "Series should have no NaN (zero-filled)"

        engine = get_engine()
        point, quantile = engine.forecast(series.values, horizon=30)

        result = ForecastResult.from_forecast(
            point, quantile,
            start_date=series.index[-1] + pd.Timedelta(days=1),
            freq="D", metric="revenue",
        )

        # Validate result
        assert result.point_forecast.shape == (30,)
        assert not np.any(np.isnan(result.point_forecast))
        assert not np.any(np.isinf(result.point_forecast))

        # Presentation methods produce output
        table = result.to_table()
        assert table.startswith("|")
        assert len(table) > 50

        summary = result.summary()
        assert len(summary) > 20
        assert "$" in summary or "projected" in summary.lower()


class TestCSVFixtureToForecast:
    """Load 365-day CSV, forecast, verify ForecastResult."""

    def test_csv_fixture_to_forecast(self) -> None:
        series = _load_revenue_series()
        assert len(series) == 365

        engine = get_engine()
        point, quantile = engine.forecast(series.values, horizon=30)

        assert point.shape[1] == 30
        assert quantile.shape[1] == 30
        assert quantile.shape[2] == 10

        result = ForecastResult.from_forecast(
            point, quantile,
            start_date=series.index[-1] + pd.Timedelta(days=1),
            freq="D", metric="revenue",
        )
        assert "$" in result.summary()


class TestPerformance:
    """Forecast performance: 365-day context / 30-day horizon < 10s on CPU."""

    def test_performance_1yr_30d(self) -> None:
        series = _load_revenue_series()
        engine = get_engine()

        # Warm up (model may already be loaded from earlier tests)
        engine.load()

        start = time.perf_counter()
        engine.forecast(series.values, horizon=30)
        elapsed = time.perf_counter() - start

        assert elapsed < 10.0, (
            f"Forecast took {elapsed:.1f}s, expected <10s on CPU"
        )


class TestChannelZeroRegression:
    """Channel 0 of quantile output from real model should be close to point forecast."""

    def test_channel_zero_close_to_point(self) -> None:
        series = _load_revenue_series()
        engine = get_engine()
        point, quantile = engine.forecast(series.values, horizon=30)

        result = ForecastResult.from_forecast(
            point, quantile,
            start_date="2026-04-01", freq="D", metric="revenue",
        )

        # Channel 0 (mean) should be close to point forecast
        assert result.quantile_forecast is not None
        mean_channel = result.quantile_forecast[:, 0]
        np.testing.assert_allclose(
            mean_channel, result.point_forecast,
            rtol=0.15,
            err_msg="Channel 0 (mean) should be close to point forecast",
        )


class TestGroupedForecast:
    """Forecast by product_id grouping."""

    def test_grouped_forecast(self) -> None:
        orders = _load_orders()
        series_dict = orders_to_daily_series(
            orders, metric="revenue", group_by="product_id"
        )
        assert len(series_dict) > 0, "Should have at least one product group"

        # Pick the first product series
        first_key = next(iter(series_dict))
        series = series_dict[first_key]

        engine = get_engine()
        point, quantile = engine.forecast(series.values, horizon=30)

        result = ForecastResult.from_forecast(
            point, quantile,
            start_date=series.index[-1] + pd.Timedelta(days=1),
            freq="D", metric="revenue",
            group=first_key,
        )

        assert result.point_forecast.shape == (30,)
        assert not np.any(np.isnan(result.point_forecast))
        assert result.metadata["group"] == first_key
