# Phase 4: MCP Server Skeleton + CLI (MVP)

**Goal:** A working `shopify-forecast-mcp` server in Claude Desktop that answers `forecast_revenue` and `forecast_demand` with real Shopify data, plus a matching CLI.

**Requirements:** R7.1-R7.11, R8.1, R8.2, R9.1-R9.4, R10.4

## Plans

| Plan | Wave | Objective | Tasks | Key Files | Depends On |
|------|------|-----------|-------|-----------|------------|
| 04-01 | 1 | FastMCP server skeleton | 2 | `mcp/server.py`, `tests/test_mcp_server.py` | -- |
| 04-02 | 2 | `forecast_revenue` tool | 2 | `mcp/tools.py`, `tests/test_mcp_tools_revenue.py` | 04-01 |
| 04-03 | 3 | `forecast_demand` tool | 2 | `mcp/tools.py`, `tests/test_mcp_tools_demand.py` | 04-02 |
| 04-04 | 4 | CLI + end-to-end tests | 2 | `cli.py`, `tests/test_cli.py` | 04-03 |

## Wave Structure

```
Wave 1: 04-01 (server skeleton)
    |
Wave 2: 04-02 (forecast_revenue)
    |
Wave 3: 04-03 (forecast_demand -- appends to tools.py)
    |
Wave 4: 04-04 (CLI + tests)
```

All waves are sequential. Plans 04-02 and 04-03 both modify `mcp/tools.py` so they cannot run in parallel.

## File Ownership

| File | Plan |
|------|------|
| `src/shopify_forecast_mcp/mcp/server.py` | 04-01 |
| `src/shopify_forecast_mcp/mcp/__init__.py` | 04-01 |
| `src/shopify_forecast_mcp/mcp/tools.py` | 04-02 (create), 04-03 (extend) |
| `src/shopify_forecast_mcp/cli.py` | 04-04 |
| `tests/test_mcp_server.py` | 04-01 |
| `tests/test_mcp_tools_revenue.py` | 04-02 |
| `tests/test_mcp_tools_demand.py` | 04-03 |
| `tests/test_cli.py` | 04-04 |

## Success Criteria (Phase-level)

- `uvx shopify-forecast-mcp` launches; both tools appear in tool list
- Stdio transport emits nothing to stdout except JSON-RPC framing
- `shopify-forecast revenue --horizon 30` prints markdown table
- `shopify-forecast demand --group-by sku --group-value all` prints ranked table
- `pytest` green on all new test files
