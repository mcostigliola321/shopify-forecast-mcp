"""Order normalization: consistent dict shape from paginated or bulk sources.

Both fetch paths produce raw order dicts with different structures (paginated
has refundLineItems detail, bulk has only order-level currentSubtotalPriceSet).
This module produces a unified NormalizedOrder dict that downstream code can
consume without knowing which path was used.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def strip_gid(gid: str) -> str:
    """Extract numeric ID from Shopify GID string.

    ``gid://shopify/Order/1234`` -> ``"1234"``
    Plain ``"1234"`` passes through unchanged.
    """
    if "/" in gid:
        return gid.split("/")[-1]
    return gid


def utc_to_local_date(created_at: str, tz_name: str) -> str:
    """Convert UTC ISO-8601 timestamp to local date string (YYYY-MM-DD).

    Uses :class:`zoneinfo.ZoneInfo` for correct DST handling.
    """
    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    local_dt = dt.astimezone(ZoneInfo(tz_name))
    return local_dt.strftime("%Y-%m-%d")


def _safe_float(value: str | None, default: float = 0.0) -> float:
    """Parse a string to float, returning default on failure (T-02-11)."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        logger.warning("Malformed monetary amount: %r, defaulting to %s", value, default)
        return default


def _build_refund_map(order_node: dict) -> dict[str, dict]:
    """Build a map of lineItem GID -> {quantity, amount} from paginated refunds.

    Accumulates if the same line item is refunded multiple times.
    """
    refund_map: dict[str, dict] = {}

    for refund in order_node.get("refunds", []):
        refund_line_items = refund.get("refundLineItems", {})
        edges = refund_line_items.get("edges", [])
        for edge in edges:
            node = edge["node"]
            li_id = node["lineItem"]["id"]
            qty = node.get("quantity", 0)
            amount = _safe_float(
                node.get("subtotalSet", {}).get("shopMoney", {}).get("amount")
            )

            if li_id in refund_map:
                refund_map[li_id]["quantity"] += qty
                refund_map[li_id]["amount"] += amount
            else:
                refund_map[li_id] = {"quantity": qty, "amount": amount}

    return refund_map


def normalize_line_item(
    li_node: dict,
    refund_map: dict[str, dict] | None = None,
) -> dict:
    """Normalize a single line item from either paginated or bulk source.

    Args:
        li_node: Raw line item dict from GraphQL.
        refund_map: For paginated source, map of lineItem GID -> refund info.
            None for bulk source (uses currentQuantity directly).
    """
    li_id = li_node["id"]
    quantity = li_node.get("quantity", 0)
    current_quantity = li_node.get("currentQuantity", quantity)
    unit_price = _safe_float(
        li_node.get("originalUnitPriceSet", {}).get("shopMoney", {}).get("amount")
    )
    gross_revenue = quantity * unit_price

    # Handle null product/variant (deleted products - T-02-11)
    product = li_node.get("product") or {}
    variant = li_node.get("variant") or {}

    product_id_raw = product.get("id", "")
    variant_id_raw = variant.get("id", "")

    if refund_map is not None:
        # Paginated source: use refund_map for detailed refund info
        refund_info = refund_map.get(li_id, {"quantity": 0, "amount": 0.0})
        refund_quantity = refund_info["quantity"]
        refund_amount = refund_info["amount"]
        net_quantity = quantity - refund_quantity
        net_revenue = gross_revenue - refund_amount
    else:
        # Bulk source: use currentQuantity directly (already refund-adjusted)
        net_quantity = current_quantity
        refund_quantity = quantity - current_quantity
        refund_amount = refund_quantity * unit_price  # approximate
        net_revenue = current_quantity * unit_price

    return {
        "id": strip_gid(li_id),
        "title": li_node.get("title", ""),
        "quantity": quantity,
        "current_quantity": current_quantity,
        "unit_price": unit_price,
        "gross_revenue": gross_revenue,
        "refund_quantity": refund_quantity,
        "refund_amount": refund_amount,
        "net_quantity": net_quantity,
        "net_revenue": net_revenue,
        "product_id": strip_gid(product_id_raw) or "unknown",
        "product_title": product.get("title") or "Unknown Product",
        "variant_id": strip_gid(variant_id_raw) or "unknown",
        "sku": variant.get("sku") or "",
        "variant_title": variant.get("title") or "",
    }


def normalize_order(
    order_node: dict,
    tz_name: str,
    *,
    source: str = "paginated",
) -> dict:
    """Normalize a raw order dict into a consistent shape.

    Args:
        order_node: Raw order dict from GraphQL (paginated) or bulk JSONL.
        tz_name: IANA timezone name for local date bucketing.
        source: ``"paginated"`` or ``"bulk"`` -- determines refund handling.
    """
    # Build refund map for paginated source
    refund_map: dict[str, dict] | None = None
    if source == "paginated" and "refunds" in order_node:
        refund_map = _build_refund_map(order_node)

    # Normalize line items
    line_items: list[dict] = []
    if source == "paginated":
        li_edges = order_node.get("lineItems", {}).get("edges", [])
        for edge in li_edges:
            line_items.append(normalize_line_item(edge["node"], refund_map=refund_map))
    else:
        # Bulk: line_items already flattened by parse_bulk_jsonl
        for li in order_node.get("line_items", []):
            line_items.append(normalize_line_item(li, refund_map=None))

    # Extract customer_id for cohort analysis (R6.4)
    customer = order_node.get("customer") or {}
    raw_customer_id = customer.get("id", "")
    customer_id = strip_gid(raw_customer_id) if raw_customer_id else "unknown"

    return {
        "id": strip_gid(order_node["id"]),
        "created_at": order_node["createdAt"],
        "local_date": utc_to_local_date(order_node["createdAt"], tz_name),
        "financial_status": order_node.get("displayFinancialStatus", "UNKNOWN"),
        "customer_id": customer_id,
        "subtotal": _safe_float(
            order_node.get("subtotalPriceSet", {}).get("shopMoney", {}).get("amount")
        ),
        "current_subtotal": _safe_float(
            order_node.get("currentSubtotalPriceSet", {}).get("shopMoney", {}).get("amount")
        ),
        "total_discounts": _safe_float(
            order_node.get("totalDiscountsSet", {}).get("shopMoney", {}).get("amount")
        ),
        "total_refunded": _safe_float(
            order_node.get("totalRefundedSet", {}).get("shopMoney", {}).get("amount")
        ),
        "net_payment": _safe_float(
            order_node.get("netPaymentSet", {}).get("shopMoney", {}).get("amount")
        ),
        "currency": order_node.get("subtotalPriceSet", {}).get("shopMoney", {}).get(
            "currencyCode", "USD"
        ),
        "discount_codes": order_node.get("discountCodes", []),
        "tags": order_node.get("tags", []),
        "source_name": order_node.get("sourceName", ""),
        "test": order_node.get("test", False),
        "cancelled_at": order_node.get("cancelledAt"),
        "line_items": line_items,
    }


def filter_orders(orders: list[dict]) -> list[dict]:
    """Exclude test orders and cancelled orders.

    Operates on normalized order dicts (post-normalize_order).
    """
    return [
        o for o in orders
        if not o.get("test", False) and o.get("cancelled_at") is None
    ]
