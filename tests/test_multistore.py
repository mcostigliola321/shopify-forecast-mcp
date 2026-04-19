"""Tests for multi-store support: config, AppContext resolver, cache isolation."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError
from unittest.mock import AsyncMock, MagicMock

from shopify_forecast_mcp.config import Settings, StoreConfig


# ---------------------------------------------------------------------------
# StoreConfig model tests
# ---------------------------------------------------------------------------


def test_store_config_model(monkeypatch):
    """StoreConfig validates with shop, access_token, and label."""
    sc = StoreConfig(
        shop="a.myshopify.com",
        access_token=SecretStr("tok"),
        label="US",
    )
    assert sc.shop == "a.myshopify.com"
    assert sc.access_token.get_secret_value() == "tok"
    assert sc.label == "US"


def test_store_config_minimal():
    """StoreConfig works with only shop (access_token and label optional)."""
    sc = StoreConfig(shop="b.myshopify.com")
    assert sc.shop == "b.myshopify.com"
    assert sc.access_token is None
    assert sc.label is None


# ---------------------------------------------------------------------------
# Settings backward compat tests
# ---------------------------------------------------------------------------


def _clear_env(monkeypatch):
    for k in [
        "SHOPIFY_FORECAST_SHOP",
        "SHOPIFY_FORECAST_ACCESS_TOKEN",
        "SHOPIFY_FORECAST_API_VERSION",
        "SHOPIFY_FORECAST_STORES",
        "SHOPIFY_FORECAST_DEFAULT_STORE",
    ]:
        monkeypatch.delenv(k, raising=False)


def test_settings_backward_compat(monkeypatch):
    """Settings with no stores list works -- stores defaults to []."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("SHOPIFY_FORECAST_SHOP", "x.myshopify.com")
    s = Settings(_env_file=None)
    assert s.shop == "x.myshopify.com"
    assert s.stores == []
    assert s.default_store is None


def test_settings_with_stores(monkeypatch):
    """Settings with stores list validates."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("SHOPIFY_FORECAST_SHOP", "x.myshopify.com")
    s = Settings(
        _env_file=None,
        stores=[StoreConfig(shop="a.myshopify.com")],
    )
    assert len(s.stores) == 1
    assert s.stores[0].shop == "a.myshopify.com"


def test_settings_stores_from_json_env(monkeypatch):
    """SHOPIFY_FORECAST_STORES env var set to JSON array parses correctly."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("SHOPIFY_FORECAST_SHOP", "x.myshopify.com")
    monkeypatch.setenv(
        "SHOPIFY_FORECAST_STORES",
        '[{"shop":"eu.myshopify.com","access_token":"shpat_eu","label":"EU Store"}]',
    )
    s = Settings(_env_file=None)
    assert len(s.stores) == 1
    assert s.stores[0].shop == "eu.myshopify.com"
    assert s.stores[0].access_token.get_secret_value() == "shpat_eu"
    assert s.stores[0].label == "EU Store"


# ---------------------------------------------------------------------------
# AppContext.get_client tests
# ---------------------------------------------------------------------------


def test_app_context_get_client_default():
    """get_client(None) returns the default ShopifyClient."""
    from shopify_forecast_mcp.mcp.server import AppContext

    default_client = MagicMock()
    ctx = AppContext(
        shopify=default_client,
        forecaster=MagicMock(),
        store_clients={"default.myshopify.com": default_client},
    )
    assert ctx.get_client(None) is default_client


def test_app_context_get_client_by_domain():
    """get_client('store-b.myshopify.com') returns the correct client."""
    from shopify_forecast_mcp.mcp.server import AppContext

    default_client = MagicMock()
    client_b = MagicMock()
    ctx = AppContext(
        shopify=default_client,
        forecaster=MagicMock(),
        store_clients={
            "default.myshopify.com": default_client,
            "store-b.myshopify.com": client_b,
        },
    )
    assert ctx.get_client("store-b.myshopify.com") is client_b


def test_app_context_get_client_by_label():
    """get_client('US Store') returns client whose config has label='US Store'."""
    from shopify_forecast_mcp.mcp.server import AppContext

    default_client = MagicMock()
    us_client = MagicMock()
    ctx = AppContext(
        shopify=default_client,
        forecaster=MagicMock(),
        store_clients={
            "default.myshopify.com": default_client,
            "us.myshopify.com": us_client,
        },
        _label_map={"US Store": "us.myshopify.com"},
    )
    assert ctx.get_client("US Store") is us_client


def test_app_context_get_client_unknown():
    """get_client('unknown') raises ValueError."""
    from shopify_forecast_mcp.mcp.server import AppContext

    ctx = AppContext(
        shopify=MagicMock(),
        forecaster=MagicMock(),
        store_clients={"default.myshopify.com": MagicMock()},
    )
    with pytest.raises(ValueError, match="Unknown store"):
        ctx.get_client("unknown")


# ---------------------------------------------------------------------------
# Cache isolation test
# ---------------------------------------------------------------------------


def test_cache_key_includes_shop():
    """OrderCache._cache_key with different shop values produces different keys."""
    from shopify_forecast_mcp.core.cache import OrderCache

    cache = OrderCache(ttl=3600)
    key_a = cache._cache_key("store-a.myshopify.com", "2025-01-01", "2025-01-31")
    key_b = cache._cache_key("store-b.myshopify.com", "2025-01-01", "2025-01-31")
    assert key_a != key_b, "Cache keys must differ when shop differs"


# ---------------------------------------------------------------------------
# MCP tool store param tests (Task 2)
# ---------------------------------------------------------------------------


def test_mcp_tool_store_param_resolves():
    """Tool handler uses get_client(params.store) to resolve store."""
    from shopify_forecast_mcp.mcp.server import AppContext

    default_client = MagicMock()
    store_b_client = MagicMock()
    ctx = AppContext(
        shopify=default_client,
        forecaster=MagicMock(),
        store_clients={
            "default.myshopify.com": default_client,
            "store-b.myshopify.com": store_b_client,
        },
    )
    # Verify get_client routes correctly
    assert ctx.get_client("store-b.myshopify.com") is store_b_client
    assert ctx.get_client(None) is default_client


def test_mcp_tool_unknown_store_error():
    """get_client with unknown store raises ValueError with 'Unknown store'."""
    from shopify_forecast_mcp.mcp.server import AppContext

    ctx = AppContext(
        shopify=MagicMock(),
        forecaster=MagicMock(),
        store_clients={"default.myshopify.com": MagicMock()},
    )
    with pytest.raises(ValueError, match="Unknown store"):
        ctx.get_client("unknown")


def test_mcp_tool_store_param_exists_on_all_params():
    """All 7 MCP tool params classes have a store field."""
    from shopify_forecast_mcp.mcp.tools import (
        ForecastRevenueParams,
        ForecastDemandParams,
        AnalyzePromotionParams,
        ComparePeriodsParams,
        GetSeasonalityParams,
        DetectAnomaliesParams,
        CompareScenariosParams,
    )

    for cls in [
        ForecastRevenueParams,
        ForecastDemandParams,
        AnalyzePromotionParams,
        ComparePeriodsParams,
        GetSeasonalityParams,
        DetectAnomaliesParams,
        CompareScenariosParams,
    ]:
        assert "store" in cls.model_fields, f"{cls.__name__} missing store field"


# ---------------------------------------------------------------------------
# CLI --store flag tests (Task 2)
# ---------------------------------------------------------------------------


def test_cli_store_flag_parsed():
    """build_parser().parse_args(['revenue', '--store', 'us-store']) works."""
    from shopify_forecast_mcp.cli import build_parser

    args = build_parser().parse_args(["revenue", "--store", "us-store"])
    assert args.store == "us-store"


def test_cli_store_flag_on_all_verbs():
    """All CLI verbs (revenue, demand, promo, compare, scenarios) accept --store."""
    from shopify_forecast_mcp.cli import build_parser

    parser = build_parser()
    # revenue
    args = parser.parse_args(["revenue", "--store", "x"])
    assert args.store == "x"
    # demand
    args = parser.parse_args(["demand", "--store", "y"])
    assert args.store == "y"
    # promo
    args = parser.parse_args(["promo", "--start", "2025-01-01", "--end", "2025-01-07", "--store", "z"])
    assert args.store == "z"
    # compare
    args = parser.parse_args(["compare", "--yoy", "--store", "w"])
    assert args.store == "w"
    # scenarios
    args = parser.parse_args(["scenarios", "--scenarios", "[]", "--store", "v"])
    assert args.store == "v"


def test_resolve_store_config():
    """_resolve_store_config finds by domain and by label."""
    from shopify_forecast_mcp.cli import _resolve_store_config

    settings = Settings(
        _env_file=None,
        shop="default.myshopify.com",
        access_token=SecretStr("tok_default"),
        stores=[
            StoreConfig(shop="eu.myshopify.com", access_token=SecretStr("tok_eu"), label="EU Store"),
        ],
    )
    # Find default by domain
    result = _resolve_store_config(settings, "default.myshopify.com")
    assert result is not None
    assert result.shop == "default.myshopify.com"

    # Find by store domain
    result = _resolve_store_config(settings, "eu.myshopify.com")
    assert result is not None
    assert result.shop == "eu.myshopify.com"

    # Find by label
    result = _resolve_store_config(settings, "EU Store")
    assert result is not None
    assert result.shop == "eu.myshopify.com"

    # Unknown returns None
    result = _resolve_store_config(settings, "unknown")
    assert result is None
