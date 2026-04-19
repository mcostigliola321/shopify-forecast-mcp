"""Tests for the forecast_demand MCP tool.

Covers Pydantic input validation and tool handler logic with
mocked Shopify client and forecaster.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from pydantic import ValidationError

from shopify_forecast_mcp.mcp.server import AppContext
from shopify_forecast_mcp.mcp.tools import ForecastDemandParams, forecast_demand


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
            np.full((1, horizon, 10), 100.0),
        )
    )

    return AppContext(shopify=shopify, forecaster=forecaster)


@pytest.fixture()
def mock_ctx(mock_app: AppContext) -> MockCtx:
    return MockCtx(mock_app)


# ---------------------------------------------------------------------------
# Level 1: Pydantic model validation
# ---------------------------------------------------------------------------


class TestForecastDemandParams:
    """ForecastDemandParams Pydantic validation."""

    def test_defaults(self) -> None:
        p = ForecastDemandParams()
        assert p.group_by == "product"
        assert p.group_value == "all"
        assert p.metric == "units"
        assert p.horizon_days == 30
        assert p.top_n == 10

    def test_rejects_invalid_group_by(self) -> None:
        with pytest.raises(ValidationError):
            ForecastDemandParams(group_by="category")

    def test_rejects_horizon_too_low(self) -> None:
        with pytest.raises(ValidationError):
            ForecastDemandParams(horizon_days=0)

    def test_rejects_horizon_too_high(self) -> None:
        with pytest.raises(ValidationError):
            ForecastDemandParams(horizon_days=366)

    def test_rejects_top_n_too_low(self) -> None:
        with pytest.raises(ValidationError):
            ForecastDemandParams(top_n=0)

    def test_rejects_top_n_too_high(self) -> None:
        with pytest.raises(ValidationError):
            ForecastDemandParams(top_n=51)

    def test_accepts_valid_group_by_values(self) -> None:
        for gb in ("product", "collection", "sku"):
            p = ForecastDemandParams(group_by=gb)
            assert p.group_by == gb

    def test_accepts_valid_metrics(self) -> None:
        for m in ("units", "revenue", "orders"):
            p = ForecastDemandParams(metric=m)
            assert p.metric == m


# ---------------------------------------------------------------------------
# Level 2: Tool handler integration (mocked dependencies)
# ---------------------------------------------------------------------------


class TestForecastDemandTool:
    """forecast_demand handler with mocked Shopify + forecaster."""

    @pytest.mark.asyncio()
    async def test_all_products_returns_markdown_table(
        self, mock_ctx: MockCtx
    ) -> None:
        """group_value='all' returns markdown with multiple product rows."""
        params = ForecastDemandParams(group_by="product", group_value="all")
        result = await forecast_demand(params, mock_ctx)  # type: ignore[arg-type]

        assert isinstance(result, str)
        assert "# Demand Forecast by Product" in result
        # The fixture has P1, P2, P3
        assert "P1" in result
        assert "P2" in result
        assert "P3" in result
        # Should have table separators
        assert "|---|" in result

    @pytest.mark.asyncio()
    async def test_specific_group_filters_to_one(
        self, mock_ctx: MockCtx
    ) -> None:
        """group_value='P1' returns only P1 in the table."""
        params = ForecastDemandParams(group_by="product", group_value="P1")
        result = await forecast_demand(params, mock_ctx)  # type: ignore[arg-type]

        assert "P1" in result
        assert "P2" not in result
        assert "P3" not in result

    @pytest.mark.asyncio()
    async def test_missing_group_returns_not_found(
        self, mock_ctx: MockCtx
    ) -> None:
        """group_value='NONEXISTENT' returns not found message."""
        params = ForecastDemandParams(
            group_by="product", group_value="NONEXISTENT"
        )
        result = await forecast_demand(params, mock_ctx)  # type: ignore[arg-type]

        assert "not found" in result.lower()
        # Should mention some available products
        assert "P1" in result or "P2" in result

    @pytest.mark.asyncio()
    async def test_empty_orders_returns_no_orders(
        self, mock_app: AppContext
    ) -> None:
        """Empty order list returns 'No orders found' message."""
        mock_app.shopify.fetch_orders = AsyncMock(return_value=[])
        ctx = MockCtx(mock_app)
        params = ForecastDemandParams()
        result = await forecast_demand(params, ctx)  # type: ignore[arg-type]

        assert "No orders found" in result

    @pytest.mark.asyncio()
    async def test_shopify_error_returns_friendly_markdown(
        self, mock_app: AppContext
    ) -> None:
        """Shopify exception returns '**Error' markdown."""
        mock_app.shopify.fetch_orders = AsyncMock(
            side_effect=RuntimeError("Connection refused")
        )
        ctx = MockCtx(mock_app)
        params = ForecastDemandParams()
        result = await forecast_demand(params, ctx)  # type: ignore[arg-type]

        assert result.startswith("**Error")
        assert "RuntimeError" in result

    @pytest.mark.asyncio()
    async def test_sku_grouping_works(self, mock_ctx: MockCtx) -> None:
        """group_by='sku' returns SKU identifiers in the table."""
        params = ForecastDemandParams(group_by="sku", group_value="all")
        result = await forecast_demand(params, mock_ctx)  # type: ignore[arg-type]

        assert "SKU-A" in result or "SKU-B" in result or "SKU-C" in result
        assert "# Demand Forecast by Sku" in result

    @pytest.mark.asyncio()
    async def test_ctx_info_called(self, mock_ctx: MockCtx) -> None:
        """Tool sends progress info messages via ctx."""
        params = ForecastDemandParams()
        await forecast_demand(params, mock_ctx)  # type: ignore[arg-type]

        assert len(mock_ctx._info_messages) >= 1
        assert any("order" in m.lower() or "forecast" in m.lower() for m in mock_ctx._info_messages)

    @pytest.mark.asyncio()
    async def test_reorder_alerts_included_when_inventory_available(
        self, mock_app: AppContext
    ) -> None:
        """When fetch_inventory returns data, reorder alerts section appears."""
        # Setup inventory with low stock relative to demand
        mock_app.shopify.fetch_inventory = AsyncMock(return_value=[
            {
                "variant_id": "100",
                "sku": "SKU-A",
                "product_id": "P1",
                "product_title": "Product P1",
                "available": 50,
                "location_id": "1",
                "location_name": "Warehouse",
            },
        ])
        ctx = MockCtx(mock_app)
        params = ForecastDemandParams(
            group_by="product", group_value="P1", lead_time_days=14
        )
        result = await forecast_demand(params, ctx)  # type: ignore[arg-type]

        assert "Reorder Alerts" in result
        assert "SKU-A" in result
        assert "Warehouse" in result

    @pytest.mark.asyncio()
    async def test_graceful_degradation_on_inventory_error(
        self, mock_app: AppContext
    ) -> None:
        """When fetch_inventory raises, demand forecast still returns without error."""
        mock_app.shopify.fetch_inventory = AsyncMock(
            side_effect=RuntimeError("Inventory scope not granted")
        )
        ctx = MockCtx(mock_app)
        params = ForecastDemandParams(group_by="product", group_value="all")
        result = await forecast_demand(params, ctx)  # type: ignore[arg-type]

        # Should still have the demand forecast table
        assert "# Demand Forecast by Product" in result
        assert "P1" in result
        # Should NOT have error message
        assert "Error" not in result
        # Should NOT have reorder alerts
        assert "Reorder Alerts" not in result

    @pytest.mark.asyncio()
    async def test_lead_time_and_safety_factor_params(self) -> None:
        """ForecastDemandParams accepts lead_time_days and safety_factor."""
        p = ForecastDemandParams(lead_time_days=21, safety_factor=1.5)
        assert p.lead_time_days == 21
        assert p.safety_factor == 1.5

    @pytest.mark.asyncio()
    async def test_rejects_invalid_lead_time(self) -> None:
        """lead_time_days must be 1-365."""
        with pytest.raises(ValidationError):
            ForecastDemandParams(lead_time_days=0)
        with pytest.raises(ValidationError):
            ForecastDemandParams(lead_time_days=366)

    @pytest.mark.asyncio()
    async def test_rejects_invalid_safety_factor(self) -> None:
        """safety_factor must be 1.0-3.0."""
        with pytest.raises(ValidationError):
            ForecastDemandParams(safety_factor=0.5)
        with pytest.raises(ValidationError):
            ForecastDemandParams(safety_factor=3.5)
