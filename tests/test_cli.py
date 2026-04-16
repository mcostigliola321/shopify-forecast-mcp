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

from shopify_forecast_mcp.cli import build_parser


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
