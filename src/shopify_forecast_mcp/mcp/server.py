"""shopify-forecast-mcp server entry point."""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncIterator

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from shopify_forecast_mcp.config import get_settings
from shopify_forecast_mcp.core.forecaster import ForecastEngine, get_engine
from shopify_forecast_mcp.core.shopify_backend import create_backend
from shopify_forecast_mcp.core.shopify_client import ShopifyClient

# R7.8: ALL logging to stderr -- stdio transport uses stdout for JSON-RPC
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("shopify-forecast-mcp")


@dataclass
class AppContext:
    """Shared application state injected into every tool via lifespan."""

    shopify: ShopifyClient  # default store (backward compat)
    forecaster: ForecastEngine
    store_clients: dict[str, ShopifyClient] = field(default_factory=dict)
    _label_map: dict[str, str] = field(default_factory=dict)  # label -> domain

    def get_client(self, store: str | None = None) -> ShopifyClient:
        """Resolve store param to a ShopifyClient.

        Args:
            store: Store domain or label. None returns the default client.

        Returns:
            ShopifyClient for the requested store.

        Raises:
            ValueError: If store is not configured.
        """
        if store is None:
            return self.shopify
        # Try by domain
        if store in self.store_clients:
            return self.store_clients[store]
        # Try by label
        domain = self._label_map.get(store)
        if domain and domain in self.store_clients:
            return self.store_clients[domain]
        available = list(self.store_clients.keys())
        raise ValueError(
            f"Unknown store: {store!r}. Configured stores: {available}"
        )


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Initialize shared resources at startup, clean up on shutdown."""
    settings = get_settings()

    # Override log level from settings
    logging.getLogger().setLevel(
        getattr(logging, settings.log_level.upper(), logging.INFO)
    )

    backend = create_backend(settings)
    shopify = ShopifyClient(backend, settings)
    engine = get_engine(settings)
    engine.load()

    # Multi-store: create clients for configured stores
    store_clients: dict[str, ShopifyClient] = {}
    label_map: dict[str, str] = {}
    # Always register the default store
    store_clients[settings.shop] = shopify
    for sc in settings.stores:
        if sc.shop == settings.shop:
            # Already the default, just register label
            if sc.label:
                label_map[sc.label] = sc.shop
            continue
        # Create a Settings copy for this store
        store_settings = settings.model_copy(update={
            "shop": sc.shop,
            "access_token": sc.access_token,
        })
        store_backend = create_backend(store_settings)
        store_client = ShopifyClient(store_backend, store_settings)
        store_clients[sc.shop] = store_client
        if sc.label:
            label_map[sc.label] = sc.shop

    log.info(
        "shopify-forecast-mcp ready (stores=%s, backend=%s)",
        list(store_clients.keys()),
        type(backend).__name__,
    )
    try:
        yield AppContext(
            shopify=shopify,
            forecaster=engine,
            store_clients=store_clients,
            _label_map=label_map,
        )
    finally:
        # Close all clients
        for client in store_clients.values():
            await client.close()
        log.info("shopify-forecast-mcp shutdown complete")


mcp = FastMCP("shopify-forecast-mcp", lifespan=lifespan)


def main() -> None:
    """Sync entry point for the ``shopify-forecast-mcp`` console script."""
    mcp.run(transport="stdio")


# Register tool handlers (must be after mcp is defined)
import shopify_forecast_mcp.mcp.tools  # noqa: F401

if __name__ == "__main__":
    main()
