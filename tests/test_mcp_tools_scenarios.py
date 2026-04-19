"""Tests for the compare_scenarios MCP tool handler."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from shopify_forecast_mcp.mcp.server import AppContext
from shopify_forecast_mcp.mcp.tools import (
    CompareScenariosParams,
    ScenarioInput,
    compare_scenarios,
)


# ---------------------------------------------------------------------------
# MockCtx
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

    forecaster = MagicMock()
    call_count = 0

    def mock_forecast_with_covariates(series, covariates, horizon=None):
        nonlocal call_count
        call_count += 1
        h = horizon or 30
        base = 100.0 * call_count
        point = np.array([[base + i for i in range(h)]])
        quantile = np.ones((1, h, 10)) * (base - 10.0)
        quantile[:, :, 1] = base - 20.0  # q10
        quantile[:, :, 9] = base + 20.0  # q90
        return point, quantile

    forecaster.forecast_with_covariates = MagicMock(
        side_effect=mock_forecast_with_covariates
    )

    return AppContext(shopify=shopify, forecaster=forecaster)


@pytest.fixture()
def mock_ctx(mock_app: AppContext) -> MockCtx:
    return MockCtx(mock_app)


# ---------------------------------------------------------------------------
# Pydantic validation tests
# ---------------------------------------------------------------------------


class TestCompareScenariosParams:
    def test_valid_params(self) -> None:
        p = CompareScenariosParams(
            scenarios=[
                ScenarioInput(
                    name="A", promo_start="2025-07-01", promo_end="2025-07-07", discount_depth=0.2
                ),
                ScenarioInput(
                    name="B", promo_start="2025-07-01", promo_end="2025-07-07", discount_depth=0.4
                ),
            ]
        )
        assert len(p.scenarios) == 2
        assert p.horizon_days == 30
        assert p.country == "US"

    def test_rejects_one_scenario(self) -> None:
        with pytest.raises(ValidationError):
            CompareScenariosParams(
                scenarios=[
                    ScenarioInput(
                        name="A", promo_start="2025-07-01", promo_end="2025-07-07", discount_depth=0.2
                    ),
                ]
            )

    def test_rejects_five_scenarios(self) -> None:
        with pytest.raises(ValidationError):
            CompareScenariosParams(
                scenarios=[
                    ScenarioInput(
                        name=f"S{i}", promo_start="2025-07-01", promo_end="2025-07-07", discount_depth=0.1 * i
                    )
                    for i in range(5)
                ]
            )

    def test_rejects_invalid_discount_depth(self) -> None:
        with pytest.raises(ValidationError):
            ScenarioInput(
                name="Bad", promo_start="2025-07-01", promo_end="2025-07-07", discount_depth=1.5
            )

    def test_rejects_negative_discount_depth(self) -> None:
        with pytest.raises(ValidationError):
            ScenarioInput(
                name="Bad", promo_start="2025-07-01", promo_end="2025-07-07", discount_depth=-0.1
            )


# ---------------------------------------------------------------------------
# Tool handler tests
# ---------------------------------------------------------------------------


class TestCompareScenariosTool:
    @pytest.mark.asyncio()
    async def test_happy_path_returns_markdown(self, mock_ctx: MockCtx) -> None:
        params = CompareScenariosParams(
            scenarios=[
                ScenarioInput(
                    name="Conservative", promo_start="2025-07-01", promo_end="2025-07-07", discount_depth=0.1
                ),
                ScenarioInput(
                    name="Aggressive", promo_start="2025-07-01", promo_end="2025-07-14", discount_depth=0.4
                ),
            ],
            horizon_days=30,
        )
        result = await compare_scenarios(params, mock_ctx)  # type: ignore[arg-type]

        assert isinstance(result, str)
        assert "Scenario Comparison" in result
        assert "Recommendation" in result
        assert "Conservative" in result
        assert "Aggressive" in result

    @pytest.mark.asyncio()
    async def test_empty_orders_returns_no_orders(self, mock_app: AppContext) -> None:
        mock_app.shopify.fetch_orders = AsyncMock(return_value=[])
        ctx = MockCtx(mock_app)
        params = CompareScenariosParams(
            scenarios=[
                ScenarioInput(
                    name="A", promo_start="2025-07-01", promo_end="2025-07-07", discount_depth=0.2
                ),
                ScenarioInput(
                    name="B", promo_start="2025-07-01", promo_end="2025-07-07", discount_depth=0.3
                ),
            ]
        )
        result = await compare_scenarios(params, ctx)  # type: ignore[arg-type]
        assert "No orders found" in result

    @pytest.mark.asyncio()
    async def test_error_returns_friendly_message(self, mock_app: AppContext) -> None:
        mock_app.shopify.fetch_orders = AsyncMock(
            side_effect=RuntimeError("Connection failed")
        )
        ctx = MockCtx(mock_app)
        params = CompareScenariosParams(
            scenarios=[
                ScenarioInput(
                    name="A", promo_start="2025-07-01", promo_end="2025-07-07", discount_depth=0.2
                ),
                ScenarioInput(
                    name="B", promo_start="2025-07-01", promo_end="2025-07-07", discount_depth=0.3
                ),
            ]
        )
        result = await compare_scenarios(params, ctx)  # type: ignore[arg-type]
        assert result.startswith("**Error")
        assert "RuntimeError" in result

    @pytest.mark.asyncio()
    async def test_ctx_info_called(self, mock_ctx: MockCtx) -> None:
        params = CompareScenariosParams(
            scenarios=[
                ScenarioInput(
                    name="A", promo_start="2025-07-01", promo_end="2025-07-07", discount_depth=0.2
                ),
                ScenarioInput(
                    name="B", promo_start="2025-07-01", promo_end="2025-07-07", discount_depth=0.3
                ),
            ]
        )
        await compare_scenarios(params, mock_ctx)  # type: ignore[arg-type]
        assert len(mock_ctx._info_messages) >= 1
