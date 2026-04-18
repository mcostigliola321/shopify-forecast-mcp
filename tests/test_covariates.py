"""Tests for covariate engineering module and XReg integration.

Covers all 7 built-in covariates, custom events, future covariates,
aligned covariate building for TimesFM XReg integration, feature flag,
and ForecastEngine.forecast_with_covariates().
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from shopify_forecast_mcp.core.covariates import (
    build_aligned_covariates,
    build_covariates,
    build_future_covariates,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_simple_order(
    order_id: str,
    local_date: str,
    subtotal: float = 100.0,
    total_discounts: float = 0.0,
    discount_codes: list | None = None,
) -> dict:
    """Build a minimal normalized order dict for covariate testing."""
    return {
        "id": order_id,
        "created_at": f"{local_date}T10:00:00Z",
        "local_date": local_date,
        "financial_status": "PAID",
        "subtotal": subtotal,
        "current_subtotal": subtotal - total_discounts,
        "total_discounts": total_discounts,
        "total_refunded": 0.0,
        "net_payment": subtotal - total_discounts,
        "currency": "USD",
        "discount_codes": discount_codes or [],
        "tags": [],
        "source_name": "",
        "test": False,
        "cancelled_at": None,
        "customer_id": "C1",
        "line_items": [],
    }


# ---------------------------------------------------------------------------
# Test 1: build_covariates returns dict with 7 keys
# ---------------------------------------------------------------------------

class TestBuildCovariatesKeys:
    def test_returns_seven_builtin_keys(self):
        date_range = pd.date_range("2025-12-22", "2025-12-28", freq="D")
        result = build_covariates(date_range, orders=[])
        expected_keys = {
            "day_of_week", "is_weekend", "month",
            "is_holiday", "holiday_proximity",
            "has_discount", "discount_depth",
        }
        assert set(result.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Test 2: Each covariate is list[list[float]] with correct length
# ---------------------------------------------------------------------------

class TestCovariateShape:
    def test_each_value_is_nested_list_with_correct_length(self):
        date_range = pd.date_range("2025-12-22", "2025-12-28", freq="D")
        result = build_covariates(date_range, orders=[])
        for key, val in result.items():
            assert isinstance(val, list), f"{key} should be a list"
            assert len(val) == 1, f"{key} should have batch dim of 1"
            assert len(val[0]) == len(date_range), (
                f"{key} inner list length {len(val[0])} != date_range length {len(date_range)}"
            )


# ---------------------------------------------------------------------------
# Test 3: day_of_week normalized 0-1 (Monday=0.0, Sunday=1.0)
# ---------------------------------------------------------------------------

class TestDayOfWeek:
    def test_monday_is_zero_sunday_is_one(self):
        # 2025-12-22 is Monday, 2025-12-28 is Sunday
        date_range = pd.date_range("2025-12-22", "2025-12-28", freq="D")
        result = build_covariates(date_range, orders=[])
        dow = result["day_of_week"][0]
        assert dow[0] == pytest.approx(0.0)         # Monday
        assert dow[1] == pytest.approx(1 / 6)        # Tuesday
        assert dow[6] == pytest.approx(1.0)           # Sunday


# ---------------------------------------------------------------------------
# Test 4: is_weekend returns 1.0 for Sat/Sun, 0.0 otherwise
# ---------------------------------------------------------------------------

class TestIsWeekend:
    def test_weekend_detection(self):
        # Mon through Sun
        date_range = pd.date_range("2025-12-22", "2025-12-28", freq="D")
        result = build_covariates(date_range, orders=[])
        weekend = result["is_weekend"][0]
        # Mon=0, Tue=0, Wed=0, Thu=0, Fri=0, Sat=1, Sun=1
        assert weekend[:5] == [0.0, 0.0, 0.0, 0.0, 0.0]
        assert weekend[5:] == [1.0, 1.0]


# ---------------------------------------------------------------------------
# Test 5: is_holiday returns 1.0 for known US holidays
# ---------------------------------------------------------------------------

class TestIsHoliday:
    def test_christmas_detected(self):
        date_range = pd.date_range("2025-12-24", "2025-12-26", freq="D")
        result = build_covariates(date_range, orders=[], country="US")
        hol = result["is_holiday"][0]
        # Dec 25 is Christmas
        assert hol[1] == 1.0  # Dec 25
        assert hol[0] == 0.0  # Dec 24 (Christmas Eve is not a federal holiday)


# ---------------------------------------------------------------------------
# Test 6: holiday_proximity values in normalized range
# ---------------------------------------------------------------------------

class TestHolidayProximity:
    def test_proximity_zero_on_holiday(self):
        date_range = pd.date_range("2025-12-24", "2025-12-26", freq="D")
        result = build_covariates(date_range, orders=[], country="US")
        prox = result["holiday_proximity"][0]
        # Dec 25 is on holiday -> proximity value should be 0.0
        assert prox[1] == pytest.approx(0.0)

    def test_proximity_nonzero_near_holiday(self):
        # Dec 20 is 5 days before Christmas -> within [-7, +3] window
        date_range = pd.date_range("2025-12-20", "2025-12-20", freq="D")
        result = build_covariates(date_range, orders=[], country="US")
        prox = result["holiday_proximity"][0]
        assert prox[0] != 0.0  # Should have non-zero proximity


# ---------------------------------------------------------------------------
# Test 7: has_discount returns 1.0 for dates with discounted orders
# ---------------------------------------------------------------------------

class TestHasDiscount:
    def test_discount_detection(self):
        orders = [
            _make_simple_order("1", "2025-12-22", discount_codes=[{"code": "SAVE10"}]),
            _make_simple_order("2", "2025-12-23"),  # no discount
        ]
        date_range = pd.date_range("2025-12-22", "2025-12-24", freq="D")
        result = build_covariates(date_range, orders)
        has_disc = result["has_discount"][0]
        assert has_disc[0] == 1.0  # Dec 22 has discount
        assert has_disc[1] == 0.0  # Dec 23 no discount
        assert has_disc[2] == 0.0  # Dec 24 no orders


# ---------------------------------------------------------------------------
# Test 8: discount_depth returns average discount ratio
# ---------------------------------------------------------------------------

class TestDiscountDepth:
    def test_depth_calculation(self):
        orders = [
            _make_simple_order("1", "2025-12-22", subtotal=100.0, total_discounts=20.0,
                               discount_codes=[{"code": "SAVE20"}]),
        ]
        date_range = pd.date_range("2025-12-22", "2025-12-23", freq="D")
        result = build_covariates(date_range, orders)
        depth = result["discount_depth"][0]
        assert depth[0] == pytest.approx(0.2)  # 20/100
        assert depth[1] == pytest.approx(0.0)  # no orders on Dec 23


# ---------------------------------------------------------------------------
# Test 9: custom_events add a covariate
# ---------------------------------------------------------------------------

class TestCustomEvents:
    def test_custom_event_date_gets_one(self):
        events = [{"date": "2025-12-23", "label": "Flash Sale", "type": "promo"}]
        date_range = pd.date_range("2025-12-22", "2025-12-24", freq="D")
        result = build_covariates(date_range, orders=[], custom_events=events)
        assert "custom_event" in result
        ce = result["custom_event"][0]
        assert ce[1] == 1.0  # Dec 23 is the event date

    def test_custom_event_proximity_decay(self):
        events = [{"date": "2025-12-23", "label": "Flash Sale", "type": "promo"}]
        date_range = pd.date_range("2025-12-22", "2025-12-24", freq="D")
        result = build_covariates(date_range, orders=[], custom_events=events)
        ce = result["custom_event"][0]
        # Adjacent days should have some proximity value (not zero, not one)
        assert 0.0 < ce[0] < 1.0  # Dec 22 is 1 day before
        assert 0.0 < ce[2] < 1.0  # Dec 24 is 1 day after


# ---------------------------------------------------------------------------
# Test 10: build_future_covariates
# ---------------------------------------------------------------------------

class TestBuildFutureCovariates:
    def test_returns_deterministic_covariates_for_horizon(self):
        last_date = pd.Timestamp("2025-12-24")
        result = build_future_covariates(horizon=7, last_date=last_date, country="US")
        assert "day_of_week" in result
        assert "is_holiday" in result
        # Should have 7 values
        assert len(result["day_of_week"][0]) == 7

    def test_planned_promos_set_discount_flags(self):
        last_date = pd.Timestamp("2025-12-24")
        promos = [{"start": "2025-12-26", "end": "2025-12-27", "depth": 0.15}]
        result = build_future_covariates(
            horizon=7, last_date=last_date, country="US", planned_promos=promos
        )
        has_disc = result["has_discount"][0]
        depth = result["discount_depth"][0]
        # Dec 25 (index 0) no promo, Dec 26 (index 1) promo, Dec 27 (index 2) promo
        assert has_disc[0] == 0.0
        assert has_disc[1] == 1.0
        assert has_disc[2] == 1.0
        assert depth[1] == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# Test 11: build_aligned_covariates
# ---------------------------------------------------------------------------

class TestBuildAlignedCovariates:
    def test_aligned_covariates_span_context_plus_horizon(self):
        context_dates = pd.date_range("2025-12-01", "2025-12-24", freq="D")
        horizon = 7
        result = build_aligned_covariates(context_dates, horizon=horizon, orders=[])
        expected_len = len(context_dates) + horizon
        for key, val in result.items():
            assert len(val[0]) == expected_len, (
                f"{key} length {len(val[0])} != expected {expected_len}"
            )


# ===========================================================================
# Task 2 tests: Settings feature flag + ForecastEngine.forecast_with_covariates
# ===========================================================================


class TestCovariatesFeatureFlag:
    def test_settings_has_covariates_enabled_default_false(self):
        from shopify_forecast_mcp.config import Settings
        s = Settings(
            shop="test.myshopify.com",
            access_token="shpat_test",
            _env_file=None,
        )
        assert s.covariates_enabled is False

    def test_env_var_enables_covariates(self, monkeypatch):
        from shopify_forecast_mcp.config import Settings
        monkeypatch.setenv("SHOPIFY_FORECAST_COVARIATES_ENABLED", "true")
        s = Settings(
            shop="test.myshopify.com",
            access_token="shpat_test",
            _env_file=None,
        )
        assert s.covariates_enabled is True


class TestForecastWithCovariates:
    def test_method_exists_on_forecast_engine(self):
        from shopify_forecast_mcp.core.forecaster import ForecastEngine
        assert hasattr(ForecastEngine, "forecast_with_covariates")

    @patch("shopify_forecast_mcp.core.forecaster.timesfm")
    def test_returns_tuple_of_ndarrays(self, mock_timesfm):
        from shopify_forecast_mcp.core.forecaster import ForecastEngine

        # Set up mock model
        mock_model = MagicMock()
        mock_model.forecast_with_covariates.return_value = (
            np.array([[1.0, 2.0, 3.0]]),
            np.array([[[0.1] * 10, [0.2] * 10, [0.3] * 10]]),
        )

        engine = ForecastEngine.__new__(ForecastEngine)
        engine._model = mock_model
        engine._xreg_compiled = True
        engine.context_length = 1024
        engine.default_horizon = 3
        engine.device = "cpu"

        series = np.array([10.0, 20.0, 30.0])
        covariates = {"day_of_week": [[0.0, 0.1, 0.2, 0.3, 0.4, 0.5]]}

        point, quantile = engine.forecast_with_covariates(series, covariates, horizon=3)
        assert isinstance(point, np.ndarray)
        assert isinstance(quantile, np.ndarray)

    @patch("shopify_forecast_mcp.core.forecaster.timesfm")
    def test_calls_ensure_xreg_compiled(self, mock_timesfm):
        from shopify_forecast_mcp.core.forecaster import ForecastEngine

        mock_model = MagicMock()
        mock_model.forecast_with_covariates.return_value = (
            np.array([[1.0]]),
            np.array([[[0.1] * 10]]),
        )

        engine = ForecastEngine.__new__(ForecastEngine)
        engine._model = mock_model
        engine._xreg_compiled = False
        engine.context_length = 1024
        engine.default_horizon = 1
        engine.device = "cpu"

        series = np.array([10.0])
        covariates = {"day_of_week": [[0.0, 0.1]]}

        engine.forecast_with_covariates(series, covariates, horizon=1)
        # After calling forecast_with_covariates, _xreg_compiled should be True
        assert engine._xreg_compiled is True

    @patch("shopify_forecast_mcp.core.forecaster.timesfm")
    def test_delegates_to_model_forecast_with_covariates(self, mock_timesfm):
        from shopify_forecast_mcp.core.forecaster import ForecastEngine

        mock_model = MagicMock()
        mock_model.forecast_with_covariates.return_value = (
            np.array([[1.0, 2.0]]),
            np.array([[[0.1] * 10, [0.2] * 10]]),
        )

        engine = ForecastEngine.__new__(ForecastEngine)
        engine._model = mock_model
        engine._xreg_compiled = True
        engine.context_length = 1024
        engine.default_horizon = 2
        engine.device = "cpu"

        series = np.array([10.0, 20.0, 30.0])
        covariates = {"day_of_week": [[0.0, 0.1, 0.2, 0.3, 0.4]]}

        engine.forecast_with_covariates(series, covariates, horizon=2)
        mock_model.forecast_with_covariates.assert_called_once()
        call_kwargs = mock_model.forecast_with_covariates.call_args
        assert "dynamic_numerical_covariates" in call_kwargs.kwargs or len(call_kwargs.args) >= 2

    def test_covariates_disclaimer_exists(self):
        from shopify_forecast_mcp.core.forecaster import COVARIATES_DISCLAIMER
        assert "marginal" in COVARIATES_DISCLAIMER.lower()

    @patch("shopify_forecast_mcp.core.forecaster.timesfm")
    def test_recompiles_with_return_backcast_on_first_call(self, mock_timesfm):
        from shopify_forecast_mcp.core.forecaster import ForecastEngine

        mock_model = MagicMock()
        mock_model.forecast_with_covariates.return_value = (
            np.array([[1.0]]),
            np.array([[[0.1] * 10]]),
        )

        engine = ForecastEngine.__new__(ForecastEngine)
        engine._model = mock_model
        engine._xreg_compiled = False
        engine.context_length = 1024
        engine.default_horizon = 1
        engine.device = "cpu"

        series = np.array([10.0])
        covariates = {"day_of_week": [[0.0, 0.1]]}

        engine.forecast_with_covariates(series, covariates, horizon=1)

        # Verify model.compile was called with return_backcast=True
        mock_model.compile.assert_called_once()
        config_arg = mock_model.compile.call_args[0][0]
        # The ForecastConfig should have return_backcast=True
        mock_timesfm.ForecastConfig.assert_called_once()
        fc_kwargs = mock_timesfm.ForecastConfig.call_args.kwargs
        assert fc_kwargs.get("return_backcast") is True
