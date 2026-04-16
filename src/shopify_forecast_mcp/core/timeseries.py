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
