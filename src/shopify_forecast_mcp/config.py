"""Single-source-of-truth configuration for shopify-forecast-mcp.

Loaded from environment variables prefixed ``SHOPIFY_FORECAST_`` (and optionally
from a local ``.env`` file). The access token is wrapped in
:class:`pydantic.SecretStr` so it never leaks into logs, reprs, or
``model_dump`` output.
"""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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


def get_settings() -> Settings:
    """Return a freshly constructed :class:`Settings` instance."""
    return Settings()  # type: ignore[call-arg]
