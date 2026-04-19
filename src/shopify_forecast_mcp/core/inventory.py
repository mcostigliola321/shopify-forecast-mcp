"""Inventory reorder alert logic.

Computes reorder alerts when projected days-to-stockout falls below
the configured lead time. Uses demand forecasts from the forecaster
to estimate daily consumption rates.

References:
- D-06: days_to_stockout = available / daily_demand
- D-07: suggested_qty = ceil(lead_time_days * daily_demand * safety_factor)
"""

from __future__ import annotations

import math


def compute_reorder_alerts(
    inventory: list[dict],
    forecasts: dict[str, float],  # group_key -> avg daily demand
    lead_time_days: int = 14,
    safety_factor: float = 1.2,
) -> list[dict]:
    """Compute reorder alerts for inventory items with demand forecasts.

    An alert fires when ``available / daily_demand < lead_time_days``.

    Args:
        inventory: List of inventory dicts with product_id, available, sku, etc.
        forecasts: Map of group_key (product_id) to average daily demand.
        lead_time_days: Supplier lead time in days (default: 14).
        safety_factor: Buffer multiplier for reorder qty (default: 1.2 = 20%).

    Returns:
        Sorted list of alert dicts (by days_to_stockout ascending).
    """
    alerts: list[dict] = []
    for inv in inventory:
        key = inv["product_id"]
        daily_demand = forecasts.get(key, 0.0)
        if daily_demand <= 0:
            continue
        days_to_stockout = inv["available"] / daily_demand
        if days_to_stockout < lead_time_days:
            suggested_qty = int(lead_time_days * daily_demand * safety_factor + 0.5)
            alerts.append({
                "product_id": inv["product_id"],
                "product_title": inv.get("product_title", ""),
                "sku": inv["sku"],
                "current_stock": inv["available"],
                "daily_demand": round(daily_demand, 1),
                "days_to_stockout": round(days_to_stockout, 1),
                "suggested_reorder_qty": suggested_qty,
                "location": inv.get("location_name", ""),
            })
    return sorted(alerts, key=lambda a: a["days_to_stockout"])


def format_reorder_alerts(alerts: list[dict]) -> str:
    """Format reorder alerts as a markdown table.

    Returns empty string if no alerts.
    """
    if not alerts:
        return ""
    lines = [
        "",
        "## Reorder Alerts",
        "",
        "| Product | SKU | Stock | Daily Demand | Days to Stockout | Reorder Qty | Location |",
        "|---|---|---|---|---|---|---|",
    ]
    for a in alerts:
        lines.append(
            f"| {a['product_title']} | {a['sku']} | {a['current_stock']} "
            f"| {a['daily_demand']} | {a['days_to_stockout']} "
            f"| {a['suggested_reorder_qty']} | {a['location']} |"
        )
    return "\n".join(lines)
