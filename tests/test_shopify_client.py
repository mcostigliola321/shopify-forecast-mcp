"""Tests for ShopifyClient: auth, throttle backoff, shop timezone."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from shopify_forecast_mcp.core.exceptions import (
    ShopifyGraphQLError,
    ShopifyThrottledError,
)
from shopify_forecast_mcp.core.shopify_client import (
    SHOP_TIMEZONE_QUERY,
    ShopifyClient,
)
from tests.conftest import (
    MOCK_COST_EXTENSIONS,
    SHOPIFY_GQL_URL,
    AlwaysThrottledDispatcher,
    ThrottleThenSucceedDispatcher,
)


@pytest.mark.asyncio(loop_scope="function")
async def test_client_auth(shopify_settings, shopify_client):
    """ShopifyClient sends X-Shopify-Access-Token header and correct URL."""
    with respx.mock:
        route = respx.post(SHOPIFY_GQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"shop": {"ianaTimezone": "UTC", "currencyCode": "USD", "name": "T"}},
                    "extensions": {"cost": MOCK_COST_EXTENSIONS},
                },
            )
        )
        await shopify_client._post_graphql(SHOP_TIMEZONE_QUERY)

        assert route.called
        request = route.calls[0].request
        assert request.headers["X-Shopify-Access-Token"] == "shpat_test123"
        assert request.headers["Content-Type"] == "application/json"
        assert str(request.url) == SHOPIFY_GQL_URL


@pytest.mark.asyncio(loop_scope="function")
async def test_post_graphql_success(mock_shopify, shopify_client):
    """_post_graphql returns parsed response on success."""
    result = await shopify_client._post_graphql(SHOP_TIMEZONE_QUERY)
    assert result["data"]["shop"]["ianaTimezone"] == "America/New_York"
    assert "extensions" in result


@pytest.mark.asyncio(loop_scope="function")
async def test_throttle_backoff(shopify_settings):
    """On THROTTLED error, client sleeps and retries; succeeds on retry."""
    dispatcher = ThrottleThenSucceedDispatcher()

    with respx.mock:
        respx.post(SHOPIFY_GQL_URL).mock(side_effect=dispatcher)
        client = ShopifyClient(shopify_settings)

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await client._post_graphql(SHOP_TIMEZONE_QUERY)

        # Should have succeeded on second attempt
        assert result["data"]["shop"]["ianaTimezone"] == "America/New_York"
        assert dispatcher.call_count == 2

        # Verify sleep was called with the calculated backoff
        # deficit = 502 - 42 = 460, sleep = 460/100 + 0.5 = 5.1
        mock_sleep.assert_awaited_once()
        sleep_arg = mock_sleep.call_args[0][0]
        assert abs(sleep_arg - 5.1) < 0.01


@pytest.mark.asyncio(loop_scope="function")
async def test_throttle_max_retries(shopify_settings):
    """After 3 THROTTLED responses, raises ShopifyThrottledError."""
    dispatcher = AlwaysThrottledDispatcher()

    with respx.mock:
        respx.post(SHOPIFY_GQL_URL).mock(side_effect=dispatcher)
        client = ShopifyClient(shopify_settings)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ShopifyThrottledError):
                await client._post_graphql(SHOP_TIMEZONE_QUERY)

    # Initial call + 3 retries = 4 total calls
    assert dispatcher.call_count == 4


@pytest.mark.asyncio(loop_scope="function")
async def test_graphql_error(shopify_settings):
    """Non-throttle GraphQL errors raise ShopifyGraphQLError."""
    with respx.mock:
        respx.post(SHOPIFY_GQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "errors": [{"message": "Field 'foo' doesn't exist on type 'QueryRoot'"}],
                },
            )
        )
        client = ShopifyClient(shopify_settings)

        with pytest.raises(ShopifyGraphQLError) as exc_info:
            await client._post_graphql("{ foo }")

        assert "foo" in str(exc_info.value)


@pytest.mark.asyncio(loop_scope="function")
async def test_fetch_shop_timezone(mock_shopify, shopify_client):
    """Returns IANA timezone string."""
    tz = await shopify_client.fetch_shop_timezone()
    assert tz == "America/New_York"


@pytest.mark.asyncio(loop_scope="function")
async def test_fetch_shop_timezone_cached(shopify_settings):
    """Second call does not make HTTP request (cached)."""
    with respx.mock:
        route = respx.post(SHOPIFY_GQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "shop": {
                            "ianaTimezone": "America/New_York",
                            "currencyCode": "USD",
                            "name": "Test Store",
                        }
                    },
                    "extensions": {"cost": MOCK_COST_EXTENSIONS},
                },
            )
        )
        client = ShopifyClient(shopify_settings)

        tz1 = await client.fetch_shop_timezone()
        tz2 = await client.fetch_shop_timezone()

        assert tz1 == tz2 == "America/New_York"
        assert route.call_count == 1  # Only one HTTP request
