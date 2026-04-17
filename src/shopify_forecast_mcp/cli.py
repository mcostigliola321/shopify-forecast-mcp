"""CLI entry point for shopify-forecast."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import subprocess
import sys
from datetime import date, timedelta

import numpy as np

# R9.3: NO imports from shopify_forecast_mcp.mcp -- CLI is MCP-independent
from shopify_forecast_mcp.config import get_settings
from shopify_forecast_mcp.core.forecast_result import ForecastResult
from shopify_forecast_mcp.core.forecaster import get_engine
from shopify_forecast_mcp.core.shopify_backend import create_backend
from shopify_forecast_mcp.core.shopify_client import CLI_AUTH_SCOPES, REQUIRED_SCOPES, ShopifyClient
from shopify_forecast_mcp.core.timeseries import (
    clean_series,
    orders_to_daily_series,
    resample_series,
)

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("shopify-forecast")

FREQ_MAP = {"daily": "D", "weekly": "W", "monthly": "M"}


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argparse parser with revenue and demand subcommands."""
    parser = argparse.ArgumentParser(
        prog="shopify-forecast",
        description="Shopify sales forecasting powered by TimesFM 2.5",
    )
    sub = parser.add_subparsers(dest="command")

    # -- revenue subcommand --
    rev = sub.add_parser("revenue", help="Forecast total store revenue")
    rev.add_argument("--horizon", type=int, default=30, help="Days to forecast (default: 30)")
    rev.add_argument("--context", type=int, default=365, help="Days of history to use (default: 365)")
    rev.add_argument("--frequency", choices=["daily", "weekly", "monthly"], default="daily")
    rev.add_argument("--json", action="store_true", dest="json_output", help="Output raw JSON instead of markdown")

    # -- demand subcommand --
    dem = sub.add_parser("demand", help="Forecast demand by product/collection/SKU")
    dem.add_argument("--group-by", choices=["product", "collection", "sku"], default="product")
    dem.add_argument("--group-value", default="all", help="Specific ID or 'all' for top N")
    dem.add_argument("--metric", choices=["units", "revenue", "orders"], default="units")
    dem.add_argument("--horizon", type=int, default=30)
    dem.add_argument("--top-n", type=int, default=10)
    dem.add_argument("--json", action="store_true", dest="json_output")

    # -- auth subcommand --
    auth_p = sub.add_parser("auth", help="Authenticate with Shopify via browser OAuth")
    auth_p.add_argument("--store", required=True, help="mystore.myshopify.com")

    return parser


async def _run_revenue(args: argparse.Namespace) -> int:
    """Execute the revenue forecast and print results."""
    settings = get_settings()
    backend = create_backend(settings)
    async with ShopifyClient(backend, settings) as shopify:
        end = date.today()
        start = end - timedelta(days=args.context)

        log.info("Fetching %dd of orders...", args.context)
        orders = await shopify.fetch_orders(start.isoformat(), end.isoformat())

        if not orders:
            print("No orders found in the requested date range.", file=sys.stderr)
            return 1

        series_dict = orders_to_daily_series(orders, metric="revenue")
        daily = series_dict["store"]

        freq_code = FREQ_MAP[args.frequency]
        if freq_code != "D":
            daily = resample_series(daily, freq=freq_code, metric="revenue")
        daily = clean_series(daily)

        engine = get_engine(settings)
        engine.load()
        values = daily.values.astype(np.float32)
        point, quantile = engine.forecast(values, horizon=args.horizon)

        result = ForecastResult.from_forecast(
            point=point, quantile=quantile,
            start_date=daily.index[-1] + timedelta(days=1),
            freq="D", metric="revenue",
        )

        if args.json_output:
            out = {
                "dates": result.dates,
                "point_forecast": [round(float(v), 2) for v in result.point_forecast],
                "confidence_bands": {
                    k: [round(float(v), 2) for v in arr]
                    for k, arr in result.confidence_bands.items()
                },
                "metadata": result.metadata,
            }
            print(json.dumps(out, indent=2))
        else:
            print(result.summary())
            print()
            print(result.to_table())

    return 0


async def _run_demand(args: argparse.Namespace) -> int:
    """Execute the demand forecast and print results."""
    settings = get_settings()
    group_by_map = {"product": "product_id", "collection": "collection_id", "sku": "sku"}

    backend = create_backend(settings)
    async with ShopifyClient(backend, settings) as shopify:
        end = date.today()
        start = end - timedelta(days=365)

        log.info("Fetching orders for demand analysis...")
        orders = await shopify.fetch_orders(start.isoformat(), end.isoformat())

        if not orders:
            print("No orders found.", file=sys.stderr)
            return 1

        ts_group_by = group_by_map[args.group_by]
        series_dict = orders_to_daily_series(orders, metric=args.metric, group_by=ts_group_by)

        if not series_dict:
            print(f"No data for grouping by {args.group_by}.", file=sys.stderr)
            return 1

        # Filter / rank
        if args.group_value != "all":
            if args.group_value not in series_dict:
                print(f"Group '{args.group_value}' not found.", file=sys.stderr)
                return 1
            series_dict = {args.group_value: series_dict[args.group_value]}
        else:
            ranked = sorted(series_dict.items(), key=lambda kv: float(kv[1].sum()), reverse=True)[:args.top_n]
            series_dict = dict(ranked)

        engine = get_engine(settings)
        engine.load()

        results: dict[str, dict] = {}
        for group_key, series in series_dict.items():
            values = series.values.astype(np.float32)
            if len(values) < 7:
                results[group_key] = {"error": "insufficient data"}
                continue
            point, quantile = engine.forecast(values, horizon=args.horizon)
            fr = ForecastResult.from_forecast(
                point=point, quantile=quantile,
                start_date=series.index[-1] + timedelta(days=1),
                metric=args.metric,
            )
            results[group_key] = {
                "historical_total": float(series.sum()),
                "projected": float(np.sum(fr.point_forecast)),
                "low_q10": float(np.sum(fr.confidence_bands.get("q10", fr.point_forecast))),
                "high_q90": float(np.sum(fr.confidence_bands.get("q90", fr.point_forecast))),
                "dates": fr.dates,
                "point_forecast": [round(float(v), 2) for v in fr.point_forecast],
            }

        if args.json_output:
            print(json.dumps(results, indent=2))
        else:
            # Markdown table
            lines = [f"| {args.group_by.capitalize()} | Historical | Projected ({args.horizon}d) | Low (10%) | High (90%) |"]
            lines.append("|---|---|---|---|---|")
            for gk, data in results.items():
                if "error" in data:
                    lines.append(f"| {gk} | - | {data['error']} | - | - |")
                else:
                    lines.append(f"| {gk} | {data['historical_total']:,.0f} | {data['projected']:,.0f} | {data['low_q10']:,.0f} | {data['high_q90']:,.0f} |")
            print("\n".join(lines))

    return 0


def _run_auth(args: argparse.Namespace) -> int:
    """Authenticate with Shopify via the Shopify CLI browser OAuth flow."""
    store = args.store

    # Check CLI is available
    if shutil.which("shopify") is None:
        print(
            "Error: Shopify CLI not found on PATH.\n"
            "Install it with: npm install -g @shopify/cli\n"
            "Or see: https://shopify.dev/docs/api/shopify-cli",
            file=sys.stderr,
        )
        return 1

    scopes = ",".join(CLI_AUTH_SCOPES)
    log.info("Authenticating with store %s (scopes: %s)", store, scopes)

    print(
        "\nNote: CLI OAuth cannot grant 'read_all_orders' (protected scope).\n"
        "Order history will be limited to the last 60 days.\n"
        "For full history, create a custom app in Shopify admin and set\n"
        "SHOPIFY_FORECAST_ACCESS_TOKEN in your .env file.\n",
        file=sys.stderr,
    )

    # Run shopify store auth
    result = subprocess.run(
        ["shopify", "store", "auth", "--store", store, "--scopes", scopes],
        capture_output=False,  # Let the user see the browser prompt
    )

    if result.returncode != 0:
        print("Error: shopify store auth failed.", file=sys.stderr)
        return 1

    # Verify auth by running a quick query
    log.info("Verifying authentication...")
    verify = subprocess.run(
        [
            "shopify", "store", "execute",
            "--store", store,
            "--json",
            "--query", "{ shop { ianaTimezone } }",
        ],
        capture_output=True,
        text=True,
    )

    if verify.returncode != 0:
        print(
            f"Warning: Auth succeeded but verification query failed:\n{verify.stderr}",
            file=sys.stderr,
        )
        return 1

    try:
        data = json.loads(verify.stdout)
        tz = data["data"]["shop"]["ianaTimezone"]
        print(f"Authenticated successfully! Store timezone: {tz}")
    except (json.JSONDecodeError, KeyError):
        print("Warning: Auth may have succeeded but could not parse verification response.", file=sys.stderr)
        return 1

    return 0


def main() -> int:
    """Sync entry point for the shopify-forecast console script."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "auth":
        return _run_auth(args)
    elif args.command == "revenue":
        return asyncio.run(_run_revenue(args))
    elif args.command == "demand":
        return asyncio.run(_run_demand(args))
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
