"""MCP tool handlers for shopify-forecast-mcp."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Literal

import numpy as np
from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from pydantic import BaseModel, Field

from shopify_forecast_mcp.core.inventory import (
    compute_reorder_alerts,
    format_reorder_alerts,
)
from shopify_forecast_mcp.core.analytics import (
    analyze_promotion as _analyze_promotion,
    compare_periods as _compare_periods,
    detect_anomalies as _detect_anomalies,
    get_seasonality as _get_seasonality,
)
from shopify_forecast_mcp.core.forecast_result import ForecastResult
from shopify_forecast_mcp.core.scenarios import (
    format_scenario_comparison,
    run_scenarios,
)
from shopify_forecast_mcp.core.timeseries import (
    clean_series,
    orders_to_daily_series,
    resample_series,
)
from shopify_forecast_mcp.mcp.server import AppContext, mcp

log = logging.getLogger(__name__)

# Frequency mapping: user-facing names -> pandas freq codes
FREQ_MAP: dict[str, str] = {"daily": "D", "weekly": "W", "monthly": "M"}


class ForecastRevenueParams(BaseModel):
    """Input schema for the forecast_revenue tool."""

    horizon_days: int = Field(
        30, ge=1, le=365, description="Number of days to forecast into the future"
    )
    context_days: int = Field(
        365, ge=30, le=1095, description="Days of historical data to use as context"
    )
    frequency: Literal["daily", "weekly", "monthly"] = Field(
        "daily", description="Aggregation frequency for the forecast"
    )
    include_chart_data: bool = Field(
        False, description="If true, append raw forecast values as a JSON block"
    )
    store: str | None = Field(None, description="Store domain or label (multi-store mode)")


@mcp.tool()
async def forecast_revenue(
    params: ForecastRevenueParams,
    ctx: Context[ServerSession, AppContext],
) -> str:
    """Forecast total store revenue over a future horizon using TimesFM 2.5.

    Returns a markdown summary and table with point forecast and 80% confidence band (q10-q90).
    """
    app: AppContext = ctx.request_context.lifespan_context
    try:
        try:
            client = app.get_client(params.store)
        except ValueError as e:
            return f"**Store not found**\n\n{e}"

        # Compute date range
        end = date.today()
        start = end - timedelta(days=params.context_days)

        await ctx.info(f"Pulling {params.context_days}d of order history...")
        orders = await client.fetch_orders(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )

        if not orders:
            return (
                "**No orders found** in the requested date range. "
                "Check your Shopify connection and date range."
            )

        # Aggregate to daily series (store-level revenue)
        series_dict = orders_to_daily_series(orders, metric="revenue", group_by=None)
        daily_series = series_dict["store"]

        # Resample if requested
        freq_code = FREQ_MAP[params.frequency]
        if freq_code != "D":
            daily_series = resample_series(
                daily_series, freq=freq_code, metric="revenue"
            )

        # Clean outliers
        daily_series = clean_series(daily_series)

        # Convert to numpy for forecaster
        values = daily_series.values.astype(np.float32)

        await ctx.info(
            f"Running TimesFM forecast (horizon={params.horizon_days}d)..."
        )
        point, quantile = app.forecaster.forecast(values, horizon=params.horizon_days)

        # Build ForecastResult
        last_date = daily_series.index[-1]
        next_date = last_date + timedelta(days=1)
        result = ForecastResult.from_forecast(
            point=point,
            quantile=quantile,
            start_date=next_date,
            freq="D",
            metric="revenue",
            context_days=params.context_days,
            horizon_days=params.horizon_days,
        )

        # Build response
        parts = [result.summary(), "", result.to_table()]

        if params.include_chart_data:
            import json

            chart_data = {
                "dates": result.dates,
                "point_forecast": [
                    round(float(v), 2) for v in result.point_forecast
                ],
                "q10": [
                    round(float(v), 2)
                    for v in result.confidence_bands.get("q10", [])
                ],
                "q90": [
                    round(float(v), 2)
                    for v in result.confidence_bands.get("q90", [])
                ],
            }
            parts.extend(["", "```json", json.dumps(chart_data, indent=2), "```"])

        return "\n".join(parts)

    except Exception as e:
        log.exception("forecast_revenue failed")
        return f"**Error running forecast_revenue**\n\n{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# forecast_demand
# ---------------------------------------------------------------------------


class ForecastDemandParams(BaseModel):
    """Input schema for the forecast_demand tool."""

    group_by: Literal["product", "collection", "sku"] = Field(
        "product",
        description="Dimension to group demand by: product, collection, or sku",
    )
    group_value: str = Field(
        "all",
        description="Specific group identifier to forecast, or 'all' for top N groups",
    )
    metric: Literal["units", "revenue", "orders"] = Field(
        "units",
        description="Demand metric to forecast",
    )
    horizon_days: int = Field(30, ge=1, le=365, description="Days to forecast")
    top_n: int = Field(
        10, ge=1, le=50, description="Number of top groups when group_value='all'"
    )
    lead_time_days: int = Field(
        14,
        ge=1,
        le=365,
        description="Lead time in days for reorder calculation (default: 14)",
    )
    safety_factor: float = Field(
        1.2,
        ge=1.0,
        le=3.0,
        description="Safety factor for reorder qty (default: 1.2, i.e. 20% buffer)",
    )
    store: str | None = Field(None, description="Store domain or label (multi-store mode)")


@mcp.tool()
async def forecast_demand(
    params: ForecastDemandParams,
    ctx: Context[ServerSession, AppContext],
) -> str:
    """Forecast demand by product, collection, or SKU using TimesFM 2.5.

    Returns a ranked markdown table showing projected demand per group
    with confidence bands. When group_value is 'all', forecasts the top N
    groups by historical volume.
    """
    app: AppContext = ctx.request_context.lifespan_context
    try:
        try:
            client = app.get_client(params.store)
        except ValueError as e:
            return f"**Store not found**\n\n{e}"

        end = date.today()
        start = end - timedelta(days=365)

        await ctx.info("Fetching order history for demand analysis...")
        orders = await client.fetch_orders(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )

        if not orders:
            return "**No orders found** in the last 365 days. Cannot forecast demand."

        # Map user-facing group_by to timeseries GroupBy values
        group_by_map = {
            "product": "product_id",
            "collection": "collection_id",
            "sku": "sku",
        }
        ts_group_by = group_by_map[params.group_by]

        # For collection grouping, product_collection_map is required
        product_collection_map = None
        if params.group_by == "collection":
            # MVP: collection mapping requires product-collection data
            # which is not yet wired. Catch the ValueError below.
            pass

        # Aggregate orders into per-group daily series
        try:
            series_dict = orders_to_daily_series(
                orders,
                metric=params.metric,
                group_by=ts_group_by,
                product_collection_map=product_collection_map,
            )
        except ValueError as exc:
            return (
                f"**Cannot group by {params.group_by}**: {exc}\n\n"
                "Try grouping by `product` or `sku` instead."
            )

        if not series_dict:
            return f"**No data** for grouping by {params.group_by}."

        # Filter to specific group or top N
        if params.group_value != "all":
            if params.group_value not in series_dict:
                available = ", ".join(list(series_dict.keys())[:5])
                return (
                    f"**Group '{params.group_value}' not found.**\n\n"
                    f"Available {params.group_by}s (showing first 5): {available}"
                )
            series_dict = {params.group_value: series_dict[params.group_value]}
        else:
            # Rank by total historical volume, take top N
            ranked = sorted(
                series_dict.items(),
                key=lambda kv: float(kv[1].sum()),
                reverse=True,
            )[: params.top_n]
            series_dict = dict(ranked)

        # Forecast each group
        await ctx.info(
            f"Forecasting {len(series_dict)} group(s) over {params.horizon_days}d..."
        )

        rows: list[str] = []
        rows.append(f"# Demand Forecast by {params.group_by.capitalize()}")
        rows.append("")
        rows.append(
            f"| {params.group_by.capitalize()} | Historical Total "
            f"| Projected ({params.horizon_days}d) | Low (10%) | High (90%) |"
        )
        rows.append("|---|---|---|---|---|")

        # Track forecast results for reorder alerts
        forecast_results: dict[str, dict] = {}

        for group_key, series in series_dict.items():
            historical_total = float(series.sum())
            values = series.values.astype(np.float32)

            if len(values) < 7:
                rows.append(
                    f"| {group_key} | {historical_total:,.0f} "
                    "| Insufficient data | - | - |"
                )
                continue

            point, quantile = app.forecaster.forecast(
                values, horizon=params.horizon_days
            )

            result = ForecastResult.from_forecast(
                point=point,
                quantile=quantile,
                start_date=series.index[-1] + timedelta(days=1),
                freq="D",
                metric=params.metric,
                group_key=group_key,
            )

            projected = float(np.sum(result.point_forecast))
            low = float(
                np.sum(result.confidence_bands.get("q10", result.point_forecast))
            )
            high = float(
                np.sum(result.confidence_bands.get("q90", result.point_forecast))
            )

            rows.append(
                f"| {group_key} | {historical_total:,.0f} "
                f"| {projected:,.0f} | {low:,.0f} | {high:,.0f} |"
            )

            # Store projected total for reorder alert demand map
            forecast_results[group_key] = {"projected": projected}

        rows.append("")
        rows.append(
            f"*{params.metric.capitalize()} metric, {params.horizon_days}-day "
            f"horizon, top {len(series_dict)} by volume*"
        )

        # Inventory-aware reorder alerts (D-05, D-09: graceful degradation)
        reorder_section = ""
        try:
            await ctx.info("Checking inventory levels for reorder alerts...")
            inventory = await client.fetch_inventory()
            if inventory:
                # Build daily demand map: product_id -> avg daily demand from forecast
                demand_map: dict[str, float] = {}
                for group_key, data_dict in forecast_results.items():
                    if "projected" in data_dict:
                        daily_avg = data_dict["projected"] / params.horizon_days
                        demand_map[group_key] = daily_avg
                alerts = compute_reorder_alerts(
                    inventory,
                    demand_map,
                    lead_time_days=params.lead_time_days,
                    safety_factor=params.safety_factor,
                )
                reorder_section = format_reorder_alerts(alerts)
        except Exception as inv_err:
            # D-09: graceful degradation -- log warning, continue without alerts
            log.warning("Could not fetch inventory for reorder alerts: %s", inv_err)

        if reorder_section:
            rows.append(reorder_section)

        return "\n".join(rows)

    except Exception as e:
        log.exception("forecast_demand failed")
        return f"**Error running forecast_demand**\n\n{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# analyze_promotion
# ---------------------------------------------------------------------------


class AnalyzePromotionParams(BaseModel):
    """Input schema for the analyze_promotion tool."""

    promo_start: str = Field(..., description="Promo start date (YYYY-MM-DD)")
    promo_end: str = Field(..., description="Promo end date (YYYY-MM-DD)")
    promo_name: str = Field("", description="Optional promo name for labeling")
    baseline_days: int = Field(
        30, ge=7, le=365, description="Days before promo to use as baseline"
    )
    store: str | None = Field(None, description="Store domain or label (multi-store mode)")


@mcp.tool()
async def analyze_promotion(
    params: AnalyzePromotionParams,
    ctx: Context[ServerSession, AppContext],
) -> str:
    """Analyze a past promotion's impact vs baseline: revenue lift, order lift, AOV change, post-promo hangover, and product cannibalization."""
    app: AppContext = ctx.request_context.lifespan_context
    try:
        try:
            client = app.get_client(params.store)
        except ValueError as e:
            return f"**Store not found**\n\n{e}"

        # Parse dates (T-05-08)
        try:
            promo_start = date.fromisoformat(params.promo_start)
            promo_end = date.fromisoformat(params.promo_end)
        except ValueError:
            return (
                "**Error running analyze_promotion**\n\n"
                "Invalid date format. Use YYYY-MM-DD."
            )

        if promo_end < promo_start:
            return (
                "**Error running analyze_promotion**\n\n"
                "promo_end must be on or after promo_start."
            )

        # Compute fetch window with buffer
        promo_duration = (promo_end - promo_start).days + 1
        baseline_start = promo_start - timedelta(days=params.baseline_days + 7)
        fetch_end = promo_end + timedelta(days=promo_duration + 7)

        await ctx.info("Fetching orders for promotion analysis...")
        orders = await client.fetch_orders(
            start_date=baseline_start.isoformat(),
            end_date=fetch_end.isoformat(),
        )

        result = _analyze_promotion(
            orders, promo_start, promo_end, params.baseline_days, params.promo_name
        )
        return result.to_markdown()

    except Exception as e:
        log.exception("analyze_promotion failed")
        return f"**Error running analyze_promotion**\n\n{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# compare_periods
# ---------------------------------------------------------------------------


class ComparePeriodsParams(BaseModel):
    """Input schema for the compare_periods tool."""

    period_a_start: str = Field(..., description="Period A start (YYYY-MM-DD)")
    period_a_end: str = Field(..., description="Period A end (YYYY-MM-DD)")
    period_b_start: str = Field(..., description="Period B start (YYYY-MM-DD)")
    period_b_end: str = Field(..., description="Period B end (YYYY-MM-DD)")
    metrics: list[str] | None = Field(
        None, description="Metrics to compare (default: all 6)"
    )
    group_by: str | None = Field(
        None, description="Optional: product_id, collection_id, or sku"
    )
    store: str | None = Field(None, description="Store domain or label (multi-store mode)")


@mcp.tool()
async def compare_periods(
    params: ComparePeriodsParams,
    ctx: Context[ServerSession, AppContext],
) -> str:
    """Compare two time periods across revenue, orders, units, AOV, discount rate, and units per order."""
    app: AppContext = ctx.request_context.lifespan_context
    try:
        try:
            client = app.get_client(params.store)
        except ValueError as e:
            return f"**Store not found**\n\n{e}"

        # Parse dates (T-05-08)
        try:
            a_start = date.fromisoformat(params.period_a_start)
            a_end = date.fromisoformat(params.period_a_end)
            b_start = date.fromisoformat(params.period_b_start)
            b_end = date.fromisoformat(params.period_b_end)
        except ValueError:
            return (
                "**Error running compare_periods**\n\n"
                "Invalid date format. Use YYYY-MM-DD."
            )

        if a_end < a_start or b_end < b_start:
            return (
                "**Error running compare_periods**\n\n"
                "End date must be on or after start date for both periods."
            )

        # Fetch orders spanning both periods
        fetch_start = min(a_start, b_start)
        fetch_end = max(a_end, b_end)

        await ctx.info("Fetching orders for period comparison...")
        orders = await client.fetch_orders(
            start_date=fetch_start.isoformat(),
            end_date=fetch_end.isoformat(),
        )

        metrics_tuple = tuple(params.metrics) if params.metrics else None
        result = _compare_periods(
            orders, a_start, a_end, b_start, b_end, metrics_tuple
        )
        return result.to_markdown()

    except Exception as e:
        log.exception("compare_periods failed")
        return f"**Error running compare_periods**\n\n{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# get_seasonality
# ---------------------------------------------------------------------------


class GetSeasonalityParams(BaseModel):
    """Input schema for the get_seasonality tool."""

    lookback_days: int = Field(
        365, ge=30, le=1095, description="Days of history to analyze"
    )
    granularity: Literal["day_of_week", "monthly", "quarterly"] = Field(
        "day_of_week", description="Seasonality granularity"
    )
    metric: Literal["revenue", "orders", "units", "aov"] = Field(
        "revenue", description="Metric to analyze"
    )
    store: str | None = Field(None, description="Store domain or label (multi-store mode)")


@mcp.tool()
async def get_seasonality(
    params: GetSeasonalityParams,
    ctx: Context[ServerSession, AppContext],
) -> str:
    """Identify seasonal patterns in store data by day of week, month, or quarter."""
    app: AppContext = ctx.request_context.lifespan_context
    try:
        try:
            client = app.get_client(params.store)
        except ValueError as e:
            return f"**Store not found**\n\n{e}"

        end = date.today()
        start = end - timedelta(days=params.lookback_days)

        await ctx.info("Fetching orders for seasonality analysis...")
        orders = await client.fetch_orders(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )

        if not orders:
            return (
                "**No orders found** in the requested date range. "
                "Cannot analyze seasonality."
            )

        # Build daily series
        series_dict = orders_to_daily_series(orders, metric=params.metric)
        daily_series = series_dict["store"]

        result = _get_seasonality(daily_series, granularity=params.granularity)
        return result.to_markdown()

    except Exception as e:
        log.exception("get_seasonality failed")
        return f"**Error running get_seasonality**\n\n{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# detect_anomalies
# ---------------------------------------------------------------------------


class DetectAnomaliesParams(BaseModel):
    """Input schema for the detect_anomalies tool."""

    lookback_days: int = Field(
        90, ge=14, le=365, description="Days to look back for anomalies"
    )
    sensitivity: Literal["low", "medium", "high"] = Field(
        "medium",
        description="Anomaly sensitivity: low (q10/q90), medium (q20/q80), high (q30/q70)",
    )
    metric: Literal["revenue", "orders", "units", "aov"] = Field(
        "revenue", description="Single metric to check for anomalies"
    )
    store: str | None = Field(None, description="Store domain or label (multi-store mode)")


@mcp.tool()
async def detect_anomalies(
    params: DetectAnomaliesParams,
    ctx: Context[ServerSession, AppContext],
) -> str:
    """Detect anomalous days where actual values fell outside expected forecast bands."""
    app: AppContext = ctx.request_context.lifespan_context
    try:
        try:
            client = app.get_client(params.store)
        except ValueError as e:
            return f"**Store not found**\n\n{e}"

        # Fetch extra context for better forecast quality
        end = date.today()
        extra_context = 90
        start = end - timedelta(days=params.lookback_days + extra_context)

        await ctx.info("Fetching orders for anomaly detection...")
        orders = await client.fetch_orders(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )

        if not orders:
            return (
                "**No orders found** in the requested date range. "
                "Cannot detect anomalies."
            )

        # Build daily series
        series_dict = orders_to_daily_series(orders, metric=params.metric)
        daily_series = series_dict["store"]

        if len(daily_series) < 14:
            return (
                "**Insufficient data** -- need at least 14 days of history "
                "for anomaly detection."
            )

        await ctx.info("Running forecast to establish expected values...")

        # Split series: use early portion as context, forecast the lookback window
        lookback = min(params.lookback_days, len(daily_series) - 7)
        context_len = len(daily_series) - lookback

        if context_len < 7:
            # Not enough context -- use all data as context, smaller lookback
            context_len = 7
            lookback = len(daily_series) - context_len

        context_series = daily_series.iloc[:context_len]
        actuals_series = daily_series.iloc[context_len:]

        # Forecast the lookback window
        context_values = context_series.values.astype(np.float32)
        point, quantile = app.forecaster.forecast(
            context_values, horizon=lookback
        )

        # Build ForecastResult for the lookback window
        forecast_start = context_series.index[-1] + timedelta(days=1)
        forecast_result = ForecastResult.from_forecast(
            point=point,
            quantile=quantile,
            start_date=forecast_start,
            freq="D",
            metric=params.metric,
        )

        # Build known_events from holidays if covariates module available
        known_events: list[dict[str, str]] = []
        try:
            from shopify_forecast_mcp.core.covariates import _get_country_holidays

            holiday_dict = _get_country_holidays("US")
            for d in actuals_series.index:
                d_date = d.date() if hasattr(d, "date") else d
                if d_date in holiday_dict:
                    known_events.append(
                        {"date": d_date.isoformat(), "label": holiday_dict[d_date]}
                    )
        except (ImportError, Exception):
            pass  # Covariates module not available -- skip event labeling

        result = _detect_anomalies(
            actuals_series,
            forecast_result,
            params.sensitivity,
            lookback,
            known_events,
        )
        return result.to_markdown()

    except Exception as e:
        log.exception("detect_anomalies failed")
        return f"**Error running detect_anomalies**\n\n{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# compare_scenarios
# ---------------------------------------------------------------------------


class ScenarioInput(BaseModel):
    """Schema for a single promotional scenario."""

    name: str = Field(..., description="Scenario name, e.g. 'Aggressive'")
    promo_start: str = Field(..., description="Promo start date (YYYY-MM-DD)")
    promo_end: str = Field(..., description="Promo end date (YYYY-MM-DD)")
    discount_depth: float = Field(
        ..., ge=0.0, le=1.0, description="Discount depth (0-1)"
    )


class CompareScenariosParams(BaseModel):
    """Input schema for the compare_scenarios tool."""

    scenarios: list[ScenarioInput] = Field(
        ..., min_length=2, max_length=4, description="2-4 named scenarios"
    )
    horizon_days: int = Field(30, ge=1, le=365, description="Days to forecast")
    context_days: int = Field(
        365, ge=30, le=1095, description="Days of historical data"
    )
    country: str = Field("US", description="Country for holiday covariates")
    store: str | None = Field(None, description="Store domain or label (multi-store mode)")


@mcp.tool()
async def compare_scenarios(
    params: CompareScenariosParams,
    ctx: Context[ServerSession, AppContext],
) -> str:
    """Compare 2-4 promotional scenarios with what-if forecasting.

    Each scenario specifies a promo period and discount depth. Returns a
    side-by-side markdown table with revenue projections, confidence bands,
    and a recommendation for the best-performing scenario.
    """
    app: AppContext = ctx.request_context.lifespan_context
    try:
        try:
            client = app.get_client(params.store)
        except ValueError as e:
            return f"**Store not found**\n\n{e}"

        end = date.today()
        start = end - timedelta(days=params.context_days)

        await ctx.info(
            f"Pulling {params.context_days}d of order history for scenario comparison..."
        )
        orders = await client.fetch_orders(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )

        if not orders:
            return "**No orders found** in the requested date range."

        scenario_dicts = [s.model_dump() for s in params.scenarios]
        await ctx.info(
            f"Running {len(scenario_dicts)} scenarios over {params.horizon_days}d horizon..."
        )
        results = await run_scenarios(
            orders, scenario_dicts, params.horizon_days, app.forecaster, params.country
        )
        return format_scenario_comparison(results, params.horizon_days)

    except ValueError as e:
        return f"**Error running compare_scenarios**\n\n{e}"
    except Exception as e:
        log.exception("compare_scenarios failed")
        return f"**Error running compare_scenarios**\n\n{type(e).__name__}: {e}"
