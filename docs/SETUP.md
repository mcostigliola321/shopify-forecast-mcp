# Setup Guide

This guide gets you from zero to a working `shopify-forecast-mcp` in under 10 minutes. For the TL;DR install, see [README.md#quick-start](../README.md#quick-start).

> **For merchants:** you can follow every step with just a terminal and a Shopify admin login. For developers, see [ARCHITECTURE.md](ARCHITECTURE.md) for the two-layer design.

## Contents

- [Prerequisites](#prerequisites)
- [Step 1 — Create a Shopify custom app](#step-1--create-a-shopify-custom-app)
- [Step 2 — Install and configure](#step-2--install-and-configure)
- [Step 3 — Add to your MCP client](#step-3--add-to-your-mcp-client)
- [Docker install](#docker)
- [Multi-store configuration](#multi-store)
- [Environment variable reference](#environment-variable-reference)
- [CLI usage](#cli-usage)
- [Troubleshooting](#troubleshooting)

***

## Prerequisites

- A Shopify store with admin access
- Python 3.11 (installed automatically by `uvx`)
- One of: Claude Desktop, Claude Code, Cursor, or any other MCP-compatible client
- ~400MB disk space for TimesFM 2.5 weights (downloaded on first use)

***

## Step 1 — Create a Shopify custom app

`shopify-forecast-mcp` reads order + product + inventory data via Shopify's Admin GraphQL API. You need a private admin-scoped token.

1. In your Shopify admin, go to **Settings → Apps and sales channels → Develop apps**.
2. Click **Create an app** (name it `shopify-forecast-mcp` or similar).
3. Click **Configure Admin API scopes** and enable these four scopes:
   - `read_orders` — order data
   - `read_all_orders` — **required** for >60 days of history (the default `read_orders` scope is capped at 60 days)
   - `read_products` — product catalog for demand forecasting
   - `read_inventory` — inventory levels for reorder alerts
4. Click **Save**, then **Install app**.
5. Copy the **Admin API access token** (starts with `shpat_`). You won't see it again — save it now.

> **Alternative (host-only):** if you have the [Shopify CLI](https://shopify.dev/docs/api/shopify-cli) installed on your machine, you can run `shopify-forecast auth --store mystore.myshopify.com` to authenticate via browser OAuth instead of a manual token. This does NOT work inside Docker — see the [Docker](#docker) section.

***

## Step 2 — Install and configure

### Install `uv` (once)

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
irm https://astral.sh/uv/install.ps1 | iex
```

### Configure environment variables

Create a `.env` file in your working directory (or export these in your shell):

```bash
SHOPIFY_FORECAST_SHOP=mystore.myshopify.com
SHOPIFY_FORECAST_ACCESS_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxxxxxx
```

Test it:

```bash
uvx shopify-forecast revenue --horizon 7
```

If this prints a 7-day forecast table, you're ready. First run downloads TimesFM 2.5 weights (~400MB, one-time).

***

## Step 3 — Add to your MCP client

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

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

Restart Claude Desktop. You should see `shopify-forecast` in the tools menu.

### Claude Code

```bash
claude mcp add shopify-forecast \
  --command uvx \
  --args shopify-forecast-mcp \
  --env SHOPIFY_FORECAST_SHOP=mystore.myshopify.com \
  --env SHOPIFY_FORECAST_ACCESS_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxxxxxx
```

### Generic MCP client

The server speaks the [Model Context Protocol](https://modelcontextprotocol.io/) over stdio. Launch it with:

```bash
uvx shopify-forecast-mcp
```

It reads `SHOPIFY_FORECAST_*` env vars at startup. Any MCP-compatible client (Cursor, custom agents) can connect by invoking the command above with the env vars set.

### Alpha pre-release installation

v0.1.0-rc1 and earlier release candidates are published to PyPI as pre-releases. `uvx` skips pre-releases by default — use:

```bash
uvx --prerelease=allow shopify-forecast-mcp@0.1.0rc1
```

In Claude Desktop config, pass the same flags via `args`:

```bash
# equivalent args array for claude_desktop_config.json:
#   "args": ["--prerelease=allow", "shopify-forecast-mcp@0.1.0rc1"]
```

***

## Docker

Two image tags on GHCR (`ghcr.io/omnialta/shopify-forecast-mcp`):

| Tag | Size | Model load |
|-----|------|------------|
| `:latest` | ~1.5 GB | Downloads on first forecast call |
| `:bundled` | ~2.5 GB | Weights baked in, offline-capable |

Run the MCP server:

```bash
docker run --rm -i \
  -e SHOPIFY_FORECAST_SHOP=mystore.myshopify.com \
  -e SHOPIFY_FORECAST_ACCESS_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxxxxxx \
  ghcr.io/omnialta/shopify-forecast-mcp:latest
```

Or dispatch a CLI verb directly:

```bash
docker run --rm \
  -e SHOPIFY_FORECAST_SHOP=mystore.myshopify.com \
  -e SHOPIFY_FORECAST_ACCESS_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxxxxxx \
  ghcr.io/omnialta/shopify-forecast-mcp:bundled revenue --horizon 30
```

> **Docker limitation:** the browser-based OAuth flow (`shopify-forecast auth`) cannot work inside a container — there's no browser. You MUST supply `SHOPIFY_FORECAST_ACCESS_TOKEN` via `-e` when running in Docker. This is enforced by the container's DirectBackend-only mode.

### Claude Desktop with Docker

```json
{
  "mcpServers": {
    "shopify-forecast": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "SHOPIFY_FORECAST_SHOP=mystore.myshopify.com",
        "-e", "SHOPIFY_FORECAST_ACCESS_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxxxxxx",
        "ghcr.io/omnialta/shopify-forecast-mcp:bundled"
      ]
    }
  }
}
```

***

## Multi-store

If you operate multiple Shopify stores, configure them via the nested env-var convention (pydantic-settings):

```bash
# Default / primary store
SHOPIFY_FORECAST_SHOP=us-store.myshopify.com
SHOPIFY_FORECAST_ACCESS_TOKEN=shpat_usxxxxxxxx

# Additional stores indexed from 0
SHOPIFY_FORECAST_STORES__0__SHOP=eu-store.myshopify.com
SHOPIFY_FORECAST_STORES__0__ACCESS_TOKEN=shpat_euxxxxxxxx
SHOPIFY_FORECAST_STORES__0__LABEL=EU Store

SHOPIFY_FORECAST_STORES__1__SHOP=uk-store.myshopify.com
SHOPIFY_FORECAST_STORES__1__ACCESS_TOKEN=shpat_ukxxxxxxxx
SHOPIFY_FORECAST_STORES__1__LABEL=UK Store

SHOPIFY_FORECAST_DEFAULT_STORE=us-store.myshopify.com
```

Every MCP tool accepts an optional `store` parameter (domain or label) to target a specific store without restart.

For Claude Desktop, serialize the `stores` list as a JSON string:

```json
{
  "mcpServers": {
    "shopify-forecast": {
      "command": "uvx",
      "args": ["shopify-forecast-mcp"],
      "env": {
        "SHOPIFY_FORECAST_SHOP": "us-store.myshopify.com",
        "SHOPIFY_FORECAST_ACCESS_TOKEN": "shpat_usxxxxxxxx",
        "SHOPIFY_FORECAST_STORES": "[{\"shop\":\"eu-store.myshopify.com\",\"access_token\":\"shpat_euxxxxxxxx\",\"label\":\"EU Store\"}]",
        "SHOPIFY_FORECAST_DEFAULT_STORE": "us-store.myshopify.com"
      }
    }
  }
}
```

***

## Environment variable reference

All variables are prefixed `SHOPIFY_FORECAST_`. Full list:

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `SHOPIFY_FORECAST_SHOP` | yes | — | Primary store domain (e.g. `mystore.myshopify.com`) |
| `SHOPIFY_FORECAST_ACCESS_TOKEN` | yes* | — | Admin API access token (*optional when using Shopify CLI host-mode) |
| `SHOPIFY_FORECAST_API_VERSION` | no | `2026-04` | GraphQL Admin API version |
| `SHOPIFY_FORECAST_TIMESFM_DEVICE` | no | `cpu` | `cpu` or `cuda`. No `mps` (Apple Silicon runs on CPU) |
| `SHOPIFY_FORECAST_TIMESFM_CONTEXT_LENGTH` | no | `1024` | TimesFM context window |
| `SHOPIFY_FORECAST_TIMESFM_HORIZON` | no | `90` | TimesFM max horizon |
| `SHOPIFY_FORECAST_COVARIATES_ENABLED` | no | `false` | Enable XReg covariates (Phase 5 feature flag) |
| `SHOPIFY_FORECAST_FORECAST_CACHE_TTL` | no | `3600` | Order cache TTL in seconds |
| `SHOPIFY_FORECAST_LOG_LEVEL` | no | `INFO` | Python logging level |
| `SHOPIFY_FORECAST_HF_HOME` | no | HF default | Override HuggingFace cache dir (Docker `:bundled` uses `/opt/hf-cache`) |
| `SHOPIFY_FORECAST_DEFAULT_STORE` | no | — | Multi-store: default target when no `store` param passed |
| `SHOPIFY_FORECAST_STORES__N__SHOP` | no | — | Multi-store: additional store domain at index N |
| `SHOPIFY_FORECAST_STORES__N__ACCESS_TOKEN` | no | — | Multi-store: additional store token |
| `SHOPIFY_FORECAST_STORES__N__LABEL` | no | — | Multi-store: friendly label for store at index N |

See also: `.env.example` in the repo root.

***

## CLI usage

The standalone CLI runs the same core without the MCP runtime — useful for scripting, cron, and CI.

### `revenue`

```bash
shopify-forecast revenue [--horizon N] [--context N] [--frequency daily|weekly|monthly] [--json] [--store STORE]
```

Store-level revenue forecast. Defaults: 30-day horizon, 365-day context, daily frequency.

### `demand`

```bash
shopify-forecast demand [--group-by product|collection|sku] [--group-value ID|all] [--metric units|revenue|orders] [--horizon N] [--top-n N] [--store STORE]
```

Product / collection / SKU demand with reorder alerts when projected demand exceeds on-hand inventory.

### `promo`

```bash
shopify-forecast promo --start YYYY-MM-DD --end YYYY-MM-DD [--baseline-days N] [--store STORE]
```

Analyze a past promo window against the prior N-day baseline. Returns lift, AOV change, hangover.

### `compare`

```bash
shopify-forecast compare --period-a YYYY-MM-DD:YYYY-MM-DD --period-b YYYY-MM-DD:YYYY-MM-DD [--store STORE]
```

Year-over-year or month-over-month comparison across metrics.

### `auth` (host-only)

```bash
shopify-forecast auth --store mystore.myshopify.com
```

Browser OAuth via Shopify CLI (does NOT work in Docker). Requires `shopify` CLI on PATH.

Add `--json` to any verb for machine-readable output.

***

## Troubleshooting

**"No compatible Python found"** — `uvx` picks the latest installed Python by default. Force 3.11 with `uvx --python 3.11 shopify-forecast-mcp`.

**First run is slow** — TimesFM 2.5 weights (~400MB) download on first forecast. Subsequent calls are <10s. For offline use, `docker run ghcr.io/omnialta/shopify-forecast-mcp:bundled` has the weights baked in.

**"No orders found"** — verify `SHOPIFY_FORECAST_SHOP` matches your exact `.myshopify.com` domain, and the access token has all four required scopes (especially `read_all_orders` for more than 60 days of history).

**Rate limiting / THROTTLED** — the client backs off automatically on cost-based throttling. Large initial fetches (>10k orders) use the bulk-operations path, which can take up to 60 seconds.

**Claude Desktop can't find the server** — restart Claude Desktop fully (quit + relaunch). Check `~/Library/Logs/Claude/mcp*.log` (macOS) for startup errors.

**Apple Silicon (M-series) performance** — TimesFM 2.5 source has no `mps` branch; Apple users run on CPU. Forecasts stay well under the 10s target for typical store volumes.

***

*Documentation for v0.1.0-alpha. See [CHANGELOG.md](../CHANGELOG.md) for release notes.*
