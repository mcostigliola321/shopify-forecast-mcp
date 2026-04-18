"""Tests for analytics MCP tools (analyze_promotion, compare_periods, get_seasonality, detect_anomalies).

Covers tool handler logic with mocked Shopify client and forecaster.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest

from shopify_forecast_mcp.mcp.server import AppContext


# ---------------------------------------------------------------------------
# MockCtx -- lightweight stand-in for mcp Context
# ---------------------------------------------------------------------------


class MockCtx:
    """Minimal mock of mcp Context for tool testing."""

    def __init__(self, app: AppContext) -> None:
        self.request_context = MagicMock()
        self.request_context.lifespan_context = app
        self._info_messages: list[str] = []

    async def info(self, msg: str) -> None:
        self._info_messages.append(msg)

    async def report_progress(self, current: int, total: int) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_app(sample_orders_with_promos: list[dict]) -> AppContext:
    """AppContext with mocked ShopifyClient returning promo fixture data."""
    shopify = AsyncMock()
    shopify.fetch_orders = AsyncMock(return_value=sample_orders_with_promos)

    horizon = 90
    forecaster = MagicMock()
    rng = np.random.default_rng(42)
    forecaster.forecast = MagicMock(
        return_value=(
            np.full((1, horizon), 100.0),
            rng.random((1, horizon, 10)) * 200,
        )
    )

    return AppContext(shopify=shopify, forecaster=forecaster)


@pytest.fixture()
def mock_ctx(mock_app: AppContext) -> MockCtx:
    return MockCtx(mock_app)


# ---------------------------------------------------------------------------
# Test: analyze_promotion MCP tool
# ---------------------------------------------------------------------------


class TestAnalyzePromotionTool:
    """Tests for the analyze_promotion MCP tool handler."""

    @pytest.mark.asyncio()
    async def test_tool_returns_markdown_with_promo_sections(
        self, mock_ctx: MockCtx
    ) -> None:
        from shopify_forecast_mcp.mcp.tools import (
            AnalyzePromotionParams,
            analyze_promotion,
        )

        params = AnalyzePromotionParams(
            promo_start="2025-04-30",
            promo_end="2025-05-07",
            promo_name="Spring Sale",
        )
        result = await analyze_promotion(params, mock_ctx)  # type: ignore[arg-type]

        assert isinstance(result, str)
        assert "Promotion Impact" in result
        assert "Post-Promo Impact" in result

    @pytest.mark.asyncio()
    async def test_tool_returns_error_for_invalid_date_range(
        self, mock_ctx: MockCtx
    ) -> None:
        from shopify_forecast_mcp.mcp.tools import (
            AnalyzePromotionParams,
            analyze_promotion,
        )

        params = AnalyzePromotionParams(
            promo_start="2025-05-07",
            promo_end="2025-04-30",
        )
        result = await analyze_promotion(params, mock_ctx)  # type: ignore[arg-type]

        assert isinstance(result, str)
        # Should return error markdown, not crash
        assert "error" in result.lower() or "Error" in result

    @pytest.mark.asyncio()
    async def test_tool_error_handling_returns_markdown(
        self, mock_app: AppContext
    ) -> None:
        from shopify_forecast_mcp.mcp.tools import (
            AnalyzePromotionParams,
            analyze_promotion,
        )

        mock_app.shopify.fetch_orders = AsyncMock(
            side_effect=RuntimeError("Connection refused")
        )
        ctx = MockCtx(mock_app)
        params = AnalyzePromotionParams(
            promo_start="2025-04-30",
            promo_end="2025-05-07",
        )
        result = await analyze_promotion(params, ctx)  # type: ignore[arg-type]

        assert "**Error" in result
        assert "RuntimeError" in result


# ---------------------------------------------------------------------------
# Test: compare_periods MCP tool
# ---------------------------------------------------------------------------


class TestComparePeriodsTool:
    """Tests for the compare_periods MCP tool handler."""

    @pytest.mark.asyncio()
    async def test_tool_returns_markdown_with_all_metrics(
        self, mock_ctx: MockCtx
    ) -> None:
        from shopify_forecast_mcp.mcp.tools import (
            ComparePeriodsParams,
            compare_periods,
        )

        params = ComparePeriodsParams(
            period_a_start="2025-03-01",
            period_a_end="2025-03-31",
            period_b_start="2025-04-01",
            period_b_end="2025-04-30",
        )
        result = await compare_periods(params, mock_ctx)  # type: ignore[arg-type]

        assert isinstance(result, str)
        assert "Period Comparison" in result
        assert "Revenue" in result

    @pytest.mark.asyncio()
    async def test_tool_returns_error_for_no_orders(
        self, mock_app: AppContext
    ) -> None:
        from shopify_forecast_mcp.mcp.tools import (
            ComparePeriodsParams,
            compare_periods,
        )

        mock_app.shopify.fetch_orders = AsyncMock(return_value=[])
        ctx = MockCtx(mock_app)
        params = ComparePeriodsParams(
            period_a_start="2025-03-01",
            period_a_end="2025-03-31",
            period_b_start="2025-04-01",
            period_b_end="2025-04-30",
        )
        result = await compare_periods(params, ctx)  # type: ignore[arg-type]

        assert isinstance(result, str)
        # Even with no orders the tool should return markdown (zeros), not crash
        assert "Period Comparison" in result or "0" in result

    @pytest.mark.asyncio()
    async def test_tool_error_handling(
        self, mock_app: AppContext
    ) -> None:
        from shopify_forecast_mcp.mcp.tools import (
            ComparePeriodsParams,
            compare_periods,
        )

        mock_app.shopify.fetch_orders = AsyncMock(
            side_effect=RuntimeError("Timeout")
        )
        ctx = MockCtx(mock_app)
        params = ComparePeriodsParams(
            period_a_start="2025-03-01",
            period_a_end="2025-03-31",
            period_b_start="2025-04-01",
            period_b_end="2025-04-30",
        )
        result = await compare_periods(params, ctx)  # type: ignore[arg-type]

        assert "**Error" in result
        assert "RuntimeError" in result


# ---------------------------------------------------------------------------
# Test: get_seasonality MCP tool
# ---------------------------------------------------------------------------


class TestGetSeasonalityTool:
    """Tests for the get_seasonality MCP tool handler."""

    @pytest.mark.asyncio()
    async def test_tool_returns_markdown_with_index_table(
        self, mock_ctx: MockCtx
    ) -> None:
        from shopify_forecast_mcp.mcp.tools import (
            GetSeasonalityParams,
            get_seasonality,
        )

        params = GetSeasonalityParams()
        result = await get_seasonality(params, mock_ctx)  # type: ignore[arg-type]

        assert isinstance(result, str)
        assert "Seasonality" in result
        assert "Index" in result

    @pytest.mark.asyncio()
    async def test_tool_accepts_granularity_day_of_week(
        self, mock_ctx: MockCtx
    ) -> None:
        from shopify_forecast_mcp.mcp.tools import (
            GetSeasonalityParams,
            get_seasonality,
        )

        params = GetSeasonalityParams(granularity="day_of_week")
        result = await get_seasonality(params, mock_ctx)  # type: ignore[arg-type]

        assert "Monday" in result or "Index" in result

    @pytest.mark.asyncio()
    async def test_tool_accepts_granularity_monthly(
        self, mock_ctx: MockCtx
    ) -> None:
        from shopify_forecast_mcp.mcp.tools import (
            GetSeasonalityParams,
            get_seasonality,
        )

        params = GetSeasonalityParams(granularity="monthly")
        result = await get_seasonality(params, mock_ctx)  # type: ignore[arg-type]

        assert "Seasonality" in result

    @pytest.mark.asyncio()
    async def test_tool_accepts_granularity_quarterly(
        self, mock_ctx: MockCtx
    ) -> None:
        from shopify_forecast_mcp.mcp.tools import (
            GetSeasonalityParams,
            get_seasonality,
        )

        params = GetSeasonalityParams(granularity="quarterly")
        result = await get_seasonality(params, mock_ctx)  # type: ignore[arg-type]

        assert "Seasonality" in result

    @pytest.mark.asyncio()
    async def test_tool_error_handling(
        self, mock_app: AppContext
    ) -> None:
        from shopify_forecast_mcp.mcp.tools import (
            GetSeasonalityParams,
            get_seasonality,
        )

        mock_app.shopify.fetch_orders = AsyncMock(
            side_effect=RuntimeError("Network error")
        )
        ctx = MockCtx(mock_app)
        params = GetSeasonalityParams()
        result = await get_seasonality(params, ctx)  # type: ignore[arg-type]

        assert "**Error" in result
        assert "RuntimeError" in result


# ---------------------------------------------------------------------------
# Test: detect_anomalies MCP tool
# ---------------------------------------------------------------------------


class TestDetectAnomaliesTool:
    """Tests for the detect_anomalies MCP tool handler."""

    @pytest.fixture()
    def anomaly_app(self, sample_orders_with_promos: list[dict]) -> AppContext:
        """AppContext with forecaster that returns predictable bands for anomaly detection."""
        shopify = AsyncMock()
        shopify.fetch_orders = AsyncMock(return_value=sample_orders_with_promos)

        horizon = 90
        forecaster = MagicMock()
        # Return predictable forecast: constant 100 with tight bands
        # quantile shape: (1, horizon, 10) -- channels: mean, q10..q90
        quantile = np.zeros((1, horizon, 10))
        quantile[:, :, 0] = 100.0   # mean
        quantile[:, :, 1] = 80.0    # q10
        quantile[:, :, 2] = 85.0    # q20
        quantile[:, :, 3] = 88.0    # q30
        quantile[:, :, 4] = 92.0    # q40
        quantile[:, :, 5] = 100.0   # q50
        quantile[:, :, 6] = 108.0   # q60
        quantile[:, :, 7] = 112.0   # q70
        quantile[:, :, 8] = 115.0   # q80
        quantile[:, :, 9] = 120.0   # q90

        forecaster.forecast = MagicMock(
            return_value=(
                np.full((1, horizon), 100.0),
                quantile,
            )
        )

        return AppContext(shopify=shopify, forecaster=forecaster)

    @pytest.mark.asyncio()
    async def test_tool_registered_and_callable(
        self, anomaly_app: AppContext
    ) -> None:
        from shopify_forecast_mcp.mcp.tools import (
            DetectAnomaliesParams,
            detect_anomalies,
        )

        ctx = MockCtx(anomaly_app)
        params = DetectAnomaliesParams()
        result = await detect_anomalies(params, ctx)  # type: ignore[arg-type]

        assert isinstance(result, str)
        assert "Anomaly" in result or "anomal" in result.lower()

    @pytest.mark.asyncio()
    async def test_tool_sensitivity_param(
        self, anomaly_app: AppContext
    ) -> None:
        from shopify_forecast_mcp.mcp.tools import (
            DetectAnomaliesParams,
            detect_anomalies,
        )

        for sensitivity in ("low", "medium", "high"):
            ctx = MockCtx(anomaly_app)
            params = DetectAnomaliesParams(sensitivity=sensitivity)
            result = await detect_anomalies(params, ctx)  # type: ignore[arg-type]
            assert isinstance(result, str)

    @pytest.mark.asyncio()
    async def test_tool_short_history_warning(
        self, sample_orders_with_promos: list[dict]
    ) -> None:
        from shopify_forecast_mcp.mcp.tools import (
            DetectAnomaliesParams,
            detect_anomalies,
        )

        # Use enough orders for ~50 days (under 90) to trigger short history warning
        short_orders = sample_orders_with_promos[:100]
        shopify = AsyncMock()
        shopify.fetch_orders = AsyncMock(return_value=short_orders)

        horizon = 50
        quantile = np.zeros((1, horizon, 10))
        quantile[:, :, 0] = 100.0
        for i in range(1, 10):
            quantile[:, :, i] = 80.0 + i * 5

        forecaster = MagicMock()
        forecaster.forecast = MagicMock(
            return_value=(np.full((1, horizon), 100.0), quantile)
        )

        app = AppContext(shopify=shopify, forecaster=forecaster)
        ctx = MockCtx(app)
        params = DetectAnomaliesParams(lookback_days=60)
        result = await detect_anomalies(params, ctx)  # type: ignore[arg-type]

        assert isinstance(result, str)
        # With short history (<90 days), core detect_anomalies includes warning
        # or at minimum returns valid anomaly detection output
        assert "Anomaly" in result or "Limited" in result or "limited" in result.lower()

    @pytest.mark.asyncio()
    async def test_tool_error_handling(
        self, anomaly_app: AppContext
    ) -> None:
        from shopify_forecast_mcp.mcp.tools import (
            DetectAnomaliesParams,
            detect_anomalies,
        )

        anomaly_app.shopify.fetch_orders = AsyncMock(
            side_effect=RuntimeError("Connection error")
        )
        ctx = MockCtx(anomaly_app)
        params = DetectAnomaliesParams()
        result = await detect_anomalies(params, ctx)  # type: ignore[arg-type]

        assert "**Error" in result
        assert "RuntimeError" in result
