"""Scenario comparison engine for what-if promotional forecasting.

Runs 2-4 named promotional scenarios through the XReg covariate pipeline
and produces side-by-side markdown comparison with recommendation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from shopify_forecast_mcp.core.covariates import build_aligned_covariates
from shopify_forecast_mcp.core.forecaster import COVARIATES_DISCLAIMER
from shopify_forecast_mcp.core.timeseries import clean_series, orders_to_daily_series

logger = logging.getLogger(__name__)


@dataclass
class ScenarioResult:
    """Result of running a single promotional scenario forecast."""

    name: str
    total_revenue: float
    peak_day: str
    peak_value: float
    q10_total: float
    q90_total: float
    daily_forecast: list[float]


async def run_scenarios(
    orders: list[dict],
    scenarios: list[dict],
    horizon_days: int,
    engine: object,
    country: str = "US",
) -> list[ScenarioResult]:
    """Run 2-4 promotional scenarios and return per-scenario forecast results.

    Args:
        orders: Normalized order dicts.
        scenarios: List of 2-4 scenario dicts with keys:
            name, promo_start, promo_end, discount_depth.
        horizon_days: Number of days to forecast.
        engine: ForecastEngine (or mock) with forecast_with_covariates method.
        country: ISO country code for holiday covariates.

    Returns:
        List of ScenarioResult, one per scenario.

    Raises:
        ValueError: If fewer than 2 or more than 4 scenarios provided.
    """
    if len(scenarios) < 2 or len(scenarios) > 4:
        msg = f"Expected 2 to 4 scenarios, got {len(scenarios)}"
        raise ValueError(msg)

    # Build store-level daily series from orders
    series_dict = orders_to_daily_series(orders, metric="revenue")
    daily = series_dict.get("store", pd.Series(dtype=float))
    daily = clean_series(daily)

    values = daily.values
    context_dates = daily.index

    # Compute the start date for the forecast horizon
    last_date = context_dates[-1]
    forecast_dates = pd.date_range(
        start=last_date + pd.Timedelta(days=1),
        periods=horizon_days,
        freq="D",
    )

    results: list[ScenarioResult] = []

    for scenario in scenarios:
        planned_promos = [
            {
                "start": scenario["promo_start"],
                "end": scenario["promo_end"],
                "depth": scenario["discount_depth"],
            }
        ]

        covariates = build_aligned_covariates(
            context_dates=context_dates,
            horizon=horizon_days,
            orders=orders,
            country=country,
            planned_promos=planned_promos,
        )

        point, quantile = engine.forecast_with_covariates(  # type: ignore[union-attr]
            values, covariates, horizon=horizon_days
        )

        # point shape: (1, horizon), quantile shape: (1, horizon, 10)
        point_1d = point[0]
        total_revenue = float(np.sum(point_1d))
        peak_idx = int(np.argmax(point_1d))
        peak_day = forecast_dates[peak_idx].strftime("%Y-%m-%d")
        peak_value = float(point_1d[peak_idx])

        # Quantile channels: index 1 = q10, index 9 = q90
        q10_total = float(np.sum(quantile[0, :, 1]))
        q90_total = float(np.sum(quantile[0, :, 9]))

        results.append(
            ScenarioResult(
                name=scenario["name"],
                total_revenue=total_revenue,
                peak_day=peak_day,
                peak_value=peak_value,
                q10_total=q10_total,
                q90_total=q90_total,
                daily_forecast=point_1d.tolist(),
            )
        )

    return results


def format_scenario_comparison(
    results: list[ScenarioResult],
    horizon_days: int,
) -> str:
    """Format scenario results as a side-by-side markdown comparison table.

    Args:
        results: List of ScenarioResult from run_scenarios.
        horizon_days: Forecast horizon used.

    Returns:
        Markdown string with comparison table, recommendation, and disclaimer.
    """
    lines: list[str] = []

    # Header
    lines.append(f"# Scenario Comparison ({horizon_days}-day horizon)")
    lines.append("")

    # Table header
    header = "| Metric |"
    separator = "|--------|"
    for r in results:
        header += f" {r.name} |"
        separator += "--------|"
    lines.append(header)
    lines.append(separator)

    # Total Revenue row
    row = "| Total Revenue |"
    for r in results:
        row += f" ${r.total_revenue:,.0f} |"
    lines.append(row)

    # Peak Day row
    row = "| Peak Day |"
    for r in results:
        row += f" {r.peak_day} |"
    lines.append(row)

    # Peak Revenue row
    row = "| Peak Revenue |"
    for r in results:
        row += f" ${r.peak_value:,.0f} |"
    lines.append(row)

    # Low Estimate (10%)
    row = "| Low Estimate (10%) |"
    for r in results:
        row += f" ${r.q10_total:,.0f} |"
    lines.append(row)

    # High Estimate (90%)
    row = "| High Estimate (90%) |"
    for r in results:
        row += f" ${r.q90_total:,.0f} |"
    lines.append(row)

    lines.append("")

    # Recommendation
    best = max(results, key=lambda r: r.total_revenue)
    others = [r for r in results if r is not best]
    runner_up = max(others, key=lambda r: r.total_revenue) if others else None

    if runner_up and runner_up.total_revenue > 0:
        lift = (best.total_revenue - runner_up.total_revenue) / runner_up.total_revenue * 100
        lines.append(
            f"**Recommendation:** The **{best.name}** scenario projects the highest "
            f"revenue at ${best.total_revenue:,.0f}, which is {lift:.1f}% higher than "
            f"the next best option ({runner_up.name} at ${runner_up.total_revenue:,.0f})."
        )
    else:
        lines.append(
            f"**Recommendation:** The **{best.name}** scenario projects the highest "
            f"revenue at ${best.total_revenue:,.0f}."
        )

    lines.append("")
    lines.append(COVARIATES_DISCLAIMER)

    return "\n".join(lines)
