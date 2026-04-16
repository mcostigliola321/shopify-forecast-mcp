"""Tests for the forecast_revenue MCP tool.

Covers Pydantic input validation and tool handler logic with
mocked Shopify client and forecaster.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from pydantic import ValidationError

from shopify_forecast_mcp.mcp.server import AppContext
from shopify_forecast_mcp.mcp.tools import ForecastRevenueParams, forecast_revenue


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
def mock_app(normalized_orders: list[dict]) -> AppContext:
    """AppContext with mocked ShopifyClient and ForecastEngine."""
    shopify = AsyncMock()
    shopify.fetch_orders = AsyncMock(return_value=normalized_orders)

    horizon = 30
    forecaster = MagicMock()
    # point shape: (1, horizon), quantile shape: (1, horizon, 10)
    forecaster.forecast = MagicMock(
        return_value=(
            np.full((1, horizon), 100.0),
            np.random.default_rng(42).random((1, horizon, 10)) * 200,
        )
    )

    return AppContext(shopify=shopify, forecaster=forecaster)


@pytest.fixture()
def mock_ctx(mock_app: AppContext) -> MockCtx:
    return MockCtx(mock_app)


# ---------------------------------------------------------------------------
# Level 1: Pydantic model validation
# ---------------------------------------------------------------------------


class TestForecastRevenueParams:
    """ForecastRevenueParams Pydantic validation."""

    def test_defaults(self) -> None:
        p = ForecastRevenueParams()
        assert p.horizon_days == 30
        assert p.context_days == 365
        assert p.frequency == "daily"
        assert p.include_chart_data is False

    def test_rejects_invalid_frequency(self) -> None:
        with pytest.raises(ValidationError):
            ForecastRevenueParams(frequency="biweekly")

    def test_rejects_horizon_too_low(self) -> None:
        with pytest.raises(ValidationError):
            ForecastRevenueParams(horizon_days=0)

    def test_rejects_horizon_too_high(self) -> None:
        with pytest.raises(ValidationError):
            ForecastRevenueParams(horizon_days=366)

    def test_rejects_context_too_low(self) -> None:
        with pytest.raises(ValidationError):
            ForecastRevenueParams(context_days=29)

    def test_accepts_valid_frequencies(self) -> None:
        for freq in ("daily", "weekly", "monthly"):
            p = ForecastRevenueParams(frequency=freq)
            assert p.frequency == freq


# ---------------------------------------------------------------------------
# Level 2: Tool handler integration (mocked dependencies)
# ---------------------------------------------------------------------------


class TestForecastRevenueTool:
    """forecast_revenue handler with mocked Shopify + forecaster."""

    @pytest.mark.asyncio()
    async def test_happy_path_returns_markdown(self, mock_ctx: MockCtx) -> None:
        params = ForecastRevenueParams()
        result = await forecast_revenue(params, mock_ctx)  # type: ignore[arg-type]

        assert isinstance(result, str)
        # summary() output contains "projected"
        assert "projected" in result.lower()
        # to_table() output contains pipe characters
        assert "|" in result

    @pytest.mark.asyncio()
    async def test_empty_orders_returns_no_orders_message(
        self, mock_app: AppContext
    ) -> None:
        mock_app.shopify.fetch_orders = AsyncMock(return_value=[])
        ctx = MockCtx(mock_app)
        params = ForecastRevenueParams()
        result = await forecast_revenue(params, ctx)  # type: ignore[arg-type]

        assert "No orders found" in result

    @pytest.mark.asyncio()
    async def test_shopify_error_returns_friendly_markdown(
        self, mock_app: AppContext
    ) -> None:
        mock_app.shopify.fetch_orders = AsyncMock(
            side_effect=RuntimeError("Connection refused")
        )
        ctx = MockCtx(mock_app)
        params = ForecastRevenueParams()
        result = await forecast_revenue(params, ctx)  # type: ignore[arg-type]

        assert result.startswith("**Error")
        assert "RuntimeError" in result

    @pytest.mark.asyncio()
    async def test_ctx_info_called(self, mock_ctx: MockCtx) -> None:
        params = ForecastRevenueParams()
        await forecast_revenue(params, mock_ctx)  # type: ignore[arg-type]

        assert len(mock_ctx._info_messages) >= 1
        assert any("order" in m.lower() for m in mock_ctx._info_messages)

    @pytest.mark.asyncio()
    async def test_include_chart_data(self, mock_ctx: MockCtx) -> None:
        params = ForecastRevenueParams(include_chart_data=True)
        result = await forecast_revenue(params, mock_ctx)  # type: ignore[arg-type]

        assert "```json" in result
        assert "point_forecast" in result
