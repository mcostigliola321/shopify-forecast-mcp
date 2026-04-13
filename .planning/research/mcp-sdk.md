# MCP Python SDK Research

**Package:** `mcp` on PyPI, current `1.27.0` (2026-04-02), Python 3.10+.
**Confidence:** HIGH on API shape; MEDIUM on edge details.

## Critical PRD corrections

| PRD location | Current | Fix |
|---|---|---|
| L676–679 | `from mcp.server import Server` + `stdio_server` | Replace with `from mcp.server.fastmcp import FastMCP, Context`. **`FastMCP` is the idiomatic API**, not low-level `Server`. |
| L667 | "Support stdio and SSE" | "Support stdio and **streamable-http**" — pure SSE is deprecated per 2025 spec revision. |
| L147 | "`mcp` Python package (latest)" | Pin: `mcp>=1.27,<2.0` (v2 is pre-alpha, breaking). |
| Logging (implicit) | — | **All logging MUST go to stderr**. Stdio transport uses stdout for JSON-RPC framing — any `print()` corrupts the protocol stream. |

## Key decisions

1. **Use FastMCP, not low-level `Server`.** The `@mcp.tool()` decorator auto-generates JSON Schema from type hints.
2. **Pydantic models for tool params.** Simple scalars (`days: int`) can be bare hints. Forecast tools have many optional params — define one `BaseModel` per tool with `Field(description=...)` for self-documenting schemas.
3. **Async tools are fully supported.** `async def` works natively. Required for `httpx.AsyncClient` Shopify calls.
4. **Initialize httpx + TimesFM in `lifespan`.** One client + one model instance at server startup, injected via `Context[ServerSession, AppContext]`. Avoids connection churn and per-request model loads.
5. **Return plain `str` for markdown.** FastMCP auto-wraps into `TextContent`. Only drop to `CallToolResult` if you need `_meta` or multiple content blocks.
6. **Errors: try/except → return friendly markdown.** PRD requires graceful errors. Wrap each tool body, log via stderr, return `f"**Error**\n\n{type(e).__name__}: {e}"` instead of raising.
7. **Transport names:** `mcp.run(transport="stdio")` for Claude Desktop / Code, `transport="streamable-http"` for hosted. Drop "SSE" terminology.

## Stderr logging is mandatory

```python
import logging, sys
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
```

For in-protocol info messages visible to the client, use `ctx.info()`, `ctx.debug()`, `ctx.report_progress()`.

## Minimal server skeleton

```python
"""shopify-forecast-mcp server entry point."""
from __future__ import annotations
import logging, sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator
import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from pydantic import BaseModel, Field

from shopify_forecast_mcp.config import load_config
from shopify_forecast_mcp.core.shopify_client import ShopifyClient
from shopify_forecast_mcp.core.forecaster import ForecastEngine

logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("shopify-forecast-mcp")


@dataclass
class AppContext:
    shopify: ShopifyClient
    forecaster: ForecastEngine


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    cfg = load_config()
    http = httpx.AsyncClient(timeout=30.0)
    shopify = ShopifyClient(http=http, shop=cfg.shop, token=cfg.access_token)
    forecaster = ForecastEngine.load()  # singleton lazy-load TimesFM
    log.info("shopify-forecast-mcp ready (shop=%s)", cfg.shop)
    try:
        yield AppContext(shopify=shopify, forecaster=forecaster)
    finally:
        await http.aclose()


mcp = FastMCP("shopify-forecast-mcp", lifespan=lifespan)


class ForecastRevenueParams(BaseModel):
    horizon_days: int = Field(30, ge=1, le=365)
    lookback_days: int = Field(365, ge=30, le=1095)
    granularity: str = Field("day", pattern="^(day|week|month)$")


@mcp.tool()
async def forecast_revenue(
    params: ForecastRevenueParams,
    ctx: Context[ServerSession, AppContext],
) -> str:
    """Forecast total revenue over a future horizon using TimesFM 2.5."""
    app = ctx.request_context.lifespan_context
    try:
        await ctx.info(f"Pulling {params.lookback_days}d history…")
        series = await app.shopify.fetch_revenue_series(
            lookback_days=params.lookback_days,
            granularity=params.granularity,
        )
        await ctx.info(f"Running TimesFM (horizon={params.horizon_days})…")
        forecast = app.forecaster.predict(series, horizon=params.horizon_days)
        return forecast.to_markdown()
    except Exception as e:  # noqa: BLE001
        log.exception("forecast_revenue failed")
        return f"**Error running forecast_revenue**\n\n{type(e).__name__}: {e}"


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
```

## Claude Desktop config (recommended `uvx` form)

```json
{
  "mcpServers": {
    "shopify-forecast": {
      "command": "uvx",
      "args": ["shopify-forecast-mcp"],
      "env": {
        "SHOPIFY_FORECAST_SHOP": "mystore.myshopify.com",
        "SHOPIFY_FORECAST_ACCESS_TOKEN": "shpat_..."
      }
    }
  }
}
```

## Open questions

- Confirm `mcp[cli]` still ships `mcp dev` inspector in 1.27 (very likely yes).
- `CallToolResult` import path stability between 1.27 and 2.0 (you likely won't need it if returning plain strings).

## Sources

- https://github.com/modelcontextprotocol/python-sdk
- https://pypi.org/project/mcp/ (1.27.0, 2026-04-02)
