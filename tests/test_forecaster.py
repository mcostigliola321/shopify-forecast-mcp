"""Tests for ForecastEngine -- TimesFM 2.5 singleton wrapper.

All tests are marked ``@pytest.mark.slow`` because they load the ~400 MB
TimesFM model (downloaded on first run, cached afterwards).
"""

from __future__ import annotations

import logging

import numpy as np
import pytest

import shopify_forecast_mcp.core.forecaster as forecaster_mod
from shopify_forecast_mcp.core.forecaster import ForecastEngine, get_engine

pytestmark = pytest.mark.slow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the module-level singleton before each test."""
    original = forecaster_mod._engine
    forecaster_mod._engine = None
    yield
    forecaster_mod._engine = original


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSingleton:
    """Verify singleton pattern for get_engine()."""

    def test_singleton_returns_same_instance(self) -> None:
        engine1 = get_engine()
        engine2 = get_engine()
        assert engine1 is engine2


class TestDeviceDetection:
    """Verify device is always cpu or cuda (never mps)."""

    def test_device_is_cpu_or_cuda(self) -> None:
        engine = get_engine()
        assert engine.device in ("cpu", "cuda")


class TestFirstRunLog:
    """Verify the first-run download log message is emitted."""

    def test_first_run_log_message(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="shopify_forecast_mcp.core.forecaster"):
            engine = get_engine()
            engine.load()
        assert "Downloading TimesFM 2.5" in caplog.text


class TestSineWaveForecast:
    """Smoke test: forecast a sine wave and verify reasonable output."""

    def test_sine_wave_forecast(self) -> None:
        # Generate a clean sine wave as context
        context = np.sin(np.linspace(0, 20 * np.pi, 500))
        horizon = 50

        engine = get_engine()
        point, quantile = engine.forecast(context, horizon=horizon)

        # Shape checks
        assert point.shape == (1, horizon)
        assert quantile.shape == (1, horizon, 10)

        # Expected continuation of the sine wave
        # The context ends at 20*pi; the next 50 steps continue the linspace
        step = (20 * np.pi) / 499  # step size from linspace
        expected = np.sin(
            np.linspace(20 * np.pi + step, 20 * np.pi + step * horizon, horizon)
        )

        # MAE should be reasonable (< 0.5 is generous for a foundation model)
        mae = np.mean(np.abs(point[0] - expected))
        assert mae < 0.5, f"Sine-wave MAE too high: {mae:.4f}"

        # At least 80% of true values should fall within q10-q90 bands
        q10 = quantile[0, :, 1]  # channel 1 = q10
        q90 = quantile[0, :, 9]  # channel 9 = q90
        within_bands = np.sum((expected >= q10) & (expected <= q90))
        coverage = within_bands / horizon
        assert coverage >= 0.8, f"Quantile coverage too low: {coverage:.2%}"


class TestChannelZeroIsMean:
    """Regression guard: channel 0 of quantile output is mean, not q10."""

    def test_channel_zero_is_mean(self) -> None:
        context = np.sin(np.linspace(0, 20 * np.pi, 500))
        engine = get_engine()
        point, quantile = engine.forecast(context, horizon=50)

        # Channel 0 should match the point forecast (both are the mean)
        np.testing.assert_allclose(
            quantile[0, :, 0],
            point[0, :],
            atol=0.1,
            err_msg="Channel 0 should be mean, not q10",
        )


class TestBatchForecast:
    """Verify batch mode with multiple input series."""

    def test_batch_forecast(self) -> None:
        s1 = np.sin(np.linspace(0, 10 * np.pi, 200))  # sine
        s2 = np.linspace(0, 100, 200)                   # linear ramp
        s3 = np.full(200, 42.0)                          # constant

        engine = get_engine()
        horizon = 30
        point, quantile = engine.forecast([s1, s2, s3], horizon=horizon)

        assert point.shape == (3, horizon)
        assert quantile.shape == (3, horizon, 10)
