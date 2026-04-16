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
