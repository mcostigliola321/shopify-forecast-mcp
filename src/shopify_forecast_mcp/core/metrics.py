"""Metrics infrastructure for analytics functions.

Defines SUPPORTED_METRICS, AnalyticsResult/AnalyticsSection dataclasses,
and pure aggregation functions for discount_rate and units_per_order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SUPPORTED_METRICS: tuple[str, ...] = (
    "revenue",
    "orders",
    "units",
    "aov",
    "discount_rate",
    "units_per_order",
)


@dataclass
class AnalyticsSection:
    """A single section of an analytics result with a table."""

    heading: str
    table_headers: list[str]
    table_rows: list[list[str]]


@dataclass
class AnalyticsResult:
    """Structured analytics output with markdown rendering.

    Multi-section output supporting tables, summary, and recommendations.
    """

    title: str
    sections: list[AnalyticsSection]
    summary: str
    recommendations: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_markdown(self) -> str:
        """Render the analytics result as a markdown string."""
        parts: list[str] = []

        # Title
        parts.append(f"# {self.title}")
        parts.append("")

        # Sections
        for section in self.sections:
            parts.append(f"## {section.heading}")
            parts.append("")

            # Table header
            header = "| " + " | ".join(section.table_headers) + " |"
            separator = "| " + " | ".join("---" for _ in section.table_headers) + " |"
            parts.append(header)
            parts.append(separator)

            # Table rows
            for row in section.table_rows:
                parts.append("| " + " | ".join(row) + " |")

            parts.append("")

        # Summary
        parts.append(self.summary)
        parts.append("")

        # Recommendations
        if self.recommendations:
            parts.append("**Recommendations:**")
            parts.append("")
            for rec in self.recommendations:
                parts.append(f"- {rec}")
            parts.append("")

        return "\n".join(parts)


def compute_discount_rate(orders: list[dict]) -> float:
    """Return the percentage of orders that used a discount code.

    Returns 0.0 for an empty list.
    """
    if not orders:
        return 0.0

    discounted = sum(1 for o in orders if len(o.get("discount_codes", [])) > 0)
    return (discounted / len(orders)) * 100


def compute_units_per_order(orders: list[dict]) -> float:
    """Return the average number of net units per order.

    Returns 0.0 for an empty list.
    """
    if not orders:
        return 0.0

    total_units = sum(
        li["net_quantity"] for o in orders for li in o.get("line_items", [])
    )
    return total_units / len(orders)


def aggregate_metrics(
    orders: list[dict],
    start_date: str,
    end_date: str,
) -> dict[str, float]:
    """Compute all 6 supported metrics for orders within a date range.

    Filters orders by local_date between start_date and end_date (inclusive).
    Returns a dict keyed by metric name.
    """
    filtered = [
        o for o in orders
        if start_date <= o["local_date"] <= end_date
    ]

    if not filtered:
        return {m: 0.0 for m in SUPPORTED_METRICS}

    revenue = sum(
        li["net_revenue"] for o in filtered for li in o.get("line_items", [])
    )
    order_count = len(filtered)
    units = sum(
        li["net_quantity"] for o in filtered for li in o.get("line_items", [])
    )
    aov = revenue / order_count if order_count > 0 else 0.0
    discount_rate = compute_discount_rate(filtered)
    units_per_order = compute_units_per_order(filtered)

    return {
        "revenue": revenue,
        "orders": float(order_count),
        "units": float(units),
        "aov": aov,
        "discount_rate": discount_rate,
        "units_per_order": units_per_order,
    }
