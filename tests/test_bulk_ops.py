"""Tests for the bulk operations module.

Covers JSONL parsing, polling lifecycle, error handling, and the
full fetch_orders_bulk orchestration flow.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from shopify_forecast_mcp.core.bulk_ops import (
    _download_bulk_result,
    _poll_bulk_operation,
    fetch_orders_bulk,
    parse_bulk_jsonl,
)
from shopify_forecast_mcp.core.exceptions import BulkOperationError
from shopify_forecast_mcp.core.shopify_client import BULK_ORDERS_INNER_QUERY

from .conftest import SHOPIFY_GQL_URL

# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def bulk_jsonl_lines() -> list[str]:
    """Return lines from the mock bulk JSONL fixture."""
    return (FIXTURES_DIR / "mock_bulk.jsonl").read_text().strip().splitlines()


@pytest.fixture()
def bulk_responses() -> dict:
    """Return the mock bulk response variants."""
    return json.loads((FIXTURES_DIR / "mock_bulk_responses.json").read_text())


# ---------------------------------------------------------------------------
# parse_bulk_jsonl tests
# ---------------------------------------------------------------------------


class TestParseBulkJsonl:
    def test_parse_bulk_jsonl(self, bulk_jsonl_lines: list[str]) -> None:
        """Parses fixture JSONL into 4 order dicts, each with line_items list."""
        orders = parse_bulk_jsonl(bulk_jsonl_lines)
        assert len(orders) == 4

    def test_parse_bulk_jsonl_parent_child(
        self, bulk_jsonl_lines: list[str]
    ) -> None:
        """Order 1001 has 2 line items, Order 1002 has 1, Order 1003 has 1, Order 1004 has 1."""
        orders = parse_bulk_jsonl(bulk_jsonl_lines)
        # Build lookup by order GID
        by_id = {o["id"]: o for o in orders}

        assert len(by_id["gid://shopify/Order/1001"]["line_items"]) == 2
        assert len(by_id["gid://shopify/Order/1002"]["line_items"]) == 1
        assert len(by_id["gid://shopify/Order/1003"]["line_items"]) == 1
        assert len(by_id["gid://shopify/Order/1004"]["line_items"]) == 1

        # Verify __parentId was stripped from children
        for order in orders:
            for li in order["line_items"]:
                assert "__parentId" not in li

    def test_parse_bulk_jsonl_empty(self) -> None:
        """Empty input returns empty list."""
        assert parse_bulk_jsonl([]) == []
        assert parse_bulk_jsonl([""]) == []


# ---------------------------------------------------------------------------
# Polling tests
# ---------------------------------------------------------------------------


class TestPollBulkOperation:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_poll_completed(
        self, shopify_client, bulk_responses: dict
    ) -> None:
        """Polling returns operation dict when COMPLETED."""
        shopify_client._backend.post_graphql = AsyncMock(
            return_value=bulk_responses["completed"]
        )

        result = await _poll_bulk_operation(
            shopify_client, "gid://shopify/BulkOperation/999"
        )
        assert result["status"] == "COMPLETED"
        assert result["url"] is not None

    @pytest.mark.asyncio(loop_scope="function")
    async def test_poll_running_then_completed(
        self, shopify_client, bulk_responses: dict
    ) -> None:
        """RUNNING then COMPLETED -- polls twice."""
        shopify_client._backend.post_graphql = AsyncMock(
            side_effect=[
                bulk_responses["running"],
                bulk_responses["completed"],
            ]
        )

        with patch("shopify_forecast_mcp.core.bulk_ops.asyncio.sleep", new_callable=AsyncMock):
            result = await _poll_bulk_operation(
                shopify_client, "gid://shopify/BulkOperation/999"
            )

        assert result["status"] == "COMPLETED"
        assert shopify_client._backend.post_graphql.call_count == 2

    @pytest.mark.asyncio(loop_scope="function")
    async def test_poll_failed(
        self, shopify_client, bulk_responses: dict
    ) -> None:
        """FAILED status raises BulkOperationError."""
        shopify_client._backend.post_graphql = AsyncMock(
            return_value=bulk_responses["failed"]
        )

        with pytest.raises(BulkOperationError, match="FAILED"):
            await _poll_bulk_operation(
                shopify_client, "gid://shopify/BulkOperation/999"
            )


# ---------------------------------------------------------------------------
# Full lifecycle test
# ---------------------------------------------------------------------------


class TestFetchOrdersBulkLifecycle:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_fetch_orders_bulk_lifecycle(
        self, shopify_client, bulk_responses: dict, bulk_jsonl_lines: list[str]
    ) -> None:
        """Full lifecycle: start -> poll -> download -> parse -> returns orders."""
        jsonl_content = "\n".join(bulk_jsonl_lines)

        # Mock backend: mutation for start, query for poll, download for JSONL
        shopify_client._backend.post_graphql_mutation = AsyncMock(
            return_value=bulk_responses["start"]
        )
        shopify_client._backend.post_graphql = AsyncMock(
            return_value=bulk_responses["completed"]
        )

        download_url = bulk_responses["completed"]["data"]["bulkOperation"]["url"]
        shopify_client._backend.download_url = AsyncMock(
            return_value=jsonl_content.encode()
        )

        orders = await fetch_orders_bulk(
            shopify_client, "2025-06-01", "2025-06-30"
        )

        assert len(orders) == 4
        # Verify line items are attached
        by_id = {o["id"]: o for o in orders}
        assert len(by_id["gid://shopify/Order/1001"]["line_items"]) == 2


# ---------------------------------------------------------------------------
# Query safety test
# ---------------------------------------------------------------------------


class TestBulkQuerySafety:
    def test_bulk_query_no_refund_line_items(self) -> None:
        """BULK_ORDERS_INNER_QUERY does NOT contain refundLineItems."""
        assert "refundLineItems" not in BULK_ORDERS_INNER_QUERY
