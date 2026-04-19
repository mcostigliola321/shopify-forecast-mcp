"""Single-source-of-truth configuration for shopify-forecast-mcp.

Loaded from environment variables prefixed ``SHOPIFY_FORECAST_`` (and optionally
from a local ``.env`` file). The access token is wrapped in
:class:`pydantic.SecretStr` so it never leaks into logs, reprs, or
``model_dump`` output.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class StoreConfig(BaseModel):
    """Configuration for a single Shopify store."""

    shop: str = Field(..., description="Store domain, e.g. mystore.myshopify.com")
    access_token: SecretStr | None = Field(None, description="Admin API access token")
    label: str | None = Field(None, description="Friendly name, e.g. 'US Store'")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SHOPIFY_FORECAST_",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Required ---
    shop: str = Field(..., description="mystore.myshopify.com")
    access_token: SecretStr | None = Field(
        None, description="Shopify Admin API access token (optional if using Shopify CLI)"
    )

    # --- Shopify API ---
    api_version: str = "2026-04"

    # --- TimesFM tuning ---
    timesfm_device: str = "cpu"
    timesfm_context_length: int = 1024
    timesfm_horizon: int = 90

    # --- Feature flags ---
    covariates_enabled: bool = Field(
        False, description="Enable XReg covariates for forecasting (opt-in, marginal improvement)"
    )

    # --- Caching ---
    forecast_cache_ttl: int = 3600

    # --- Observability ---
    log_level: str = "INFO"

    # --- HuggingFace cache override ---
    hf_home: str | None = None

    # --- Multi-store support (Phase 6) ---
    # Claude Desktop config example for multi-store:
    # {
    #   "mcpServers": {
    #     "shopify-forecast": {
    #       "command": "uvx",
    #       "args": ["shopify-forecast-mcp"],
    #       "env": {
    #         "SHOPIFY_FORECAST_SHOP": "us-store.myshopify.com",
    #         "SHOPIFY_FORECAST_ACCESS_TOKEN": "shpat_xxx",
    #         "SHOPIFY_FORECAST_STORES": "[{\"shop\":\"eu-store.myshopify.com\",\"access_token\":\"shpat_yyy\",\"label\":\"EU Store\"}]",
    #         "SHOPIFY_FORECAST_DEFAULT_STORE": "us-store.myshopify.com"
    #       }
    #     }
    #   }
    # }
    stores: list[StoreConfig] = Field(
        default_factory=list,
        description="Additional store configs for multi-store mode. JSON array.",
    )
    default_store: str | None = Field(
        None,
        description="Store domain or label to use when no store param provided",
    )


def get_settings() -> Settings:
    """Return a freshly constructed :class:`Settings` instance."""
    return Settings()  # type: ignore[call-arg]
