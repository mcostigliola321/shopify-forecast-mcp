"""Tests for OrderCache: file-based caching with TTL expiry."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from shopify_forecast_mcp.core.cache import OrderCache


class TestOrderCache:
    def test_cache_miss(self, tmp_path: Path):
        """get() returns None for uncached key."""
        cache = OrderCache(cache_dir=tmp_path, ttl=3600)
        result = cache.get("test-store", "2025-01-01", "2025-01-31")
        assert result is None

    def test_cache_hit(self, tmp_path: Path):
        """put() then get() returns data."""
        cache = OrderCache(cache_dir=tmp_path, ttl=3600)
        orders = [{"id": "1", "total": 100.0}, {"id": "2", "total": 200.0}]
        cache.put("test-store", "2025-01-01", "2025-01-31", orders)
        result = cache.get("test-store", "2025-01-01", "2025-01-31")
        assert result == orders

    def test_cache_expiry(self, tmp_path: Path):
        """put() then get() after TTL returns None."""
        cache = OrderCache(cache_dir=tmp_path, ttl=1)  # 1 second TTL
        orders = [{"id": "1"}]
        cache.put("test-store", "2025-01-01", "2025-01-31", orders)

        # Set file mtime to 2 seconds in the past
        cache_files = list(tmp_path.glob("*.json"))
        assert len(cache_files) == 1
        old_time = time.time() - 2
        os.utime(cache_files[0], (old_time, old_time))

        result = cache.get("test-store", "2025-01-01", "2025-01-31")
        assert result is None

    def test_cache_invalidate(self, tmp_path: Path):
        """invalidate() clears cached files."""
        cache = OrderCache(cache_dir=tmp_path, ttl=3600)
        cache.put("test-store", "2025-01-01", "2025-01-31", [{"id": "1"}])
        cache.put("test-store", "2025-02-01", "2025-02-28", [{"id": "2"}])

        # Invalidate for this shop
        cache.invalidate("test-store")

        assert cache.get("test-store", "2025-01-01", "2025-01-31") is None
        assert cache.get("test-store", "2025-02-01", "2025-02-28") is None

    def test_cache_invalidate_all(self, tmp_path: Path):
        """invalidate() with no shop clears all cached files."""
        cache = OrderCache(cache_dir=tmp_path, ttl=3600)
        cache.put("store-a", "2025-01-01", "2025-01-31", [{"id": "1"}])
        cache.put("store-b", "2025-01-01", "2025-01-31", [{"id": "2"}])

        cache.invalidate()
        assert list(tmp_path.glob("*.json")) == []

    def test_cache_different_financial_status(self, tmp_path: Path):
        """Different financial_status produces different cache keys."""
        cache = OrderCache(cache_dir=tmp_path, ttl=3600)
        cache.put("test-store", "2025-01-01", "2025-01-31", [{"id": "paid"}], financial_status="paid")
        cache.put("test-store", "2025-01-01", "2025-01-31", [{"id": "refunded"}], financial_status="refunded")

        result_paid = cache.get("test-store", "2025-01-01", "2025-01-31", financial_status="paid")
        result_refunded = cache.get("test-store", "2025-01-01", "2025-01-31", financial_status="refunded")

        assert result_paid == [{"id": "paid"}]
        assert result_refunded == [{"id": "refunded"}]

    def test_cache_dir_created(self, tmp_path: Path):
        """Cache dir is created if it doesn't exist."""
        cache_dir = tmp_path / "subdir" / "cache"
        cache = OrderCache(cache_dir=cache_dir, ttl=3600)
        assert cache_dir.exists()
