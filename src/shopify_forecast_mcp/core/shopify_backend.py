"""Dual-backend abstraction for Shopify GraphQL execution.

Provides a :class:`ShopifyBackend` Protocol with two implementations:

- :class:`DirectBackend` -- Authenticated httpx calls with throttle handling
  (for headless/CI environments with an access token).
- :class:`CliBackend` -- Delegates to ``shopify store execute`` subprocess
  (for interactive environments using Shopify CLI OAuth).

The :func:`create_backend` factory selects the appropriate backend based
on configuration: token present -> DirectBackend, CLI on PATH -> CliBackend,
neither -> error with setup instructions.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Any, Protocol, runtime_checkable

import httpx
from pydantic import SecretStr

from shopify_forecast_mcp.config import Settings
from shopify_forecast_mcp.core.exceptions import (
    ShopifyCliNotFoundError,
    ShopifyGraphQLError,
    ShopifyThrottledError,
)
from shopify_forecast_mcp.core.shopify_exec import execute_graphql

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ShopifyBackend(Protocol):
    """Contract for Shopify GraphQL execution backends."""

    async def post_graphql(
        self, query: str, variables: dict | None = None
    ) -> dict: ...

    async def post_graphql_mutation(
        self, query: str, variables: dict | None = None
    ) -> dict: ...

    async def download_url(self, url: str) -> bytes: ...

    async def close(self) -> None: ...


# ---------------------------------------------------------------------------
# DirectBackend -- httpx with auth headers + throttle handling
# ---------------------------------------------------------------------------


class DirectBackend:
    """Authenticated httpx backend with cost-based throttle handling.

    Sends GraphQL requests directly to the Shopify Admin API using
    an access token. Automatically retries on THROTTLED errors with
    a calculated backoff based on ``extensions.cost.throttleStatus``.
    """

    _MAX_RETRIES: int = 3

    def __init__(
        self,
        store: str,
        access_token: SecretStr,
        api_version: str = "2026-04",
    ) -> None:
        self._store = store
        self._access_token = access_token
        self._api_version = api_version
        self._client = httpx.AsyncClient(
            base_url=f"https://{store}/admin/api/{api_version}",
            headers={
                "X-Shopify-Access-Token": access_token.get_secret_value(),
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    async def post_graphql(
        self,
        query: str,
        variables: dict | None = None,
        *,
        _attempt: int = 0,
    ) -> dict:
        """POST a GraphQL query and return the parsed JSON response.

        Automatically retries on THROTTLED errors using a calculated
        backoff from ``extensions.cost.throttleStatus``.

        Raises:
            ShopifyThrottledError: After ``_MAX_RETRIES`` throttle retries.
            ShopifyGraphQLError: On non-throttle GraphQL errors.
            httpx.HTTPStatusError: On HTTP-level errors (4xx/5xx).
        """
        resp = await self._client.post(
            "/graphql.json",
            json={"query": query, "variables": variables or {}},
        )
        resp.raise_for_status()

        data: dict[str, Any] = resp.json()

        # Log cost metadata when available
        cost = data.get("extensions", {}).get("cost")
        if cost:
            throttle = cost.get("throttleStatus", {})
            logger.debug(
                "GraphQL cost: requested=%s actual=%s available=%.0f/%.0f",
                cost.get("requestedQueryCost"),
                cost.get("actualQueryCost"),
                throttle.get("currentlyAvailable", 0),
                throttle.get("maximumAvailable", 0),
            )

        # Check for GraphQL-level errors
        errors = data.get("errors")
        if errors:
            is_throttled = any(
                e.get("extensions", {}).get("code") == "THROTTLED"
                for e in errors
            )
            if is_throttled:
                return await self._handle_throttle(
                    data, query, variables, _attempt
                )
            raise ShopifyGraphQLError(errors)

        return data

    async def _handle_throttle(
        self,
        data: dict[str, Any],
        query: str,
        variables: dict | None,
        attempt: int,
    ) -> dict:
        """Sleep based on throttle status and retry the query.

        Sleep formula: ``(requestedCost - currentlyAvailable) / restoreRate + 0.5``
        capped at 30 seconds.
        """
        if attempt >= self._MAX_RETRIES:
            raise ShopifyThrottledError(data.get("errors", []))

        cost = data.get("extensions", {}).get("cost", {})
        throttle = cost.get("throttleStatus", {})
        available = throttle.get("currentlyAvailable", 0)
        restore_rate = throttle.get("restoreRate", 100)
        requested = cost.get("requestedQueryCost", 1000)

        deficit = max(requested - available, 0)
        sleep_seconds = (
            (deficit / restore_rate + 0.5) if restore_rate > 0 else 2.0
        )
        sleep_seconds = min(sleep_seconds, 30.0)

        logger.info(
            "Throttled. Sleeping %.1fs (attempt %d/%d)",
            sleep_seconds,
            attempt + 1,
            self._MAX_RETRIES,
        )

        await asyncio.sleep(sleep_seconds)
        return await self.post_graphql(query, variables, _attempt=attempt + 1)

    async def post_graphql_mutation(
        self, query: str, variables: dict | None = None
    ) -> dict:
        """Execute a GraphQL mutation (same endpoint as queries for Shopify)."""
        return await self.post_graphql(query, variables)

    async def download_url(self, url: str) -> bytes:
        """Download a signed URL and return the raw bytes.

        Uses a fresh httpx client since signed URLs require no auth headers.
        """
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


# ---------------------------------------------------------------------------
# CliBackend -- Shopify CLI subprocess
# ---------------------------------------------------------------------------


class CliBackend:
    """Shopify CLI subprocess backend.

    Delegates GraphQL execution to ``shopify store execute`` via
    :func:`execute_graphql`. No persistent connection is maintained.
    """

    def __init__(self, store: str) -> None:
        self._store = store

    async def post_graphql(
        self, query: str, variables: dict | None = None
    ) -> dict:
        """Execute a GraphQL query via the Shopify CLI."""
        return await execute_graphql(
            store=self._store,
            query=query,
            variables=variables,
            allow_mutations=False,
        )

    async def post_graphql_mutation(
        self, query: str, variables: dict | None = None
    ) -> dict:
        """Execute a GraphQL mutation via the Shopify CLI."""
        return await execute_graphql(
            store=self._store,
            query=query,
            variables=variables,
            allow_mutations=True,
        )

    async def download_url(self, url: str) -> bytes:
        """Download a signed URL and return the raw bytes.

        Uses a fresh httpx client since signed URLs require no auth headers.
        """
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content

    async def close(self) -> None:
        """No-op -- CLI backend has no persistent connection."""
        pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_backend(settings: Settings) -> ShopifyBackend:
    """Select and instantiate the appropriate Shopify backend.

    Selection logic:

    1. If ``settings.access_token`` is set (not None): :class:`DirectBackend`
    2. Elif ``shopify`` CLI is on PATH: :class:`CliBackend`
    3. Else: raise :class:`ShopifyCliNotFoundError` with setup instructions

    Args:
        settings: Application settings with shop, access_token, api_version.

    Returns:
        A backend instance implementing :class:`ShopifyBackend`.

    Raises:
        ShopifyCliNotFoundError: When neither token nor CLI is available.
    """
    if settings.access_token is not None:
        logger.info("Using DirectBackend (access token configured)")
        return DirectBackend(
            store=settings.shop,
            access_token=settings.access_token,
            api_version=settings.api_version,
        )

    if shutil.which("shopify") is not None:
        logger.info("Using CliBackend (Shopify CLI found on PATH)")
        return CliBackend(store=settings.shop)

    raise ShopifyCliNotFoundError(
        "No Shopify credentials found. Either:\n"
        "  1. Install Shopify CLI and run: shopify store auth "
        f"--store {settings.shop} "
        "--scopes read_orders,read_all_orders,read_products,read_inventory\n"
        "  2. Set SHOPIFY_FORECAST_ACCESS_TOKEN in .env"
    )
