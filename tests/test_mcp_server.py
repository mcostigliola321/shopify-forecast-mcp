"""Tests for shopify_forecast_mcp.mcp.server module.

Validates module structure, FastMCP instance, AppContext dataclass,
no-stdout policy, and lifespan lifecycle -- without requiring
Shopify credentials or the TimesFM model.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shopify_forecast_mcp.mcp.server import AppContext, lifespan, main, mcp

SERVER_SRC = Path(__file__).resolve().parent.parent / "src" / "shopify_forecast_mcp" / "mcp" / "server.py"


# ---- Test 1: mcp instance ---------------------------------------------------

def test_mcp_instance():
    """mcp is a FastMCP instance with the correct server name."""
    from mcp.server.fastmcp import FastMCP

    assert isinstance(mcp, FastMCP)
    assert mcp.name == "shopify-forecast-mcp"


# ---- Test 2: AppContext fields -----------------------------------------------

def test_app_context_fields():
    """AppContext is a dataclass with shopify and forecaster fields."""
    assert dataclasses.is_dataclass(AppContext)
    field_names = {f.name for f in dataclasses.fields(AppContext)}
    assert "shopify" in field_names
    assert "forecaster" in field_names


# ---- Test 3: no print() calls -----------------------------------------------

def test_no_print_in_server():
    """server.py source has zero bare print() calls (AST check)."""
    source = SERVER_SRC.read_text()
    tree = ast.parse(source)
    print_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
    ]
    assert print_calls == [], f"Found {len(print_calls)} print() call(s) in server.py"


# ---- Test 4: stderr logging -------------------------------------------------

def test_stderr_logging():
    """logging.basicConfig uses stream=sys.stderr in server.py source."""
    source = SERVER_SRC.read_text()
    assert "sys.stderr" in source
    assert "logging.basicConfig" in source


# ---- Test 5: main is callable ------------------------------------------------

def test_main_callable():
    """main() is a callable function."""
    assert callable(main)


# ---- Test 6: lifespan context manager ----------------------------------------

@pytest.mark.asyncio
async def test_lifespan_context_manager(shopify_settings):
    """Lifespan yields AppContext with correct types and calls close on exit."""
    from shopify_forecast_mcp.core.forecaster import ForecastEngine
    from shopify_forecast_mcp.core.shopify_client import ShopifyClient

    mock_engine = MagicMock(spec=ForecastEngine)
    mock_engine.load = MagicMock()

    mock_server = MagicMock()

    with (
        patch("shopify_forecast_mcp.mcp.server.get_settings", return_value=shopify_settings),
        patch("shopify_forecast_mcp.mcp.server.get_engine", return_value=mock_engine),
    ):
        async with lifespan(mock_server) as ctx:
            assert isinstance(ctx, AppContext)
            assert isinstance(ctx.shopify, ShopifyClient)
            assert ctx.forecaster is mock_engine
            mock_engine.load.assert_called_once()

        # After exiting, shopify client should have been closed
        # (ShopifyClient.close delegates to backend.close which calls httpx aclose)
        assert ctx.shopify._backend._client.is_closed
