"""Unit tests for ShopifyBackend implementations and factory.

Tests cover:
- DirectBackend: auth headers, throttle retry, throttle max retries, GraphQL errors, download
- CliBackend: query execution, mutation flag, variables, error handling, download
- create_backend: factory selection logic (token, CLI, neither)
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from pydantic import SecretStr

from shopify_forecast_mcp.core.exceptions import (
    ShopifyCliError,
    ShopifyCliNotFoundError,
    ShopifyGraphQLError,
    ShopifyThrottledError,
)
from shopify_forecast_mcp.core.shopify_backend import (
    CliBackend,
    DirectBackend,
    create_backend,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_STORE = "test-store.myshopify.com"
TEST_TOKEN = "shpat_test123"
TEST_API_VERSION = "2026-04"
GQL_URL = f"https://{TEST_STORE}/admin/api/{TEST_API_VERSION}/graphql.json"

MOCK_COST_EXTENSIONS: dict = {
    "requestedQueryCost": 52,
    "actualQueryCost": 12,
    "throttleStatus": {
        "maximumAvailable": 2000.0,
        "currentlyAvailable": 1988.0,
        "restoreRate": 100.0,
    },
}

MOCK_THROTTLE_COST: dict = {
    "requestedQueryCost": 502,
    "actualQueryCost": None,
    "throttleStatus": {
        "maximumAvailable": 2000.0,
        "currentlyAvailable": 42.0,
        "restoreRate": 100.0,
    },
}

SHOP_RESPONSE = {
    "data": {
        "shop": {
            "ianaTimezone": "UTC",
            "currencyCode": "USD",
            "name": "Test Store",
        }
    },
    "extensions": {"cost": MOCK_COST_EXTENSIONS},
}

THROTTLED_RESPONSE = {
    "errors": [
        {
            "message": "Throttled",
            "extensions": {"code": "THROTTLED"},
        }
    ],
    "extensions": {"cost": MOCK_THROTTLE_COST},
}

GQL_ERROR_RESPONSE = {
    "errors": [
        {
            "message": "Field 'nonexistent' doesn't exist on type 'QueryRoot'",
        }
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_direct_backend() -> DirectBackend:
    return DirectBackend(
        store=TEST_STORE,
        access_token=SecretStr(TEST_TOKEN),
        api_version=TEST_API_VERSION,
    )


class ThrottleThenSucceedHandler:
    """Returns THROTTLED on first call, success on subsequent."""

    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1
        if self.call_count == 1:
            return httpx.Response(200, json=THROTTLED_RESPONSE)
        return httpx.Response(200, json=SHOP_RESPONSE)


class AlwaysThrottledHandler:
    """Always returns THROTTLED."""

    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1
        return httpx.Response(200, json=THROTTLED_RESPONSE)


# ---------------------------------------------------------------------------
# TestDirectBackend
# ---------------------------------------------------------------------------


class TestDirectBackend:
    """Tests for DirectBackend (httpx with auth + throttle handling)."""

    @pytest.mark.asyncio
    async def test_post_graphql_success(self) -> None:
        """Sends correct headers and URL, returns parsed JSON."""
        backend = _make_direct_backend()
        try:
            with respx.mock:
                route = respx.post(GQL_URL).mock(
                    return_value=httpx.Response(200, json=SHOP_RESPONSE)
                )

                result = await backend.post_graphql("{ shop { ianaTimezone } }")

                assert result["data"]["shop"]["ianaTimezone"] == "UTC"
                assert route.called
                request = route.calls[0].request
                assert request.headers["X-Shopify-Access-Token"] == TEST_TOKEN
                assert request.headers["Content-Type"] == "application/json"
        finally:
            await backend.close()

    @pytest.mark.asyncio
    async def test_post_graphql_throttle_retry(self) -> None:
        """Retries on THROTTLED and succeeds on second attempt."""
        backend = _make_direct_backend()
        handler = ThrottleThenSucceedHandler()
        try:
            with respx.mock:
                respx.post(GQL_URL).mock(side_effect=handler)

                with patch("shopify_forecast_mcp.core.shopify_backend.asyncio.sleep", new_callable=AsyncMock):
                    result = await backend.post_graphql("{ shop { ianaTimezone } }")

                assert result["data"]["shop"]["ianaTimezone"] == "UTC"
                assert handler.call_count == 2
        finally:
            await backend.close()

    @pytest.mark.asyncio
    async def test_post_graphql_throttle_max_retries(self) -> None:
        """Raises ShopifyThrottledError after MAX_RETRIES attempts."""
        backend = _make_direct_backend()
        handler = AlwaysThrottledHandler()
        try:
            with respx.mock:
                respx.post(GQL_URL).mock(side_effect=handler)

                with patch("shopify_forecast_mcp.core.shopify_backend.asyncio.sleep", new_callable=AsyncMock):
                    with pytest.raises(ShopifyThrottledError):
                        await backend.post_graphql("{ shop { ianaTimezone } }")

                # 1 initial + 3 retries = 4 total
                assert handler.call_count == 4
        finally:
            await backend.close()

    @pytest.mark.asyncio
    async def test_post_graphql_error(self) -> None:
        """Raises ShopifyGraphQLError on non-throttle errors."""
        backend = _make_direct_backend()
        try:
            with respx.mock:
                respx.post(GQL_URL).mock(
                    return_value=httpx.Response(200, json=GQL_ERROR_RESPONSE)
                )

                with pytest.raises(ShopifyGraphQLError):
                    await backend.post_graphql("{ nonexistent }")
        finally:
            await backend.close()

    @pytest.mark.asyncio
    async def test_post_graphql_mutation_delegates(self) -> None:
        """post_graphql_mutation delegates to post_graphql."""
        backend = _make_direct_backend()
        try:
            with respx.mock:
                route = respx.post(GQL_URL).mock(
                    return_value=httpx.Response(200, json=SHOP_RESPONSE)
                )

                result = await backend.post_graphql_mutation("mutation { ... }")
                assert result["data"]["shop"]["ianaTimezone"] == "UTC"
                assert route.called
        finally:
            await backend.close()

    @pytest.mark.asyncio
    async def test_download_url(self) -> None:
        """Downloads a signed URL and returns bytes."""
        backend = _make_direct_backend()
        download_url = "https://storage.googleapis.com/fake-bulk-result.jsonl"
        content = b'{"id": "gid://shopify/Order/1"}\n'
        try:
            with respx.mock:
                respx.get(download_url).mock(
                    return_value=httpx.Response(200, content=content)
                )

                result = await backend.download_url(download_url)
                assert result == content
        finally:
            await backend.close()


# ---------------------------------------------------------------------------
# TestCliBackend
# ---------------------------------------------------------------------------


class TestCliBackend:
    """Tests for CliBackend (Shopify CLI subprocess)."""

    def _mock_process(
        self,
        returncode: int = 0,
        stdout: bytes = b"{}",
        stderr: bytes = b"",
    ) -> AsyncMock:
        """Create a mock subprocess process."""
        proc = AsyncMock()
        proc.returncode = returncode
        proc.communicate = AsyncMock(return_value=(stdout, stderr))
        return proc

    @pytest.mark.asyncio
    async def test_post_graphql(self) -> None:
        """Calls execute_graphql with allow_mutations=False."""
        backend = CliBackend(store=TEST_STORE)
        response_data = {"data": {"shop": {"ianaTimezone": "UTC"}}}
        proc = self._mock_process(stdout=json.dumps(response_data).encode())

        with patch("shopify_forecast_mcp.core.shopify_exec.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            result = await backend.post_graphql("{ shop { ianaTimezone } }")

            assert result == response_data
            # Verify command construction
            call_args = mock_exec.call_args[0]
            assert "shopify" in call_args
            assert "--store" in call_args
            assert TEST_STORE in call_args
            assert "--json" in call_args
            assert "--query" in call_args
            assert "--allow-mutations" not in call_args

    @pytest.mark.asyncio
    async def test_post_graphql_mutation(self) -> None:
        """Calls execute_graphql with allow_mutations=True."""
        backend = CliBackend(store=TEST_STORE)
        response_data = {"data": {"bulkOperationRunQuery": {"bulkOperation": {"id": "123"}}}}
        proc = self._mock_process(stdout=json.dumps(response_data).encode())

        with patch("shopify_forecast_mcp.core.shopify_exec.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            result = await backend.post_graphql_mutation("mutation { ... }")

            assert result == response_data
            call_args = mock_exec.call_args[0]
            assert "--allow-mutations" in call_args

    @pytest.mark.asyncio
    async def test_post_graphql_with_variables(self) -> None:
        """Passes --variables flag with JSON when variables provided."""
        backend = CliBackend(store=TEST_STORE)
        response_data = {"data": {"orders": {"edges": []}}}
        proc = self._mock_process(stdout=json.dumps(response_data).encode())
        variables = {"first": 10, "after": "cursor123"}

        with patch("shopify_forecast_mcp.core.shopify_exec.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            result = await backend.post_graphql(
                "query($first: Int!) { orders(first: $first) { edges { node { id } } } }",
                variables=variables,
            )

            assert result == response_data
            call_args = mock_exec.call_args[0]
            assert "--variables" in call_args
            # Find the variables JSON in the args
            var_idx = list(call_args).index("--variables")
            var_json = json.loads(call_args[var_idx + 1])
            assert var_json == variables

    @pytest.mark.asyncio
    async def test_post_graphql_error(self) -> None:
        """Raises ShopifyCliError on non-zero exit code."""
        backend = CliBackend(store=TEST_STORE)
        proc = self._mock_process(
            returncode=1,
            stderr=b"Error: Store not found",
        )

        with patch("shopify_forecast_mcp.core.shopify_exec.asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(ShopifyCliError, match="Store not found"):
                await backend.post_graphql("{ shop { name } }")

    @pytest.mark.asyncio
    async def test_download_url(self) -> None:
        """Downloads a signed URL via httpx (no auth headers)."""
        backend = CliBackend(store=TEST_STORE)
        download_url = "https://storage.googleapis.com/fake-bulk-result.jsonl"
        content = b'{"id": "gid://shopify/Order/1"}\n'

        with respx.mock:
            respx.get(download_url).mock(
                return_value=httpx.Response(200, content=content)
            )

            result = await backend.download_url(download_url)
            assert result == content


# ---------------------------------------------------------------------------
# TestCreateBackend
# ---------------------------------------------------------------------------


class TestCreateBackend:
    """Tests for create_backend factory function."""

    def _mock_settings(
        self,
        access_token: str | None = None,
        shop: str = TEST_STORE,
        api_version: str = TEST_API_VERSION,
    ) -> MagicMock:
        """Create a mock Settings object."""
        settings = MagicMock()
        settings.shop = shop
        settings.api_version = api_version
        if access_token is not None:
            settings.access_token = SecretStr(access_token)
        else:
            settings.access_token = None
        return settings

    def test_returns_direct_when_token_set(self) -> None:
        """Returns DirectBackend when access_token is configured."""
        settings = self._mock_settings(access_token="shpat_xxx")
        backend = create_backend(settings)
        assert isinstance(backend, DirectBackend)

    def test_returns_cli_when_no_token_cli_available(self) -> None:
        """Returns CliBackend when no token but shopify CLI is on PATH."""
        settings = self._mock_settings(access_token=None)

        with patch("shopify_forecast_mcp.core.shopify_backend.shutil.which", return_value="/usr/local/bin/shopify"):
            backend = create_backend(settings)
            assert isinstance(backend, CliBackend)

    def test_raises_when_neither(self) -> None:
        """Raises ShopifyCliNotFoundError when neither token nor CLI available."""
        settings = self._mock_settings(access_token=None)

        with patch("shopify_forecast_mcp.core.shopify_backend.shutil.which", return_value=None):
            with pytest.raises(ShopifyCliNotFoundError, match="No Shopify credentials found"):
                create_backend(settings)
