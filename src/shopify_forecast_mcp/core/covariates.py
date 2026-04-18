"""Covariate engineering for TimesFM XReg integration.

All covariates activate together when enabled (D-18). Holiday proximity
window is fixed at -7/+3 days (D-19).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta

import numpy as np
import pandas as pd

try:
    import holidays as holidays_lib
except ImportError:  # pragma: no cover
    holidays_lib = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _compute_holiday_proximity(
    date_range: pd.DatetimeIndex,
    country_holidays: dict,
) -> list[float]:
    """Compute normalized proximity to nearest holiday for each date.

    Window: -7 days before to +3 days after (D-19).
    Returns 0.0 if on holiday, negative normalized values before,
    positive normalized values after. 0.0 if outside window.
    """
    # Collect all holiday dates in an expanded range for proximity calculation
    first_date = date_range[0].date() - timedelta(days=10)
    last_date = date_range[-1].date() + timedelta(days=10)
    holiday_dates: list[date] = []
    current = first_date
    while current <= last_date:
        if current in country_holidays:
            holiday_dates.append(current)
        current += timedelta(days=1)

    result: list[float] = []
    for ts in date_range:
        d = ts.date()
        if d in country_holidays:
            result.append(0.0)
            continue

        # Find distance to nearest holiday
        min_dist: int | None = None
        for hd in holiday_dates:
            dist = (d - hd).days  # negative = before holiday, positive = after
            if min_dist is None or abs(dist) < abs(min_dist):
                min_dist = dist

        if min_dist is None:
            result.append(0.0)
            continue

        # Check if within window: -7 (before) to +3 (after)
        # dist < 0 means d is before the holiday
        # dist > 0 means d is after the holiday
        if -7 <= min_dist <= 3:
            if min_dist < 0:
                # Before holiday: normalize by dividing by 7
                result.append(min_dist / 7.0)
            else:
                # After holiday: normalize by dividing by 3
                result.append(min_dist / 3.0)
        else:
            result.append(0.0)

    return result


def _compute_discount_covariates(
    date_range: pd.DatetimeIndex,
    orders: list[dict],
) -> tuple[list[float], list[float]]:
    """Compute has_discount and discount_depth covariates from orders.

    Returns:
        (has_discount, discount_depth) -- each a list[float] aligned to date_range.
    """
    # Build date -> orders mapping
    orders_by_date: dict[str, list[dict]] = defaultdict(list)
    last_order_date: str | None = None
    for order in orders:
        d = order["local_date"]
        orders_by_date[d].append(order)
        if last_order_date is None or d > last_order_date:
            last_order_date = d

    has_discount: list[float] = []
    discount_depth: list[float] = []

    for ts in date_range:
        d_str = ts.strftime("%Y-%m-%d")

        # Future dates (beyond last order): 0.0 for both
        if last_order_date is not None and d_str > last_order_date:
            has_discount.append(0.0)
            discount_depth.append(0.0)
            continue

        day_orders = orders_by_date.get(d_str, [])
        if not day_orders:
            has_discount.append(0.0)
            discount_depth.append(0.0)
            continue

        # has_discount: 1.0 if any order has discount_codes
        any_discount = any(
            len(o.get("discount_codes", [])) > 0 for o in day_orders
        )
        has_discount.append(1.0 if any_discount else 0.0)

        # discount_depth: average of total_discounts/subtotal across orders
        depths: list[float] = []
        for o in day_orders:
            subtotal = o.get("subtotal", 0.0)
            total_discounts = o.get("total_discounts", 0.0)
            if subtotal > 0:
                depths.append(total_discounts / subtotal)
            else:
                depths.append(0.0)

        discount_depth.append(sum(depths) / len(depths) if depths else 0.0)

    return has_discount, discount_depth


def _get_country_holidays(country: str, years: list[int]) -> dict:
    """Get holidays for the given country and years with fallback (T-05-05)."""
    if holidays_lib is None:
        logger.warning("holidays package not installed; holiday covariates will be empty")
        return {}

    try:
        return holidays_lib.country_holidays(country, years=years)
    except KeyError:
        logger.warning(
            "Unknown country code %r for holiday detection; falling back to US",
            country,
        )
        return holidays_lib.country_holidays("US", years=years)


def build_covariates(
    date_range: pd.DatetimeIndex,
    orders: list[dict],
    country: str = "US",
    custom_events: list[dict] | None = None,
) -> dict[str, list[list[float]]]:
    """Build covariate arrays from order data and holiday calendars.

    Args:
        date_range: DatetimeIndex spanning the full period (context + horizon).
        orders: List of normalized order dicts.
        country: ISO country code for holiday detection.
        custom_events: Optional list of {"date": "YYYY-MM-DD", "label": str, "type": str}.

    Returns:
        Dict with each value wrapped in outer list for batch dimension:
        {"day_of_week": [[v1, v2, ...]], ...}
    """
    # Determine years for holiday calendar
    years = sorted(set(ts.year for ts in date_range))
    country_hols = _get_country_holidays(country, years)

    # 1. day_of_week: Monday=0.0, Sunday=1.0
    day_of_week = [d.dayofweek / 6.0 for d in date_range]

    # 2. is_weekend: Sat/Sun = 1.0
    is_weekend = [1.0 if d.dayofweek >= 5 else 0.0 for d in date_range]

    # 3. month: Jan=0.0, Dec=1.0
    month = [(d.month - 1) / 11.0 for d in date_range]

    # 4. is_holiday
    is_holiday = [1.0 if d.date() in country_hols else 0.0 for d in date_range]

    # 5. holiday_proximity
    holiday_proximity = _compute_holiday_proximity(date_range, country_hols)

    # 6-7. discount covariates
    has_discount, discount_depth = _compute_discount_covariates(date_range, orders)

    result: dict[str, list[list[float]]] = {
        "day_of_week": [day_of_week],
        "is_weekend": [is_weekend],
        "month": [month],
        "is_holiday": [is_holiday],
        "holiday_proximity": [holiday_proximity],
        "has_discount": [has_discount],
        "discount_depth": [discount_depth],
    }

    # Custom events
    if custom_events:
        ce_values: list[float] = []
        event_dates = set()
        for evt in custom_events:
            event_dates.add(evt["date"])

        for ts in date_range:
            d_str = ts.strftime("%Y-%m-%d")
            if d_str in event_dates:
                ce_values.append(1.0)
            else:
                # Proximity decay: check distance to nearest event
                min_dist: int | None = None
                for evt_date_str in event_dates:
                    evt_date = pd.Timestamp(evt_date_str).date()
                    dist = abs((ts.date() - evt_date).days)
                    if min_dist is None or dist < min_dist:
                        min_dist = dist
                if min_dist is not None and min_dist <= 3:
                    # Decay: 1.0 at event, decreasing with distance
                    ce_values.append(max(0.0, 1.0 - min_dist / 4.0))
                else:
                    ce_values.append(0.0)

        result["custom_event"] = [ce_values]

    return result


def build_future_covariates(
    horizon: int,
    last_date: pd.Timestamp,
    country: str = "US",
    planned_promos: list[dict] | None = None,
) -> dict[str, list[list[float]]]:
    """Generate covariate arrays for a future horizon window.

    Args:
        horizon: Number of future days.
        last_date: Last date of historical data.
        country: ISO country code for holiday detection.
        planned_promos: List of {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "depth": float}.

    Returns:
        Dict in same shape as build_covariates.
    """
    future_start = last_date + pd.Timedelta(days=1)
    future_range = pd.date_range(future_start, periods=horizon, freq="D")

    years = sorted(set(ts.year for ts in future_range))
    country_hols = _get_country_holidays(country, years)

    # Deterministic covariates
    day_of_week = [d.dayofweek / 6.0 for d in future_range]
    is_weekend = [1.0 if d.dayofweek >= 5 else 0.0 for d in future_range]
    month_vals = [(d.month - 1) / 11.0 for d in future_range]
    is_holiday = [1.0 if d.date() in country_hols else 0.0 for d in future_range]
    holiday_proximity = _compute_holiday_proximity(future_range, country_hols)

    # Promo covariates
    has_discount = [0.0] * horizon
    discount_depth = [0.0] * horizon

    if planned_promos:
        for promo in planned_promos:
            promo_start = pd.Timestamp(promo["start"]).date()
            promo_end = pd.Timestamp(promo["end"]).date()
            depth = promo.get("depth", 0.0)
            for i, ts in enumerate(future_range):
                if promo_start <= ts.date() <= promo_end:
                    has_discount[i] = 1.0
                    discount_depth[i] = depth

    return {
        "day_of_week": [day_of_week],
        "is_weekend": [is_weekend],
        "month": [month_vals],
        "is_holiday": [is_holiday],
        "holiday_proximity": [holiday_proximity],
        "has_discount": [has_discount],
        "discount_depth": [discount_depth],
    }


def build_aligned_covariates(
    context_dates: pd.DatetimeIndex,
    horizon: int,
    orders: list[dict],
    country: str = "US",
    custom_events: list[dict] | None = None,
    planned_promos: list[dict] | None = None,
) -> dict[str, list[list[float]]]:
    """Build a single aligned covariate dict spanning context + future horizon.

    This is the shape required by TimesFM's forecast_with_covariates():
    each array has length = len(context_dates) + horizon.

    Args:
        context_dates: DatetimeIndex for historical context period.
        horizon: Number of future days to forecast.
        orders: Normalized order dicts for the context period.
        country: ISO country code for holiday detection.
        custom_events: Optional custom event dicts.
        planned_promos: Optional planned promotions for future period.

    Returns:
        Dict with each covariate spanning context+horizon dates.
    """
    # Build full date range: context + horizon
    last_context_date = context_dates[-1]
    future_start = last_context_date + pd.Timedelta(days=1)
    future_range = pd.date_range(future_start, periods=horizon, freq="D")
    full_range = context_dates.append(future_range)

    # Build covariates for the full range (discount covariates use orders)
    result = build_covariates(full_range, orders, country=country, custom_events=custom_events)

    # Override discount covariates in the future portion with planned promos
    if planned_promos:
        future_covs = build_future_covariates(
            horizon=horizon,
            last_date=last_context_date,
            country=country,
            planned_promos=planned_promos,
        )
        context_len = len(context_dates)
        for key in ("has_discount", "discount_depth"):
            result[key][0][context_len:] = future_covs[key][0]

    return result
