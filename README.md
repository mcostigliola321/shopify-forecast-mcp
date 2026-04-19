# shopify-forecast-mcp

> ⚠️ **v0.1.0 Alpha** — Early release. API surface may change before v0.2. Feedback welcome: [open an issue](https://github.com/mcostigliola321/shopify-forecast-mcp/issues).

Merchant-native MCP server that connects Google's TimesFM 2.5 time-series foundation model to your Shopify store — so your AI assistant can answer "what does next month look like?" with a real forecast grounded in your order history.

No dashboards, no exports, no per-store training. Works with Claude Desktop, Claude Code, Cursor, and any MCP-compatible AI client.

***

## Why

Shopify has four official MCP servers, all buyer-facing or developer-facing. None serve merchant operations: forecasting, demand planning, promo analysis, anomaly detection.

Existing third-party tools either use weak models (moving averages, Prophet) or lock insights inside closed SaaS dashboards. This one:

- Runs **TimesFM 2.5** (Google's 200M-param foundation model) — state of the art on the GIFT-Eval retail benchmark
- Pulls directly from **Shopify Admin GraphQL** with bulk operations, refund-aware normalization, multi-currency, and cost-based rate limiting
- Returns **markdown tables with confidence bands** that render natively in your MCP client
- Ships as a single `uvx` command — zero manual Python setup
- Is **MIT licensed, free forever**

***

## Quick start

Three steps to a working forecast in under 5 minutes:

### 1. Install `uv` (once)

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex
```

### 2. Get a Shopify Admin API access token

Follow [docs/SETUP.md](docs/SETUP.md) to create a custom app, enable the required scopes (`read_orders`, `read_all_orders`, `read_products`, `read_inventory`), and generate an access token.

### 3. Add to Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows) and add:

```json
{
  "mcpServers": {
    "shopify-forecast": {
      "command": "uvx",
      "args": ["shopify-forecast-mcp"],
      "env": {
        "SHOPIFY_FORECAST_SHOP": "mystore.myshopify.com",
        "SHOPIFY_FORECAST_ACCESS_TOKEN": "shpat_xxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

Restart Claude Desktop, then ask: **"What does next month look like?"**

First run downloads TimesFM 2.5 weights (~400MB, one-time). Subsequent forecasts are <10 seconds.

> **Prefer the terminal first?** You can verify your setup before wiring Claude Desktop by running `uvx shopify-forecast-mcp` directly — it launches the MCP server on stdio and will exit cleanly on Ctrl-C when no client is attached. Or exercise the CLI: `uvx --from shopify-forecast-mcp shopify-forecast revenue --horizon 7`.

> **Alpha pre-release:** if installing v0.1.0-rc1, use `"args": ["--prerelease=allow", "shopify-forecast-mcp@0.1.0rc1"]` instead.

See also: [docs/SETUP.md](docs/SETUP.md) for Claude Code + generic MCP client setup, Docker install, and multi-store configuration.

***

## Examples

Drop these into your AI client after setup:

**Revenue forecasting** — *"What does next month look like?"*
Returns a daily-granularity revenue forecast for the next 30 days with an 80% confidence band (q10–q90).

**Demand + reorder alerts** — *"Which SKUs need to be reordered in the next 2 weeks?"*
Returns top-N SKUs with projected demand vs current inventory, flagging stockout risk.

**Promo analysis** — *"How did Black Friday perform vs last year?"*
Returns revenue lift, order lift, AOV change, discount depth, and post-promo hangover estimate for both windows side by side.

**Scenario planning** — *"Compare 3 promo scenarios for December: 10% off, 20% off + free shipping, and BOGO."*
Returns 3 differentiated forecasts in one markdown response with per-scenario revenue, units, and margin implications.

***

## Tools

Seven MCP tools, full reference in [docs/TOOLS.md](docs/TOOLS.md):

| Tool | Purpose |
|------|---------|
| [`forecast_revenue`](docs/TOOLS.md#forecast-revenue) | Store-level revenue forecast with confidence bands |
| [`forecast_demand`](docs/TOOLS.md#forecast-demand) | Product/collection/SKU demand + reorder alerts |
| [`analyze_promotion`](docs/TOOLS.md#analyze-promotion) | Past promo vs baseline — lift, AOV, hangover |
| [`detect_anomalies`](docs/TOOLS.md#detect-anomalies) | Flag days outside forecast quantile bands |
| [`compare_periods`](docs/TOOLS.md#compare-periods) | Year-over-year / month-over-month comparison |
| [`compare_scenarios`](docs/TOOLS.md#compare-scenarios) | What-if forecasting across 2-4 scenarios |
| [`get_seasonality`](docs/TOOLS.md#get-seasonality) | Explain learned seasonal patterns |

***

## Architecture

Two-layer design: a pure-Python **core library** (Shopify client, time-series shaping, TimesFM forecaster, analytics, covariates) wrapped by a **thin MCP server** and a **matching CLI**. Core is importable and testable without the MCP runtime.

Dual-backend Shopify access: **DirectBackend** (httpx + access token, used in Docker and when `SHOPIFY_FORECAST_ACCESS_TOKEN` is set) or **CliBackend** (`shopify store execute` — browser OAuth, no token required, host-only).

Full diagrams + design decisions in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

***

## Configuration

Minimum required env vars:

| Variable | Purpose |
|----------|---------|
| `SHOPIFY_FORECAST_SHOP` | Your store domain (e.g. `mystore.myshopify.com`) |
| `SHOPIFY_FORECAST_ACCESS_TOKEN` | Admin API access token (from custom app) |

See [docs/SETUP.md](docs/SETUP.md) for the full env var table, multi-store config, Docker env passing, and optional tuning knobs.

***

## CLI

A standalone `shopify-forecast` CLI wraps the same core library without the MCP runtime — useful for scripting, cron, and CI:

```bash
uvx --from shopify-forecast-mcp shopify-forecast revenue --horizon 30
uvx --from shopify-forecast-mcp shopify-forecast demand --group-by product --top-n 10
uvx --from shopify-forecast-mcp shopify-forecast promo --start 2025-11-24 --end 2025-11-30
uvx --from shopify-forecast-mcp shopify-forecast compare --period-a 2024-11:2024-12 --period-b 2025-11:2025-12
```

Add `--json` to any verb for machine-readable output. See [docs/SETUP.md#cli-usage](docs/SETUP.md#cli-usage) for the full CLI reference.

***

## Docker

Run the MCP server (or any CLI verb) without installing Python:

```bash
docker run --rm -i \
  -e SHOPIFY_FORECAST_SHOP=mystore.myshopify.com \
  -e SHOPIFY_FORECAST_ACCESS_TOKEN=shpat_xxx \
  ghcr.io/mcostigliola321/shopify-forecast-mcp:latest
```

Two image variants:
- **`:latest`** — lazy model download on first call (smaller image, ~1.5GB)
- **`:bundled`** — TimesFM weights baked in (larger image, ~2.5GB, offline-capable)

Browser-based OAuth does NOT work in containers; Docker mode requires the access-token env var. See [docs/SETUP.md#docker](docs/SETUP.md#docker).

***

## Roadmap

v0.1.0 is the first public alpha, covering the full MVP (7 MCP tools + 4 CLI verbs + dual-backend). Future: see [.planning/ROADMAP.md](.planning/ROADMAP.md).

***

## Contributing

Feedback and bug reports welcome at [GitHub Issues](https://github.com/mcostigliola321/shopify-forecast-mcp/issues). For code contributions, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the two-layer design and open a draft PR early.

***

## License

[MIT](LICENSE). TimesFM 2.5 weights are [Apache 2.0](https://huggingface.co/google/timesfm-2.5-200m-pytorch) (compatible).
