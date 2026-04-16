"""Daily time-series aggregation from normalized Shopify orders.

Converts normalized order dicts (from ``normalize.py``) into daily
``pd.Series`` grouped by metric and optional dimension, with zero-filled
gaps for clean forecaster input.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

Metric = Literal["revenue", "orders", "units", "aov"]
GroupBy = Literal["product_id", "collection_id", "sku"] | None


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
        NotImplementedError: Stub -- implementation in Task 2.
        ValueError: If ``group_by="collection_id"`` and
            ``product_collection_map`` is ``None``.
    """
    raise NotImplementedError("orders_to_daily_series not yet implemented")
