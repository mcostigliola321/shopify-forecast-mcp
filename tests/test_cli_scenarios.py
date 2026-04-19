"""Tests for the CLI scenarios subcommand."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from shopify_forecast_mcp.cli import _run_scenarios, build_parser


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestScenariosParser:
    def test_scenarios_subcommand_parsed(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "scenarios",
            "--scenarios", '[{"name":"A","promo_start":"2025-07-01","promo_end":"2025-07-07","discount_depth":0.2},'
                           '{"name":"B","promo_start":"2025-07-01","promo_end":"2025-07-07","discount_depth":0.3}]',
        ])
        assert args.command == "scenarios"
        assert args.horizon == 30
        assert args.context == 365
        assert args.country == "US"
        assert args.json_output is False

    def test_scenarios_with_options(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "scenarios",
            "--scenarios", "[]",
            "--horizon", "60",
            "--context", "180",
            "--country", "GB",
            "--json",
        ])
        assert args.horizon == 60
        assert args.context == 180
        assert args.country == "GB"
        assert args.json_output is True


# ---------------------------------------------------------------------------
# _run_scenarios tests
# ---------------------------------------------------------------------------


class MockEngine:
    """Returns deterministic forecasts."""

    def __init__(self) -> None:
        self.call_count = 0

    def load(self) -> None:
        pass

    def forecast_with_covariates(self, series, covariates, horizon=None):
        self.call_count += 1
        h = horizon or 30
        base = 100.0 * self.call_count
        point = np.array([[base + i for i in range(h)]])
        quantile = np.ones((1, h, 10)) * (base - 10.0)
        quantile[:, :, 1] = base - 20.0
        quantile[:, :, 9] = base + 20.0
        return point, quantile


def _make_fake_orders(n_days: int = 10) -> list[dict]:
    orders = []
    for i in range(n_days):
        d = f"2025-06-{i + 1:02d}"
        orders.append({
            "id": str(1000 + i),
            "created_at": f"{d}T10:00:00Z",
            "local_date": d,
            "financial_status": "PAID",
            "subtotal": 100.0,
            "current_subtotal": 100.0,
            "total_discounts": 0.0,
            "total_refunded": 0.0,
            "net_payment": 100.0,
            "currency": "USD",
            "discount_codes": [],
            "tags": [],
            "source_name": "",
            "test": False,
            "cancelled_at": None,
            "customer_id": "C1",
            "line_items": [{
                "id": str(5000 + i),
                "title": "Widget",
                "quantity": 1,
                "current_quantity": 1,
                "unit_price": 100.0,
                "gross_revenue": 100.0,
                "refund_quantity": 0,
                "refund_amount": 0.0,
                "net_quantity": 1,
                "net_revenue": 100.0,
                "product_id": "P1",
                "product_title": "Widget",
                "variant_id": "V1",
                "sku": "SKU-A",
                "variant_title": "Default",
            }],
        })
    return orders


class TestRunScenariosCLI:
    @pytest.mark.asyncio()
    async def test_markdown_output(self, capsys: pytest.CaptureFixture) -> None:
        scenarios_json = json.dumps([
            {"name": "A", "promo_start": "2025-07-01", "promo_end": "2025-07-07", "discount_depth": 0.2},
            {"name": "B", "promo_start": "2025-07-01", "promo_end": "2025-07-07", "discount_depth": 0.3},
        ])
        parser = build_parser()
        args = parser.parse_args(["scenarios", "--scenarios", scenarios_json])

        mock_shopify = AsyncMock()
        mock_shopify.fetch_orders = AsyncMock(return_value=_make_fake_orders())
        mock_shopify.__aenter__ = AsyncMock(return_value=mock_shopify)
        mock_shopify.__aexit__ = AsyncMock(return_value=False)

        with patch("shopify_forecast_mcp.cli.get_settings"), \
             patch("shopify_forecast_mcp.cli.create_backend"), \
             patch("shopify_forecast_mcp.cli.ShopifyClient", return_value=mock_shopify), \
             patch("shopify_forecast_mcp.cli.get_engine", return_value=MockEngine()):
            result = await _run_scenarios(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "Scenario Comparison" in captured.out
        assert "Recommendation" in captured.out

    @pytest.mark.asyncio()
    async def test_json_output(self, capsys: pytest.CaptureFixture) -> None:
        scenarios_json = json.dumps([
            {"name": "A", "promo_start": "2025-07-01", "promo_end": "2025-07-07", "discount_depth": 0.2},
            {"name": "B", "promo_start": "2025-07-01", "promo_end": "2025-07-07", "discount_depth": 0.3},
        ])
        parser = build_parser()
        args = parser.parse_args(["scenarios", "--scenarios", scenarios_json, "--json"])

        mock_shopify = AsyncMock()
        mock_shopify.fetch_orders = AsyncMock(return_value=_make_fake_orders())
        mock_shopify.__aenter__ = AsyncMock(return_value=mock_shopify)
        mock_shopify.__aexit__ = AsyncMock(return_value=False)

        with patch("shopify_forecast_mcp.cli.get_settings"), \
             patch("shopify_forecast_mcp.cli.create_backend"), \
             patch("shopify_forecast_mcp.cli.ShopifyClient", return_value=mock_shopify), \
             patch("shopify_forecast_mcp.cli.get_engine", return_value=MockEngine()):
            result = await _run_scenarios(args)

        assert result == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert isinstance(parsed, list)
        assert len(parsed) == 2
        assert parsed[0]["name"] == "A"
        assert "total_revenue" in parsed[0]

    @pytest.mark.asyncio()
    async def test_invalid_json(self, capsys: pytest.CaptureFixture) -> None:
        parser = build_parser()
        args = parser.parse_args(["scenarios", "--scenarios", "[invalid json"])
        result = await _run_scenarios(args)
        assert result == 1

    @pytest.mark.asyncio()
    async def test_no_orders(self, capsys: pytest.CaptureFixture) -> None:
        scenarios_json = json.dumps([
            {"name": "A", "promo_start": "2025-07-01", "promo_end": "2025-07-07", "discount_depth": 0.2},
            {"name": "B", "promo_start": "2025-07-01", "promo_end": "2025-07-07", "discount_depth": 0.3},
        ])
        parser = build_parser()
        args = parser.parse_args(["scenarios", "--scenarios", scenarios_json])

        mock_shopify = AsyncMock()
        mock_shopify.fetch_orders = AsyncMock(return_value=[])
        mock_shopify.__aenter__ = AsyncMock(return_value=mock_shopify)
        mock_shopify.__aexit__ = AsyncMock(return_value=False)

        with patch("shopify_forecast_mcp.cli.get_settings"), \
             patch("shopify_forecast_mcp.cli.create_backend"), \
             patch("shopify_forecast_mcp.cli.ShopifyClient", return_value=mock_shopify), \
             patch("shopify_forecast_mcp.cli.get_engine", return_value=MockEngine()):
            result = await _run_scenarios(args)

        assert result == 1

    @pytest.mark.asyncio()
    async def test_missing_scenario_keys(self, capsys: pytest.CaptureFixture) -> None:
        scenarios_json = json.dumps([
            {"name": "A"},
            {"name": "B"},
        ])
        parser = build_parser()
        args = parser.parse_args(["scenarios", "--scenarios", scenarios_json])
        result = await _run_scenarios(args)
        assert result == 1
