"""Integration smoke test for Shopify CLI backend.

Requires:
- Shopify CLI installed and on PATH
- Prior ``shopify store auth`` for the configured store
- ``SHOPIFY_FORECAST_SHOP`` env var set

Run with: ``uv run pytest -m integration``
"""

from __future__ import annotations

import os
import shutil

import pytest

from shopify_forecast_mcp.core.shopify_backend import CliBackend

# Skip entire module if Shopify CLI not available or no store configured
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        shutil.which("shopify") is None,
        reason="Shopify CLI not installed",
    ),
    pytest.mark.skipif(
        not os.environ.get("SHOPIFY_FORECAST_SHOP"),
        reason="SHOPIFY_FORECAST_SHOP not set",
    ),
]


@pytest.fixture()
def cli_backend() -> CliBackend:
    """Create a CliBackend pointing at the configured store."""
    store = os.environ["SHOPIFY_FORECAST_SHOP"]
    return CliBackend(store=store)


@pytest.mark.asyncio(loop_scope="function")
async def test_cli_backend_shop_timezone(cli_backend: CliBackend) -> None:
    """Smoke test: fetch shop timezone via real Shopify CLI."""
    result = await cli_backend.post_graphql("{ shop { ianaTimezone } }")
    assert "data" in result
    assert "shop" in result["data"]
    tz = result["data"]["shop"]["ianaTimezone"]
    # IANA timezone should contain a slash (e.g., America/New_York)
    assert "/" in tz, f"Expected IANA timezone, got: {tz}"
