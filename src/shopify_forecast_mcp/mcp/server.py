"""MCP server entry point for shopify-forecast-mcp. Real FastMCP server in Phase 4."""
from __future__ import annotations

import sys


def main() -> int:
    """Sync wrapper. Phase 4 will wire asyncio.run() around a FastMCP instance.

    IMPORTANT: Per R7.8, all logging MUST go to stderr — stdio transport uses
    stdout for JSON-RPC framing. Do not add print() to stdout anywhere here.
    """
    print("shopify-forecast-mcp: not implemented (Phase 4)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
