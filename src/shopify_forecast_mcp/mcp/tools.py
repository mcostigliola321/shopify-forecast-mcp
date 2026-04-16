"""MCP tool handlers for shopify-forecast-mcp."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Literal

import numpy as np
from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from pydantic import BaseModel, Field

from shopify_forecast_mcp.core.forecast_result import ForecastResult
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
        # Compute date range
        end = date.today()
        start = end - timedelta(days=params.context_days)

        await ctx.info(f"Pulling {params.context_days}d of order history...")
        orders = await app.shopify.fetch_orders(
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
        end = date.today()
        start = end - timedelta(days=365)

        await ctx.info("Fetching order history for demand analysis...")
        orders = await app.shopify.fetch_orders(
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

        rows.append("")
        rows.append(
            f"*{params.metric.capitalize()} metric, {params.horizon_days}-day "
            f"horizon, top {len(series_dict)} by volume*"
        )

        return "\n".join(rows)

    except Exception as e:
        log.exception("forecast_demand failed")
        return f"**Error running forecast_demand**\n\n{type(e).__name__}: {e}"
