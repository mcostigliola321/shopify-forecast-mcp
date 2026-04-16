"""Daily time-series aggregation from normalized Shopify orders.

Converts normalized order dicts (from ``normalize.py``) into daily
``pd.Series`` grouped by metric and optional dimension, with zero-filled
gaps for clean forecaster input.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

Metric = Literal["revenue", "orders", "units", "aov"]
GroupBy = Literal["product_id", "collection_id", "sku"] | None


def _zero_fill_series(series: pd.Series, date_range: pd.DatetimeIndex) -> pd.Series:
    """Reindex a Series to the full date range, filling gaps with 0.0."""
    return series.reindex(date_range, fill_value=0.0)


def _compute_metric_series(
    daily_revenue: pd.Series,
    daily_orders: pd.Series,
    daily_units: pd.Series,
    metric: Metric,
    date_range: pd.DatetimeIndex,
) -> pd.Series:
    """Compute and zero-fill a single metric Series."""
    if metric == "revenue":
        s = daily_revenue
    elif metric == "orders":
        s = daily_orders
    elif metric == "units":
        s = daily_units
    elif metric == "aov":
        rev = _zero_fill_series(daily_revenue, date_range)
        ords = _zero_fill_series(daily_orders, date_range)
        return pd.Series(
            np.where(ords > 0, rev / ords, 0.0),
            index=date_range,
        )
    else:
        msg = f"Unknown metric: {metric!r}"
        raise ValueError(msg)

    return _zero_fill_series(s, date_range)


def _aggregate_store_level(
    orders: list[dict],
    metric: Metric,
) -> dict[str, pd.Series]:
    """Aggregate all orders at store level (group_by=None)."""
    if not orders:
        return {"store": pd.Series(dtype=float)}

    # Collect daily totals
    revenue_by_day: dict[str, float] = defaultdict(float)
    orders_by_day: dict[str, int] = defaultdict(int)
    units_by_day: dict[str, float] = defaultdict(float)

    for order in orders:
        day = order["local_date"]
        orders_by_day[day] += 1
        for li in order["line_items"]:
            revenue_by_day[day] += li["net_revenue"]
            units_by_day[day] += li["net_quantity"]

    all_days = sorted(set(revenue_by_day.keys()) | set(orders_by_day.keys()))
    date_range = pd.date_range(start=all_days[0], end=all_days[-1], freq="D")

    daily_revenue = pd.Series(revenue_by_day).rename(lambda d: pd.Timestamp(d))
    daily_orders = pd.Series(orders_by_day, dtype=float).rename(lambda d: pd.Timestamp(d))
    daily_units = pd.Series(units_by_day).rename(lambda d: pd.Timestamp(d))

    return {"store": _compute_metric_series(
        daily_revenue, daily_orders, daily_units, metric, date_range
    )}


def _aggregate_by_field(
    orders: list[dict],
    metric: Metric,
    field: str,
) -> dict[str, pd.Series]:
    """Aggregate by a line-item field (product_id or sku)."""
    if not orders:
        return {}

    # Collect per-group daily totals
    revenue: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    order_sets: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    units: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    all_days: set[str] = set()

    for order in orders:
        day = order["local_date"]
        all_days.add(day)
        for li in order["line_items"]:
            key = li[field]
            revenue[key][day] += li["net_revenue"]
            order_sets[key][day].add(order["id"])
            units[key][day] += li["net_quantity"]

    sorted_days = sorted(all_days)
    date_range = pd.date_range(start=sorted_days[0], end=sorted_days[-1], freq="D")

    result: dict[str, pd.Series] = {}
    for group_key in revenue:
        daily_rev = pd.Series(revenue[group_key]).rename(lambda d: pd.Timestamp(d))
        daily_ord = pd.Series(
            {d: float(len(ids)) for d, ids in order_sets[group_key].items()},
        ).rename(lambda d: pd.Timestamp(d))
        daily_units = pd.Series(units[group_key]).rename(lambda d: pd.Timestamp(d))

        result[group_key] = _compute_metric_series(
            daily_rev, daily_ord, daily_units, metric, date_range
        )

    return result


def _aggregate_by_collection(
    orders: list[dict],
    metric: Metric,
    product_collection_map: dict[str, list[str]],
) -> dict[str, pd.Series]:
    """Aggregate by collection_id using a product->collections map."""
    if not orders:
        return {}

    revenue: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    order_sets: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    units: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    all_days: set[str] = set()

    for order in orders:
        day = order["local_date"]
        all_days.add(day)
        for li in order["line_items"]:
            product_id = li["product_id"]
            collection_ids = product_collection_map.get(product_id)
            if collection_ids is None:
                logger.warning(
                    "Product %s not in product_collection_map, skipping",
                    product_id,
                )
                continue
            for coll_id in collection_ids:
                revenue[coll_id][day] += li["net_revenue"]
                order_sets[coll_id][day].add(order["id"])
                units[coll_id][day] += li["net_quantity"]

    if not all_days:
        return {}

    sorted_days = sorted(all_days)
    date_range = pd.date_range(start=sorted_days[0], end=sorted_days[-1], freq="D")

    result: dict[str, pd.Series] = {}
    for coll_id in revenue:
        daily_rev = pd.Series(revenue[coll_id]).rename(lambda d: pd.Timestamp(d))
        daily_ord = pd.Series(
            {d: float(len(ids)) for d, ids in order_sets[coll_id].items()},
        ).rename(lambda d: pd.Timestamp(d))
        daily_units = pd.Series(units[coll_id]).rename(lambda d: pd.Timestamp(d))

        result[coll_id] = _compute_metric_series(
            daily_rev, daily_ord, daily_units, metric, date_range
        )

    return result


def resample_series(
    series: pd.Series,
    freq: Literal["D", "W", "M"],
    metric: Metric = "revenue",
) -> pd.Series:
    """Resample a daily time series to a coarser frequency.

    Args:
        series: Daily ``pd.Series`` with ``DatetimeIndex``.
        freq: Target frequency -- ``"D"`` (passthrough), ``"W"`` (weekly),
            or ``"M"`` (monthly).
        metric: Determines aggregation method. ``"aov"`` uses mean;
            all others (``"revenue"``, ``"orders"``, ``"units"``) use sum.

    Returns:
        Resampled ``pd.Series`` with the requested frequency.
    """
    if freq == "D":
        return series.copy()

    if len(series) == 0:
        return series.copy()

    # Pandas 2.2+ requires "ME"/"W" instead of deprecated "M"
    pandas_freq = "ME" if freq == "M" else freq
    aggregator = "mean" if metric == "aov" else "sum"
    return series.resample(pandas_freq).agg(aggregator)


def clean_series(
    series: pd.Series,
    remove_outliers: bool = True,
    outlier_method: Literal["iqr", "zscore"] = "iqr",
    interpolate_gaps: bool = False,
) -> pd.Series:
    """Clean a time series by capping outliers and interpolating gaps.

    CRITICAL: This function never drops data points. TimesFM requires
    continuous series, so outliers are clipped (capped) to bound values
    rather than removed.

    Args:
        series: ``pd.Series`` with ``DatetimeIndex``.
        remove_outliers: Whether to cap outlier values.
        outlier_method: ``"iqr"`` (1.5 * IQR bounds) or ``"zscore"``
            (mean +/- 3 * std bounds).
        interpolate_gaps: If ``True``, fill NaN values via linear
            interpolation (edge NaNs filled with 0).

    Returns:
        Cleaned ``pd.Series`` with the same length as input.
    """
    original_len = len(series)
    result = series.copy()

    # Interpolate gaps first (before outlier detection)
    if interpolate_gaps:
        result = result.interpolate(method="linear")
        # Fill edge NaNs that interpolation can't reach
        result = result.fillna(0.0)

    if not remove_outliers:
        assert len(result) == original_len
        return result

    if outlier_method == "iqr":
        q1 = result.quantile(0.25)
        q3 = result.quantile(0.75)
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        result = result.clip(lower=lower, upper=upper)
    elif outlier_method == "zscore":
        mean = result.mean()
        std = result.std()
        if std == 0:
            return result
        lower = mean - 3 * std
        upper = mean + 3 * std
        result = result.clip(lower=lower, upper=upper)

    assert len(result) == original_len, (
        f"clean_series changed series length: {original_len} -> {len(result)}"
    )
    return result


def orders_to_daily_series(
    orders: list[dict],
    metric: Metric = "revenue",
    group_by: GroupBy = None,
    product_collection_map: dict[str, list[str]] | None = None,
) -> dict[str, pd.Series]:
    """Aggregate normalized orders into daily pd.Series by metric and group.

    Args:
        orders: List of normalized order dicts (from ``normalize_order()``).
        metric: Aggregation metric -- ``"revenue"``, ``"orders"``,
            ``"units"``, or ``"aov"``.
        group_by: Optional grouping dimension. ``None`` aggregates at store
            level (single key ``"store"``). ``"product_id"``, ``"sku"``, or
            ``"collection_id"`` produce one Series per unique value.
        product_collection_map: Required when ``group_by="collection_id"``.
            Maps product_id -> list of collection_ids.

    Returns:
        Dict mapping group label to a ``pd.Series`` with ``DatetimeIndex``
        (daily frequency) and zero-filled gaps.

    Raises:
        ValueError: If ``group_by="collection_id"`` and
            ``product_collection_map`` is ``None``.
    """
    if group_by is None:
        return _aggregate_store_level(orders, metric)

    if group_by == "collection_id":
        if product_collection_map is None:
            msg = "product_collection_map is required when group_by='collection_id'"
            raise ValueError(msg)
        return _aggregate_by_collection(orders, metric, product_collection_map)

    # product_id or sku
    return _aggregate_by_field(orders, metric, group_by)
