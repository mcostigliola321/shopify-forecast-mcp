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
from dateutil.relativedelta import relativedelta

# R9.3: NO imports from shopify_forecast_mcp.mcp -- CLI is MCP-independent
from shopify_forecast_mcp.config import Settings, StoreConfig, get_settings
from shopify_forecast_mcp.core.analytics import (
    analyze_promotion as _analyze_promotion,
    compare_periods as _compare_periods,
)
from shopify_forecast_mcp.core.forecast_result import ForecastResult
from shopify_forecast_mcp.core.forecaster import get_engine
from shopify_forecast_mcp.core.scenarios import format_scenario_comparison, run_scenarios
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


def _resolve_store_config(settings: Settings, store: str) -> StoreConfig | None:
    """Find a StoreConfig by domain or label."""
    if store == settings.shop:
        return StoreConfig(shop=settings.shop, access_token=settings.access_token)
    for sc in settings.stores:
        if sc.shop == store or sc.label == store:
            return sc
    return None


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
    rev.add_argument("--store", default=None, help="Store domain or label (multi-store mode)")

    # -- demand subcommand --
    dem = sub.add_parser("demand", help="Forecast demand by product/collection/SKU")
    dem.add_argument("--group-by", choices=["product", "collection", "sku"], default="product")
    dem.add_argument("--group-value", default="all", help="Specific ID or 'all' for top N")
    dem.add_argument("--metric", choices=["units", "revenue", "orders"], default="units")
    dem.add_argument("--horizon", type=int, default=30)
    dem.add_argument("--top-n", type=int, default=10)
    dem.add_argument("--json", action="store_true", dest="json_output")
    dem.add_argument("--store", default=None, help="Store domain or label (multi-store mode)")

    # -- auth subcommand --
    auth_p = sub.add_parser("auth", help="Authenticate with Shopify via browser OAuth")
    auth_p.add_argument("--store", required=True, help="mystore.myshopify.com")

    # -- promo subcommand (D-21) --
    promo_p = sub.add_parser("promo", help="Analyze a past promotion's impact")
    promo_p.add_argument("--start", required=True, help="Promo start date (YYYY-MM-DD)")
    promo_p.add_argument("--end", required=True, help="Promo end date (YYYY-MM-DD)")
    promo_p.add_argument("--name", default="", help="Optional promo name")
    promo_p.add_argument("--baseline-days", type=int, default=30, help="Baseline period in days (default: 30)")
    promo_p.add_argument("--json", action="store_true", dest="json_output", help="Output JSON instead of markdown")
    promo_p.add_argument("--store", default=None, help="Store domain or label (multi-store mode)")

    # -- compare subcommand (D-23) --
    cmp_p = sub.add_parser("compare", help="Compare two time periods")
    cmp_p.add_argument("--yoy", action="store_true", help="This month vs same month last year")
    cmp_p.add_argument("--mom", action="store_true", help="This month vs last month")
    cmp_p.add_argument("--period-a-start", help="Custom period A start (YYYY-MM-DD)")
    cmp_p.add_argument("--period-a-end", help="Custom period A end (YYYY-MM-DD)")
    cmp_p.add_argument("--period-b-start", help="Custom period B start (YYYY-MM-DD)")
    cmp_p.add_argument("--period-b-end", help="Custom period B end (YYYY-MM-DD)")
    cmp_p.add_argument("--json", action="store_true", dest="json_output", help="Output JSON instead of markdown")
    cmp_p.add_argument("--store", default=None, help="Store domain or label (multi-store mode)")

    # -- scenarios subcommand (R8.6) --
    scn_p = sub.add_parser("scenarios", help="Compare what-if promotional scenarios")
    scn_p.add_argument("--scenarios", required=True, help="JSON array of scenarios or path to JSON file")
    scn_p.add_argument("--horizon", type=int, default=30, help="Days to forecast (default: 30)")
    scn_p.add_argument("--context", type=int, default=365, help="Days of history (default: 365)")
    scn_p.add_argument("--country", default="US", help="Country for holiday covariates (default: US)")
    scn_p.add_argument("--json", action="store_true", dest="json_output", help="Output JSON instead of markdown")
    scn_p.add_argument("--store", default=None, help="Store domain or label (multi-store mode)")

    return parser


async def _run_revenue(args: argparse.Namespace) -> int:
    """Execute the revenue forecast and print results."""
    settings = get_settings()
    if args.store:
        store_config = _resolve_store_config(settings, args.store)
        if store_config is None:
            print(f"Error: Unknown store '{args.store}'", file=sys.stderr)
            return 1
        settings = settings.model_copy(update={
            "shop": store_config.shop,
            "access_token": store_config.access_token,
        })
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
    if args.store:
        store_config = _resolve_store_config(settings, args.store)
        if store_config is None:
            print(f"Error: Unknown store '{args.store}'", file=sys.stderr)
            return 1
        settings = settings.model_copy(update={
            "shop": store_config.shop,
            "access_token": store_config.access_token,
        })
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


async def _run_promo(args: argparse.Namespace) -> int:
    """Execute promotion analysis and print results."""
    # Parse dates (T-05-10)
    try:
        promo_start = date.fromisoformat(args.start)
        promo_end = date.fromisoformat(args.end)
    except ValueError:
        print("Error: Invalid date format. Use YYYY-MM-DD.", file=sys.stderr)
        return 1

    if promo_end < promo_start:
        print("Error: --end must be on or after --start.", file=sys.stderr)
        return 1

    promo_duration = (promo_end - promo_start).days + 1
    baseline_start = promo_start - timedelta(days=args.baseline_days + 7)
    fetch_end = promo_end + timedelta(days=promo_duration + 7)

    settings = get_settings()
    if args.store:
        store_config = _resolve_store_config(settings, args.store)
        if store_config is None:
            print(f"Error: Unknown store '{args.store}'", file=sys.stderr)
            return 1
        settings = settings.model_copy(update={
            "shop": store_config.shop,
            "access_token": store_config.access_token,
        })
    backend = create_backend(settings)
    async with ShopifyClient(backend, settings) as shopify:
        log.info("Fetching orders for promotion analysis...")
        orders = await shopify.fetch_orders(
            baseline_start.isoformat(), fetch_end.isoformat()
        )

        if not orders:
            print("No orders found in the promotion date range.", file=sys.stderr)
            return 1

        result = _analyze_promotion(
            orders, promo_start, promo_end, args.baseline_days, args.name
        )

        if args.json_output:
            out = {
                "metadata": result.metadata,
                "sections": [
                    {
                        "heading": s.heading,
                        "headers": s.table_headers,
                        "rows": s.table_rows,
                    }
                    for s in result.sections
                ],
                "summary": result.summary,
                "recommendations": result.recommendations,
            }
            print(json.dumps(out, indent=2))
        else:
            print(result.to_markdown())

    return 0


def _resolve_compare_dates(
    args: argparse.Namespace,
) -> tuple[date, date, date, date]:
    """Resolve period A and B dates from --yoy, --mom, or custom flags.

    Returns (a_start, a_end, b_start, b_end).
    Raises ValueError if dates cannot be resolved.
    """
    if args.yoy:
        today = date.today()
        b_start = today.replace(day=1)
        b_end = today
        a_start = b_start - relativedelta(years=1)
        a_end = a_start + (b_end - b_start)
        return (a_start, a_end, b_start, b_end)

    if args.mom:
        today = date.today()
        b_start = today.replace(day=1)
        b_end = today
        a_start = b_start - relativedelta(months=1)
        a_end = b_start - timedelta(days=1)
        return (a_start, a_end, b_start, b_end)

    # Custom date ranges -- all four required
    if not all([args.period_a_start, args.period_a_end, args.period_b_start, args.period_b_end]):
        raise ValueError(
            "Provide --yoy, --mom, or all four custom date flags "
            "(--period-a-start, --period-a-end, --period-b-start, --period-b-end)."
        )

    a_start = date.fromisoformat(args.period_a_start)
    a_end = date.fromisoformat(args.period_a_end)
    b_start = date.fromisoformat(args.period_b_start)
    b_end = date.fromisoformat(args.period_b_end)
    return (a_start, a_end, b_start, b_end)


async def _run_compare(args: argparse.Namespace) -> int:
    """Execute period comparison and print results."""
    try:
        a_start, a_end, b_start, b_end = _resolve_compare_dates(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    fetch_start = min(a_start, b_start)
    fetch_end = max(a_end, b_end)

    settings = get_settings()
    if args.store:
        store_config = _resolve_store_config(settings, args.store)
        if store_config is None:
            print(f"Error: Unknown store '{args.store}'", file=sys.stderr)
            return 1
        settings = settings.model_copy(update={
            "shop": store_config.shop,
            "access_token": store_config.access_token,
        })
    backend = create_backend(settings)
    async with ShopifyClient(backend, settings) as shopify:
        log.info("Fetching orders for period comparison...")
        orders = await shopify.fetch_orders(
            fetch_start.isoformat(), fetch_end.isoformat()
        )

        if not orders:
            print("No orders found in the comparison date range.", file=sys.stderr)
            return 1

        result = _compare_periods(orders, a_start, a_end, b_start, b_end)

        if args.json_output:
            out = {
                "metadata": result.metadata,
                "sections": [
                    {
                        "heading": s.heading,
                        "headers": s.table_headers,
                        "rows": s.table_rows,
                    }
                    for s in result.sections
                ],
                "summary": result.summary,
                "recommendations": result.recommendations,
            }
            print(json.dumps(out, indent=2))
        else:
            print(result.to_markdown())

    return 0


async def _run_scenarios(args: argparse.Namespace) -> int:
    """Execute scenario comparison and print results."""
    # Parse --scenarios: JSON string or file path
    raw = args.scenarios.strip()
    if raw.startswith("["):
        try:
            scenario_list = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"Error: Invalid JSON in --scenarios: {exc}", file=sys.stderr)
            return 1
    else:
        # Treat as file path
        import os

        if not os.path.isfile(raw):
            print(f"Error: File not found: {raw}", file=sys.stderr)
            return 1
        with open(raw) as f:
            try:
                scenario_list = json.load(f)
            except json.JSONDecodeError as exc:
                print(f"Error: Invalid JSON in file {raw}: {exc}", file=sys.stderr)
                return 1

    if not isinstance(scenario_list, list):
        print("Error: --scenarios must be a JSON array.", file=sys.stderr)
        return 1

    # Validate scenario dicts
    required_keys = {"name", "promo_start", "promo_end", "discount_depth"}
    for i, s in enumerate(scenario_list):
        if not isinstance(s, dict):
            print(f"Error: Scenario {i} is not a dict.", file=sys.stderr)
            return 1
        missing = required_keys - set(s.keys())
        if missing:
            print(f"Error: Scenario {i} missing keys: {missing}", file=sys.stderr)
            return 1

    settings = get_settings()
    if args.store:
        store_config = _resolve_store_config(settings, args.store)
        if store_config is None:
            print(f"Error: Unknown store '{args.store}'", file=sys.stderr)
            return 1
        settings = settings.model_copy(update={
            "shop": store_config.shop,
            "access_token": store_config.access_token,
        })
    backend = create_backend(settings)
    async with ShopifyClient(backend, settings) as shopify:
        end = date.today()
        start = end - timedelta(days=args.context)

        log.info("Fetching %dd of orders for scenario comparison...", args.context)
        orders = await shopify.fetch_orders(start.isoformat(), end.isoformat())

        if not orders:
            print("No orders found in the requested date range.", file=sys.stderr)
            return 1

        engine = get_engine(settings)
        engine.load()

        results = await run_scenarios(
            orders, scenario_list, args.horizon, engine, args.country
        )

        if args.json_output:
            import dataclasses

            out = [dataclasses.asdict(r) for r in results]
            print(json.dumps(out, indent=2))
        else:
            print(format_scenario_comparison(results, args.horizon))

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
    elif args.command == "promo":
        return asyncio.run(_run_promo(args))
    elif args.command == "compare":
        return asyncio.run(_run_compare(args))
    elif args.command == "scenarios":
        return asyncio.run(_run_scenarios(args))
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
