"""Bulk operations support for Shopify GraphQL API.

Handles the full lifecycle: start mutation -> poll -> download JSONL ->
reconstruct Order->LineItem trees using ``__parentId``.

CRITICAL: The bulk inner query does NOT include ``refundLineItems``.
Shopify rejects connection-inside-list nesting in bulk operations.
Instead we use ``currentSubtotalPriceSet`` and ``LineItem.currentQuantity``
which are already refund-adjusted.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from shopify_forecast_mcp.core.shopify_client import ShopifyClient

from shopify_forecast_mcp.core.exceptions import BulkOperationError
from shopify_forecast_mcp.core.shopify_client import (
    BULK_ORDERS_INNER_QUERY,
    BULK_RUN_MUTATION,
    BULK_STATUS_QUERY,
)

logger = logging.getLogger(__name__)

# Maximum polling attempts (~1 hour at 2s average interval).
# Mitigates T-02-08 (infinite polling DoS).
_MAX_POLL_ATTEMPTS: int = 1800

# Backoff parameters for polling.
_INITIAL_BACKOFF_S: float = 2.0
_BACKOFF_FACTOR: float = 1.5
_MAX_BACKOFF_S: float = 30.0


# ---------------------------------------------------------------------------
# JSONL parsing
# ---------------------------------------------------------------------------


def parse_bulk_jsonl(lines: Iterable[str]) -> list[dict]:
    """Reconstruct nested order trees from flat JSONL with ``__parentId``.

    Objects without ``__parentId`` are treated as orders (top-level).
    Objects with ``__parentId`` are children (line items) attached to
    their parent order.

    Returns a list of order dicts, each with a ``line_items`` key
    containing its child LineItem dicts.

    Malformed lines are logged and skipped (mitigates T-02-07).
    Orphan children (``__parentId`` not matching any order) are logged
    as warnings and discarded.
    """
    orders: dict[str, dict] = {}
    children: defaultdict[str, list[dict]] = defaultdict(list)

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            logger.warning("Skipping malformed JSONL line: %s", stripped[:120])
            continue

        parent_id = obj.pop("__parentId", None)

        if parent_id is None:
            # Top-level object = Order
            obj["line_items"] = []
            orders[obj["id"]] = obj
        else:
            # Child object = LineItem
            children[parent_id].append(obj)

    # Attach children to parents
    for parent_id, kids in children.items():
        if parent_id in orders:
            orders[parent_id]["line_items"].extend(kids)
        else:
            logger.warning(
                "Orphan children for missing parent %s (%d items)",
                parent_id,
                len(kids),
            )

    return list(orders.values())


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------


async def _poll_bulk_operation(
    client: ShopifyClient,
    operation_id: str,
) -> dict:
    """Poll a bulk operation until it reaches a terminal state.

    Returns the operation dict on COMPLETED.

    Raises:
        BulkOperationError: On FAILED, CANCELED, or EXPIRED status.
    """
    backoff = _INITIAL_BACKOFF_S

    for attempt in range(_MAX_POLL_ATTEMPTS):
        data = await client._post_graphql(
            BULK_STATUS_QUERY, {"id": operation_id}
        )
        op = data["data"]["bulkOperation"]
        status = op["status"]

        logger.info(
            "Bulk op %s: %s (%s objects)",
            operation_id,
            status,
            op.get("objectCount", "?"),
        )

        if status == "COMPLETED":
            return op

        if status in ("FAILED", "CANCELED", "EXPIRED"):
            raise BulkOperationError(
                operation_id, status, op.get("errorCode")
            )

        # CREATED or RUNNING -- wait with exponential backoff
        await asyncio.sleep(backoff)
        backoff = min(backoff * _BACKOFF_FACTOR, _MAX_BACKOFF_S)

    # Safety net: should never reach here in practice
    raise BulkOperationError(
        operation_id, "TIMEOUT", "Exceeded max poll attempts"
    )


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


async def _download_bulk_result(
    client: ShopifyClient,
    url: str,
) -> list[dict]:
    """Download JSONL from the bulk operation result URL and parse it.

    Uses the client's underlying httpx client for the HTTP GET.
    """
    resp = await client._client.get(url)
    resp.raise_for_status()

    lines = resp.text.strip().splitlines()
    return parse_bulk_jsonl(lines)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def fetch_orders_bulk(
    client: ShopifyClient,
    start_date: str,
    end_date: str,
    financial_status: str = "paid",
) -> list[dict]:
    """Fetch orders via bulk operation: start -> poll -> download -> parse.

    Args:
        client: Authenticated ShopifyClient instance.
        start_date: ISO date string for query filter (inclusive).
        end_date: ISO date string for query filter (inclusive).
        financial_status: Order financial status filter (default: paid).

    Returns:
        List of order dicts with ``line_items`` attached.

    Raises:
        BulkOperationError: If the mutation returns userErrors or the
            operation reaches a terminal failure state.
    """
    # Build the query filter and inject into the inner query template
    query_filter = (
        f"created_at:>='{start_date}' "
        f"created_at:<='{end_date}' "
        f"financial_status:{financial_status}"
    )
    inner_query = BULK_ORDERS_INNER_QUERY.replace("$QUERY_FILTER", query_filter)

    # Start the bulk operation
    data = await client._post_graphql(BULK_RUN_MUTATION, {"query": inner_query})
    result = data["data"]["bulkOperationRunQuery"]

    # Check for user errors
    user_errors = result.get("userErrors", [])
    if user_errors:
        messages = "; ".join(e.get("message", str(e)) for e in user_errors)
        raise BulkOperationError("(not started)", "USER_ERROR", messages)

    operation_id = result["bulkOperation"]["id"]
    logger.info("Started bulk operation %s", operation_id)

    # Poll until complete
    op = await _poll_bulk_operation(client, operation_id)

    # Download and parse
    download_url = op["url"]
    if not download_url:
        logger.warning("Bulk operation completed but no URL returned (empty result set)")
        return []

    return await _download_bulk_result(client, download_url)
