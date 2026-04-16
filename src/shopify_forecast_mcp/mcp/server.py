"""shopify-forecast-mcp server entry point."""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from shopify_forecast_mcp.config import get_settings
from shopify_forecast_mcp.core.forecaster import ForecastEngine, get_engine
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

    shopify: ShopifyClient
    forecaster: ForecastEngine


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Initialize shared resources at startup, clean up on shutdown."""
    settings = get_settings()

    # Override log level from settings
    logging.getLogger().setLevel(
        getattr(logging, settings.log_level.upper(), logging.INFO)
    )

    shopify = ShopifyClient(settings)
    engine = get_engine(settings)
    engine.load()

    log.info("shopify-forecast-mcp ready (shop=%s)", settings.shop)
    try:
        yield AppContext(shopify=shopify, forecaster=engine)
    finally:
        await shopify.close()
        log.info("shopify-forecast-mcp shutdown complete")


mcp = FastMCP("shopify-forecast-mcp", lifespan=lifespan)


def main() -> None:
    """Sync entry point for the ``shopify-forecast-mcp`` console script."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
