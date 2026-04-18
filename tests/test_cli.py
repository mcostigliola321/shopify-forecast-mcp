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

from shopify_forecast_mcp.cli import (
    _run_demand,
    _run_revenue,
    build_parser,
    main,
)


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
            patch("shopify_forecast_mcp.cli.create_backend"),
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
            patch("shopify_forecast_mcp.cli.create_backend"),
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
            patch("shopify_forecast_mcp.cli.create_backend"),
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
            patch("shopify_forecast_mcp.cli.create_backend"),
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
            patch("shopify_forecast_mcp.cli.create_backend"),
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
            patch("shopify_forecast_mcp.cli.create_backend"),
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
            patch("shopify_forecast_mcp.cli.create_backend"),
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
            patch("shopify_forecast_mcp.cli.create_backend"),
            patch("shopify_forecast_mcp.cli.ShopifyClient", return_value=mock_client),
            patch("shopify_forecast_mcp.cli.get_engine", return_value=engine),
        ):
            code = await _run_demand(args)

        assert code == 1


# ---------------------------------------------------------------------------
# Level 4: Promo subcommand tests
# ---------------------------------------------------------------------------


class TestBuildParserPromo:
    """Verify promo subcommand structure and defaults."""

    def test_promo_subcommand_exists(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["promo", "--start", "2025-04-30", "--end", "2025-05-07"])
        assert args.command == "promo"
        assert args.start == "2025-04-30"
        assert args.end == "2025-05-07"

    def test_promo_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["promo", "--start", "2025-04-30", "--end", "2025-05-07"])
        assert args.name == ""
        assert args.baseline_days == 30
        assert args.json_output is False

    def test_promo_all_flags(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "promo", "--start", "2025-04-30", "--end", "2025-05-07",
            "--name", "Spring Sale", "--baseline-days", "60", "--json",
        ])
        assert args.name == "Spring Sale"
        assert args.baseline_days == 60
        assert args.json_output is True


class TestRunPromo:
    """Integration tests for _run_promo with mocked dependencies."""

    @pytest.mark.asyncio()
    async def test_promo_markdown_output(
        self, sample_orders_with_promos: list[dict], capsys: pytest.CaptureFixture[str]
    ) -> None:
        from shopify_forecast_mcp.cli import _run_promo

        mock_client = _mock_shopify_client(sample_orders_with_promos)

        args = build_parser().parse_args([
            "promo", "--start", "2025-04-30", "--end", "2025-05-07",
        ])

        with (
            patch("shopify_forecast_mcp.cli.get_settings"),
            patch("shopify_forecast_mcp.cli.create_backend"),
            patch("shopify_forecast_mcp.cli.ShopifyClient", return_value=mock_client),
        ):
            code = await _run_promo(args)

        assert code == 0
        captured = capsys.readouterr()
        assert "Promotion Impact" in captured.out

    @pytest.mark.asyncio()
    async def test_promo_json_output(
        self, sample_orders_with_promos: list[dict], capsys: pytest.CaptureFixture[str]
    ) -> None:
        from shopify_forecast_mcp.cli import _run_promo

        mock_client = _mock_shopify_client(sample_orders_with_promos)

        args = build_parser().parse_args([
            "promo", "--start", "2025-04-30", "--end", "2025-05-07", "--json",
        ])

        with (
            patch("shopify_forecast_mcp.cli.get_settings"),
            patch("shopify_forecast_mcp.cli.create_backend"),
            patch("shopify_forecast_mcp.cli.ShopifyClient", return_value=mock_client),
        ):
            code = await _run_promo(args)

        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "sections" in data

    @pytest.mark.asyncio()
    async def test_promo_invalid_dates_returns_one(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from shopify_forecast_mcp.cli import _run_promo

        args = build_parser().parse_args([
            "promo", "--start", "not-a-date", "--end", "2025-05-07",
        ])

        code = await _run_promo(args)
        assert code == 1


# ---------------------------------------------------------------------------
# Level 5: Compare subcommand tests
# ---------------------------------------------------------------------------


class TestBuildParserCompare:
    """Verify compare subcommand structure and defaults."""

    def test_compare_subcommand_exists_with_yoy(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["compare", "--yoy"])
        assert args.command == "compare"
        assert args.yoy is True
        assert args.mom is False

    def test_compare_subcommand_with_mom(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["compare", "--mom"])
        assert args.mom is True
        assert args.yoy is False

    def test_compare_custom_dates(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "compare",
            "--period-a-start", "2025-03-01",
            "--period-a-end", "2025-03-31",
            "--period-b-start", "2025-04-01",
            "--period-b-end", "2025-04-30",
        ])
        assert args.period_a_start == "2025-03-01"
        assert args.period_a_end == "2025-03-31"
        assert args.period_b_start == "2025-04-01"
        assert args.period_b_end == "2025-04-30"

    def test_compare_json_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["compare", "--yoy", "--json"])
        assert args.json_output is True


class TestRunCompare:
    """Integration tests for _run_compare with mocked dependencies."""

    @pytest.mark.asyncio()
    async def test_compare_custom_dates_markdown(
        self, sample_orders_with_promos: list[dict], capsys: pytest.CaptureFixture[str]
    ) -> None:
        from shopify_forecast_mcp.cli import _run_compare

        mock_client = _mock_shopify_client(sample_orders_with_promos)

        args = build_parser().parse_args([
            "compare",
            "--period-a-start", "2025-03-01",
            "--period-a-end", "2025-03-31",
            "--period-b-start", "2025-04-01",
            "--period-b-end", "2025-04-30",
        ])

        with (
            patch("shopify_forecast_mcp.cli.get_settings"),
            patch("shopify_forecast_mcp.cli.create_backend"),
            patch("shopify_forecast_mcp.cli.ShopifyClient", return_value=mock_client),
        ):
            code = await _run_compare(args)

        assert code == 0
        captured = capsys.readouterr()
        assert "Period Comparison" in captured.out
        assert "Revenue" in captured.out

    @pytest.mark.asyncio()
    async def test_compare_json_output(
        self, sample_orders_with_promos: list[dict], capsys: pytest.CaptureFixture[str]
    ) -> None:
        from shopify_forecast_mcp.cli import _run_compare

        mock_client = _mock_shopify_client(sample_orders_with_promos)

        args = build_parser().parse_args([
            "compare",
            "--period-a-start", "2025-03-01",
            "--period-a-end", "2025-03-31",
            "--period-b-start", "2025-04-01",
            "--period-b-end", "2025-04-30",
            "--json",
        ])

        with (
            patch("shopify_forecast_mcp.cli.get_settings"),
            patch("shopify_forecast_mcp.cli.create_backend"),
            patch("shopify_forecast_mcp.cli.ShopifyClient", return_value=mock_client),
        ):
            code = await _run_compare(args)

        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "sections" in data

    @pytest.mark.asyncio()
    async def test_compare_yoy_returns_zero(
        self, sample_orders_with_promos: list[dict], capsys: pytest.CaptureFixture[str]
    ) -> None:
        from shopify_forecast_mcp.cli import _run_compare

        mock_client = _mock_shopify_client(sample_orders_with_promos)

        args = build_parser().parse_args(["compare", "--yoy"])

        with (
            patch("shopify_forecast_mcp.cli.get_settings"),
            patch("shopify_forecast_mcp.cli.create_backend"),
            patch("shopify_forecast_mcp.cli.ShopifyClient", return_value=mock_client),
        ):
            code = await _run_compare(args)

        assert code == 0

    @pytest.mark.asyncio()
    async def test_compare_mom_returns_zero(
        self, sample_orders_with_promos: list[dict], capsys: pytest.CaptureFixture[str]
    ) -> None:
        from shopify_forecast_mcp.cli import _run_compare

        mock_client = _mock_shopify_client(sample_orders_with_promos)

        args = build_parser().parse_args(["compare", "--mom"])

        with (
            patch("shopify_forecast_mcp.cli.get_settings"),
            patch("shopify_forecast_mcp.cli.create_backend"),
            patch("shopify_forecast_mcp.cli.ShopifyClient", return_value=mock_client),
        ):
            code = await _run_compare(args)

        assert code == 0


class TestMainDispatches:
    """Test that main() dispatches promo and compare correctly."""

    def test_main_dispatches_promo(self) -> None:
        with (
            patch("sys.argv", ["shopify-forecast", "promo", "--start", "2025-04-30", "--end", "2025-05-07"]),
            patch("shopify_forecast_mcp.cli._run_promo", new_callable=AsyncMock, return_value=0) as mock_run,
            patch("asyncio.run", side_effect=lambda coro: 0) as mock_asyncio,
        ):
            code = main()
        assert code == 0

    def test_main_dispatches_compare(self) -> None:
        with (
            patch("sys.argv", ["shopify-forecast", "compare", "--yoy"]),
            patch("shopify_forecast_mcp.cli._run_compare", new_callable=AsyncMock, return_value=0) as mock_run,
            patch("asyncio.run", side_effect=lambda coro: 0) as mock_asyncio,
        ):
            code = main()
        assert code == 0
