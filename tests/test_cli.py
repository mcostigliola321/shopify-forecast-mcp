"""Tests for the shopify-forecast CLI (argparse subcommands).

Covers argument parsing, no-MCP-import enforcement, and integration
tests with mocked Shopify client and forecaster.
"""

from __future__ import annotations

import ast
import json
import sys
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from shopify_forecast_mcp.cli import _run_demand, _run_revenue, build_parser, main


# ---------------------------------------------------------------------------
# Level 1: Parser tests (no mocking needed)
# ---------------------------------------------------------------------------


class TestBuildParser:
    """Verify argparse subcommand structure and defaults."""

    def test_no_args_command_is_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.command is None

    def test_revenue_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["revenue"])
        assert args.command == "revenue"
        assert args.horizon == 30
        assert args.context == 365
        assert args.frequency == "daily"
        assert args.json_output is False

    def test_revenue_overrides(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["revenue", "--horizon", "60", "--context", "180", "--frequency", "weekly", "--json"])
        assert args.horizon == 60
        assert args.context == 180
        assert args.frequency == "weekly"
        assert args.json_output is True

    def test_demand_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["demand"])
        assert args.command == "demand"
        assert args.group_by == "product"
        assert args.group_value == "all"
        assert args.metric == "units"
        assert args.horizon == 30
        assert args.top_n == 10
        assert args.json_output is False

    def test_demand_with_sku_filter(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["demand", "--group-by", "sku", "--group-value", "SKU-A", "--json"])
        assert args.group_by == "sku"
        assert args.group_value == "SKU-A"
        assert args.json_output is True

    def test_demand_metric_choices(self) -> None:
        parser = build_parser()
        for metric in ("units", "revenue", "orders"):
            args = parser.parse_args(["demand", "--metric", metric])
            assert args.metric == metric

    def test_revenue_frequency_choices(self) -> None:
        parser = build_parser()
        for freq in ("daily", "weekly", "monthly"):
            args = parser.parse_args(["revenue", "--frequency", freq])
            assert args.frequency == freq


# ---------------------------------------------------------------------------
# Level 2: No MCP imports (AST check)
# ---------------------------------------------------------------------------


class TestNoMCPImports:
    """Verify cli.py does NOT import from shopify_forecast_mcp.mcp."""

    def test_cli_has_no_mcp_imports(self) -> None:
        import shopify_forecast_mcp.cli as cli_mod
        source_path = cli_mod.__file__
        assert source_path is not None

        with open(source_path) as f:
            source = f.read()

        tree = ast.parse(source)
        mcp_imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("shopify_forecast_mcp.mcp"):
                    mcp_imports.append(node.module)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("shopify_forecast_mcp.mcp"):
                        mcp_imports.append(alias.name)

        assert mcp_imports == [], f"CLI imports from MCP modules: {mcp_imports}"


# ---------------------------------------------------------------------------
# Helpers for integration tests
# ---------------------------------------------------------------------------


def _mock_shopify_client(normalized_orders: list[dict]) -> MagicMock:
    """Create a mock ShopifyClient that supports async context manager."""
    mock_client = AsyncMock()
    mock_client.fetch_orders = AsyncMock(return_value=normalized_orders)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


def _mock_forecast_engine(horizon: int = 30) -> MagicMock:
    """Create a mock ForecastEngine returning synthetic data."""
    engine = MagicMock()
    engine.load = MagicMock()
    rng = np.random.default_rng(42)
    engine.forecast = MagicMock(
        return_value=(
            np.full((1, horizon), 100.0),
            rng.random((1, horizon, 10)) * 200,
        )
    )
    return engine


# ---------------------------------------------------------------------------
# Level 3: Integration tests (mocked Shopify + forecaster)
# ---------------------------------------------------------------------------


class TestMainEntryPoint:
    """Test the main() sync entry point."""

    def test_no_args_returns_zero(self) -> None:
        with patch("sys.argv", ["shopify-forecast"]):
            code = main()
        assert code == 0


class TestRunRevenue:
    """Integration tests for _run_revenue with mocked dependencies."""

    @pytest.mark.asyncio()
    async def test_revenue_markdown_output(
        self, normalized_orders: list[dict], capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_client = _mock_shopify_client(normalized_orders)
        engine = _mock_forecast_engine()

        args = build_parser().parse_args(["revenue"])

        with (
            patch("shopify_forecast_mcp.cli.get_settings"),
            patch("shopify_forecast_mcp.cli.ShopifyClient", return_value=mock_client),
            patch("shopify_forecast_mcp.cli.get_engine", return_value=engine),
        ):
            code = await _run_revenue(args)

        assert code == 0
        captured = capsys.readouterr()
        # summary() contains "projected", to_table() contains "|"
        assert "projected" in captured.out.lower()
        assert "|" in captured.out

    @pytest.mark.asyncio()
    async def test_revenue_json_output(
        self, normalized_orders: list[dict], capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_client = _mock_shopify_client(normalized_orders)
        engine = _mock_forecast_engine()

        args = build_parser().parse_args(["revenue", "--json"])

        with (
            patch("shopify_forecast_mcp.cli.get_settings"),
            patch("shopify_forecast_mcp.cli.ShopifyClient", return_value=mock_client),
            patch("shopify_forecast_mcp.cli.get_engine", return_value=engine),
        ):
            code = await _run_revenue(args)

        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "dates" in data
        assert "point_forecast" in data
        assert "confidence_bands" in data

    @pytest.mark.asyncio()
    async def test_revenue_empty_orders_returns_one(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_client = _mock_shopify_client([])
        engine = _mock_forecast_engine()

        args = build_parser().parse_args(["revenue"])

        with (
            patch("shopify_forecast_mcp.cli.get_settings"),
            patch("shopify_forecast_mcp.cli.ShopifyClient", return_value=mock_client),
            patch("shopify_forecast_mcp.cli.get_engine", return_value=engine),
        ):
            code = await _run_revenue(args)

        assert code == 1


class TestRunDemand:
    """Integration tests for _run_demand with mocked dependencies."""

    @pytest.mark.asyncio()
    async def test_demand_markdown_output(
        self, normalized_orders: list[dict], capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_client = _mock_shopify_client(normalized_orders)
        engine = _mock_forecast_engine()

        args = build_parser().parse_args(["demand", "--group-by", "sku"])

        with (
            patch("shopify_forecast_mcp.cli.get_settings"),
            patch("shopify_forecast_mcp.cli.ShopifyClient", return_value=mock_client),
            patch("shopify_forecast_mcp.cli.get_engine", return_value=engine),
        ):
            code = await _run_demand(args)

        assert code == 0
        captured = capsys.readouterr()
        assert "|" in captured.out
        assert "Sku" in captured.out  # capitalize() of "sku"

    @pytest.mark.asyncio()
    async def test_demand_json_output(
        self, normalized_orders: list[dict], capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_client = _mock_shopify_client(normalized_orders)
        engine = _mock_forecast_engine()

        args = build_parser().parse_args(["demand", "--group-by", "sku", "--json"])

        with (
            patch("shopify_forecast_mcp.cli.get_settings"),
            patch("shopify_forecast_mcp.cli.ShopifyClient", return_value=mock_client),
            patch("shopify_forecast_mcp.cli.get_engine", return_value=engine),
        ):
            code = await _run_demand(args)

        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        # Should have at least one SKU key
        assert len(data) >= 1
        first_val = next(iter(data.values()))
        assert "projected" in first_val
        assert "point_forecast" in first_val

    @pytest.mark.asyncio()
    async def test_demand_specific_group_value(
        self, normalized_orders: list[dict], capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_client = _mock_shopify_client(normalized_orders)
        engine = _mock_forecast_engine()

        args = build_parser().parse_args(["demand", "--group-by", "sku", "--group-value", "SKU-A"])

        with (
            patch("shopify_forecast_mcp.cli.get_settings"),
            patch("shopify_forecast_mcp.cli.ShopifyClient", return_value=mock_client),
            patch("shopify_forecast_mcp.cli.get_engine", return_value=engine),
        ):
            code = await _run_demand(args)

        assert code == 0
        captured = capsys.readouterr()
        assert "SKU-A" in captured.out

    @pytest.mark.asyncio()
    async def test_demand_missing_group_returns_one(
        self, normalized_orders: list[dict], capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_client = _mock_shopify_client(normalized_orders)
        engine = _mock_forecast_engine()

        args = build_parser().parse_args(["demand", "--group-by", "sku", "--group-value", "NONEXISTENT"])

        with (
            patch("shopify_forecast_mcp.cli.get_settings"),
            patch("shopify_forecast_mcp.cli.ShopifyClient", return_value=mock_client),
            patch("shopify_forecast_mcp.cli.get_engine", return_value=engine),
        ):
            code = await _run_demand(args)

        assert code == 1

    @pytest.mark.asyncio()
    async def test_demand_empty_orders_returns_one(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_client = _mock_shopify_client([])
        engine = _mock_forecast_engine()

        args = build_parser().parse_args(["demand"])

        with (
            patch("shopify_forecast_mcp.cli.get_settings"),
            patch("shopify_forecast_mcp.cli.ShopifyClient", return_value=mock_client),
            patch("shopify_forecast_mcp.cli.get_engine", return_value=engine),
        ):
            code = await _run_demand(args)

        assert code == 1
