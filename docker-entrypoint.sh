#!/usr/bin/env bash
# docker-entrypoint.sh — dispatches between MCP server and CLI verbs.
# Implements D-10 of Phase 7 CONTEXT.md.
#
# Usage (inside container):
#   docker run <image>                          → starts MCP server over stdio
#   docker run <image> mcp                      → starts MCP server (explicit)
#   docker run <image> revenue --horizon 30     → runs `shopify-forecast revenue --horizon 30`
#   docker run <image> --help                   → CLI help
#
# Signal handling: `exec` replaces this shell process with the Python
# process, so SIGTERM from `docker stop` reaches Python at PID 1 directly
# (Pitfall 8 in RESEARCH.md).

set -euo pipefail

case "${1:-}" in
  "" | mcp)
    # No arg or explicit 'mcp' → start MCP server over stdio.
    if [ "${1:-}" = "mcp" ]; then
      shift
    fi
    exec shopify-forecast-mcp "$@"
    ;;
  revenue | demand | promo | compare | scenarios | auth | --help | -h)
    # CLI verb → pass through to shopify-forecast.
    exec shopify-forecast "$@"
    ;;
  *)
    echo "Unknown command: $1" >&2
    echo "Usage: docker run <image> [mcp|revenue|demand|promo|compare|scenarios|auth|--help]" >&2
    exit 2
    ;;
esac
