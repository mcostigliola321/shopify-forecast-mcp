import pytest
from pydantic import ValidationError

from shopify_forecast_mcp.config import Settings, get_settings


def _clear_env(monkeypatch):
    for k in [
        "SHOPIFY_FORECAST_SHOP",
        "SHOPIFY_FORECAST_ACCESS_TOKEN",
        "SHOPIFY_FORECAST_API_VERSION",
        "SHOPIFY_FORECAST_TIMESFM_DEVICE",
        "SHOPIFY_FORECAST_TIMESFM_CONTEXT_LENGTH",
        "SHOPIFY_FORECAST_TIMESFM_HORIZON",
        "SHOPIFY_FORECAST_FORECAST_CACHE_TTL",
        "SHOPIFY_FORECAST_LOG_LEVEL",
        "SHOPIFY_FORECAST_HF_HOME",
        "SHOPIFY_FORECAST_STORES",
        "SHOPIFY_FORECAST_DEFAULT_STORE",
    ]:
        monkeypatch.delenv(k, raising=False)


def test_loads_required_vars(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("SHOPIFY_FORECAST_SHOP", "test.myshopify.com")
    monkeypatch.setenv("SHOPIFY_FORECAST_ACCESS_TOKEN", "shpat_test")
    s = Settings(_env_file=None)
    assert s.shop == "test.myshopify.com"
    assert s.access_token.get_secret_value() == "shpat_test"


def test_missing_required_raises(monkeypatch):
    _clear_env(monkeypatch)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    msg = str(exc.value)
    assert "shop" in msg


def test_access_token_optional(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("SHOPIFY_FORECAST_SHOP", "t.myshopify.com")
    s = Settings(_env_file=None)
    assert s.access_token is None
    assert s.shop == "t.myshopify.com"


def test_defaults(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("SHOPIFY_FORECAST_SHOP", "t.myshopify.com")
    monkeypatch.setenv("SHOPIFY_FORECAST_ACCESS_TOKEN", "shpat_x")
    s = Settings(_env_file=None)
    assert s.api_version == "2026-04"
    assert s.timesfm_device == "cpu"
    assert s.timesfm_context_length == 1024
    assert s.timesfm_horizon == 90
    assert s.forecast_cache_ttl == 3600
    assert s.log_level == "INFO"
    assert s.hf_home is None


def test_secret_str_hides_token(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("SHOPIFY_FORECAST_SHOP", "t.myshopify.com")
    monkeypatch.setenv("SHOPIFY_FORECAST_ACCESS_TOKEN", "shpat_supersecret")
    s = Settings(_env_file=None)
    assert "shpat_supersecret" not in repr(s)
    assert "shpat_supersecret" not in str(s.access_token)


def test_model_dump_hides_token(monkeypatch):
    """R7.8 discipline — Phase 4 will log request context via model_dump.
    Token must never leak through default serialization."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("SHOPIFY_FORECAST_SHOP", "t.myshopify.com")
    monkeypatch.setenv("SHOPIFY_FORECAST_ACCESS_TOKEN", "shpat_supersecret")
    s = Settings(_env_file=None)
    assert "shpat_supersecret" not in str(s.model_dump())
    assert "shpat_supersecret" not in s.model_dump_json()


def test_get_settings_returns_instance(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("SHOPIFY_FORECAST_SHOP", "t.myshopify.com")
    monkeypatch.setenv("SHOPIFY_FORECAST_ACCESS_TOKEN", "shpat_x")
    assert isinstance(get_settings(), Settings)


def test_case_insensitive(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("shopify_forecast_shop", "t.myshopify.com")
    monkeypatch.setenv("shopify_forecast_access_token", "shpat_x")
    s = Settings(_env_file=None)
    assert s.shop == "t.myshopify.com"


def test_stores_defaults_empty(monkeypatch):
    """Multi-store: stores defaults to empty list for backward compat."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("SHOPIFY_FORECAST_SHOP", "t.myshopify.com")
    s = Settings(_env_file=None)
    assert s.stores == []
    assert s.default_store is None


def test_default_store_field(monkeypatch):
    """Multi-store: default_store field can be set."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("SHOPIFY_FORECAST_SHOP", "t.myshopify.com")
    monkeypatch.setenv("SHOPIFY_FORECAST_DEFAULT_STORE", "t.myshopify.com")
    s = Settings(_env_file=None)
    assert s.default_store == "t.myshopify.com"
