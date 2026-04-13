"""CLI entry point for shopify-forecast. Real implementation in Phase 4."""
from __future__ import annotations

import sys


def main() -> int:
    """Sync wrapper. Phase 4 will wire asyncio.run() around real subcommands."""
    print("shopify-forecast: not implemented (Phase 4)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
