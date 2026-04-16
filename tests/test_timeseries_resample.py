"""Tests for resample_series and clean_series in core/timeseries.py."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from shopify_forecast_mcp.core.timeseries import clean_series, resample_series


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def daily_revenue_90d() -> pd.Series:
    """90 days of daily revenue starting 2024-01-01, each day = 100.0."""
    dates = pd.date_range("2024-01-01", periods=90, freq="D")
    return pd.Series(100.0, index=dates)


@pytest.fixture()
def daily_aov_90d() -> pd.Series:
    """90 days of daily AOV starting 2024-01-01, each day = 50.0."""
    dates = pd.date_range("2024-01-01", periods=90, freq="D")
    return pd.Series(50.0, index=dates)


@pytest.fixture()
def series_with_outlier() -> pd.Series:
    """100-day series, normal values ~100, one outlier at index 50 = 10000."""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    values = rng.normal(loc=100, scale=10, size=100)
    values[50] = 10000.0  # extreme outlier
    return pd.Series(values, index=dates)


@pytest.fixture()
def series_with_gaps() -> pd.Series:
    """100-day series with NaN gaps at indices 20, 21, 22."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    values = np.full(100, 100.0)
    values[20] = np.nan
    values[21] = np.nan
    values[22] = np.nan
    return pd.Series(values, index=dates)


# ---------------------------------------------------------------------------
# resample_series tests
# ---------------------------------------------------------------------------

class TestResampleSeries:
    """Tests for resample_series."""

    def test_daily_to_weekly_revenue_sums(self, daily_revenue_90d: pd.Series) -> None:
        """Weekly resample of revenue uses sum: 7 * 100 = 700 for full weeks."""
        result = resample_series(daily_revenue_90d, freq="W", metric="revenue")
        # 90 days -> 13 weekly buckets (weeks ending Sun)
        assert len(result) == 13
        # All full interior weeks should sum to 700
        # The first and last week may be partial, but most should be 700
        full_weeks = result[(result == 700.0)]
        assert len(full_weeks) >= 10, f"Expected at least 10 full weeks of 700, got {len(full_weeks)}"

    def test_daily_to_weekly_aov_means(self, daily_aov_90d: pd.Series) -> None:
        """Weekly resample of aov uses mean: mean of 50.0 = 50.0."""
        result = resample_series(daily_aov_90d, freq="W", metric="aov")
        assert len(result) == 13
        # Mean of constant 50.0 should stay 50.0
        assert all(result == 50.0), f"Expected all values to be 50.0, got {result.values}"

    def test_daily_to_monthly(self, daily_revenue_90d: pd.Series) -> None:
        """Monthly resample of 90 days -> 3 monthly buckets."""
        result = resample_series(daily_revenue_90d, freq="M", metric="revenue")
        assert len(result) == 3
        # Jan has 31 days, Feb has 29 (2024 is leap year), Mar has 30 remaining
        assert result.iloc[0] == 31 * 100.0  # January
        assert result.iloc[1] == 29 * 100.0  # February (2024 leap year)
        assert result.iloc[2] == 30 * 100.0  # March (only 30 days in our 90-day range)

    def test_daily_passthrough(self, daily_revenue_90d: pd.Series) -> None:
        """freq='D' returns series unchanged."""
        result = resample_series(daily_revenue_90d, freq="D", metric="revenue")
        pd.testing.assert_series_equal(result, daily_revenue_90d)


# ---------------------------------------------------------------------------
# clean_series tests
# ---------------------------------------------------------------------------

class TestCleanSeries:
    """Tests for clean_series."""

    def test_iqr_caps_outlier(self, series_with_outlier: pd.Series) -> None:
        """IQR method caps the extreme outlier, value should be <= upper bound."""
        result = clean_series(series_with_outlier, remove_outliers=True, outlier_method="iqr")
        q1 = series_with_outlier.quantile(0.25)
        q3 = series_with_outlier.quantile(0.75)
        iqr = q3 - q1
        upper = q3 + 1.5 * iqr
        # The outlier at index 50 should be capped
        assert result.iloc[50] <= upper + 0.01, (
            f"Outlier not capped: {result.iloc[50]} > {upper}"
        )
        assert result.iloc[50] < series_with_outlier.iloc[50]

    def test_zscore_caps_outlier(self, series_with_outlier: pd.Series) -> None:
        """zscore method caps outlier to mean + 3*std."""
        result = clean_series(series_with_outlier, remove_outliers=True, outlier_method="zscore")
        mean = series_with_outlier.mean()
        std = series_with_outlier.std()
        upper = mean + 3 * std
        assert result.iloc[50] <= upper + 0.01, (
            f"Outlier not capped: {result.iloc[50]} > {upper}"
        )
        assert result.iloc[50] < series_with_outlier.iloc[50]

    def test_preserves_length(self, series_with_outlier: pd.Series) -> None:
        """CRITICAL: clean_series never drops points (TimesFM continuity)."""
        result = clean_series(series_with_outlier, remove_outliers=True, outlier_method="iqr")
        assert len(result) == len(series_with_outlier)

    def test_interpolate_gaps(self, series_with_gaps: pd.Series) -> None:
        """interpolate_gaps=True fills NaN via linear interpolation."""
        result = clean_series(
            series_with_gaps,
            remove_outliers=False,
            interpolate_gaps=True,
        )
        # No NaN should remain
        assert not result.isna().any(), f"NaN values remain: {result[result.isna()]}"
        # Interpolated values should be 100.0 (linear between 100 and 100)
        assert result.iloc[20] == pytest.approx(100.0)
        assert result.iloc[21] == pytest.approx(100.0)
        assert result.iloc[22] == pytest.approx(100.0)

    def test_remove_outliers_false_passthrough(self, series_with_outlier: pd.Series) -> None:
        """remove_outliers=False returns series unchanged."""
        result = clean_series(series_with_outlier, remove_outliers=False)
        pd.testing.assert_series_equal(result, series_with_outlier)

    def test_no_outliers_unchanged(self) -> None:
        """Series with no outliers is returned unchanged by IQR cleaning."""
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        values = np.full(100, 100.0)
        series = pd.Series(values, index=dates)
        result = clean_series(series, remove_outliers=True, outlier_method="iqr")
        pd.testing.assert_series_equal(result, series)
