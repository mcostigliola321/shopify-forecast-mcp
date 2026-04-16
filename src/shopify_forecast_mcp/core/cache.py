"""File-based order cache with TTL expiry.

Stores normalized order lists as JSON files keyed by
(shop, date_range, financial_status). Uses atomic write
(tmp + rename) to avoid partial reads.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "shopify-forecast"


class OrderCache:
    """File-based order cache with TTL expiry.

    Args:
        cache_dir: Directory for cache files. Defaults to ``~/.cache/shopify-forecast/``.
        ttl: Time-to-live in seconds. Defaults to 3600 (1 hour).
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        ttl: int = 3600,
    ) -> None:
        self._cache_dir = Path(cache_dir) if cache_dir else _DEFAULT_CACHE_DIR
        self._ttl = ttl
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(
        self,
        shop: str,
        start_date: str,
        end_date: str,
        financial_status: str = "paid",
    ) -> str:
        """Generate a cache key from query parameters.

        Returns a SHA-256 hash truncated to 16 hex chars.
        """
        raw = f"{shop}:{start_date}:{end_date}:{financial_status}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _cache_path(self, key: str) -> Path:
        """Return the filesystem path for a cache key."""
        return self._cache_dir / f"{key}.json"

    def get(
        self,
        shop: str,
        start_date: str,
        end_date: str,
        financial_status: str = "paid",
    ) -> list[dict] | None:
        """Return cached orders if fresh, None if expired or missing."""
        key = self._cache_key(shop, start_date, end_date, financial_status)
        path = self._cache_path(key)

        if not path.exists():
            return None

        # Check TTL via file modification time
        mtime = path.stat().st_mtime
        if time.time() - mtime > self._ttl:
            logger.debug("Cache expired for key %s", key)
            return None

        try:
            data = json.loads(path.read_text())
            logger.debug("Cache hit for key %s (%d orders)", key, len(data))
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Cache read error for key %s: %s", key, exc)
            return None

    def put(
        self,
        shop: str,
        start_date: str,
        end_date: str,
        orders: list[dict],
        financial_status: str = "paid",
    ) -> None:
        """Write orders to cache with atomic write (tmp + rename)."""
        key = self._cache_key(shop, start_date, end_date, financial_status)
        path = self._cache_path(key)

        # Atomic write: write to temp file then rename
        fd, tmp_path = tempfile.mkstemp(
            dir=self._cache_dir, suffix=".tmp", prefix="cache_"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(orders, f)
            os.replace(tmp_path, path)
            logger.debug("Cached %d orders for key %s", len(orders), key)
        except OSError:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def invalidate(self, shop: str | None = None) -> None:
        """Delete cached files.

        Args:
            shop: If provided, only delete cache files. Since keys are
                hashed, we delete all ``.json`` files in the cache dir
                (shop-level isolation would require a prefix scheme).
                If None, delete all cache files.
        """
        for path in self._cache_dir.glob("*.json"):
            try:
                path.unlink()
            except OSError as exc:
                logger.warning("Failed to delete cache file %s: %s", path, exc)
