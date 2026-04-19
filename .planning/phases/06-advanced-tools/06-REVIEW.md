---
phase: 06-advanced-tools
reviewed: 2026-04-18T00:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - src/shopify_forecast_mcp/core/scenarios.py
  - src/shopify_forecast_mcp/core/inventory.py
  - src/shopify_forecast_mcp/config.py
  - src/shopify_forecast_mcp/mcp/server.py
  - src/shopify_forecast_mcp/mcp/tools.py
  - src/shopify_forecast_mcp/cli.py
  - src/shopify_forecast_mcp/core/shopify_client.py
  - tests/test_scenarios.py
  - tests/test_mcp_tools_scenarios.py
  - tests/test_cli_scenarios.py
  - tests/test_inventory.py
  - tests/test_mcp_tools_demand.py
  - tests/test_multistore.py
  - tests/test_config.py
findings:
  critical: 0
  warning: 5
  info: 3
  total: 8
status: issues_found
---

# Phase 06: Code Review Report

**Reviewed:** 2026-04-18T00:00:00Z
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Phase 06 adds scenario comparison (`compare_scenarios` MCP tool and `scenarios` CLI subcommand), inventory reorder alerts, and multi-store support. The overall design is clean: Pydantic validation at the MCP boundary, graceful degradation for inventory errors, and good separation between core logic and transport layers. Test coverage is thorough for the happy paths and key edge cases.

Five warnings were found — all correctness issues that would produce crashes or silently wrong output under real inputs. No security vulnerabilities were identified. Three info items flag maintainability concerns.

## Warnings

### WR-01: Index-out-of-bounds crash when `clean_series` returns an empty series

**File:** `src/shopify_forecast_mcp/core/scenarios.py:71`
**Issue:** After `clean_series(daily)`, the code accesses `context_dates[-1]` unconditionally. If the cleaned series is empty (e.g., all-zero days that get dropped, or fewer data points than the cleaner threshold), this raises `IndexError` and the exception propagates to the MCP/CLI error handler — but only after the caller has already paid for the Shopify fetch and covariate build. The same pattern exists in `tools.py` for `forecast_revenue` (line 115) but it is already guarded by the `if not orders` check upstream. In `run_scenarios` there is no such guard.

**Fix:**
```python
daily = clean_series(daily)

if daily.empty:
    raise ValueError(
        "Insufficient data after cleaning: all days were removed as outliers."
    )

values = daily.values
context_dates = daily.index
last_date = context_dates[-1]
```

---

### WR-02: Negative `available` stock silently skips the reorder alert

**File:** `src/shopify_forecast_mcp/core/inventory.py:42-43`
**Issue:** `days_to_stockout = inv["available"] / daily_demand`. Shopify can legitimately return a negative `available` quantity when overselling is enabled. A negative `available` produces a negative `days_to_stockout`, which is always less than `lead_time_days`, so the alert fires and shows a negative "Days to Stockout" in the markdown table — a confusing and misleading value for the user. The intent is clearly to alert only when stock is genuinely running low.

**Fix:**
```python
available = inv["available"]
if available < 0:
    available = 0  # treat oversold as zero for alert purposes
days_to_stockout = available / daily_demand
```

---

### WR-03: GraphQL response accessed without error-field check in `fetch_orders_paginated`

**File:** `src/shopify_forecast_mcp/core/shopify_client.py:394-396`
**Issue:** `result["data"]["orders"]` is accessed with no guard for the `errors` key that Shopify returns when a query fails (e.g., invalid cursor, rate limit, auth error). A GraphQL error response has shape `{"errors": [...]}` with no `"data"` key, causing `KeyError: 'data'`. This is uncaught inside the pagination loop and will propagate up through `fetch_orders` as a raw `KeyError`, bypassing the cache and producing an unhelpful error message. The same pattern applies in `fetch_products`, `fetch_inventory`, and `fetch_collections`.

**Fix:** Add a small helper or inline guard:
```python
result = await self._post_graphql(PAGINATED_ORDERS_QUERY, variables)
if "errors" in result:
    raise RuntimeError(
        f"Shopify GraphQL error: {result['errors']}"
    )
data = result["data"]["orders"]
```

---

### WR-04: `discount_depth` not range-validated in CLI `_run_scenarios`

**File:** `src/shopify_forecast_mcp/cli.py:513-521`
**Issue:** The CLI validates that each scenario dict has the required keys (`name`, `promo_start`, `promo_end`, `discount_depth`), but does not validate that `discount_depth` is in `[0.0, 1.0]`. The MCP path uses `ScenarioInput` (Pydantic, `ge=0.0, le=1.0`) so it is protected. A CLI caller can pass `discount_depth: 5.0` and it silently flows through to `build_aligned_covariates`, which may produce nonsensical covariate values or a forecaster error with no actionable message.

**Fix:**
```python
for i, s in enumerate(scenario_list):
    if not isinstance(s, dict):
        print(f"Error: Scenario {i} is not a dict.", file=sys.stderr)
        return 1
    missing = required_keys - set(s.keys())
    if missing:
        print(f"Error: Scenario {i} missing keys: {missing}", file=sys.stderr)
        return 1
    depth = s.get("discount_depth")
    if not isinstance(depth, (int, float)) or not (0.0 <= depth <= 1.0):
        print(
            f"Error: Scenario {i} discount_depth must be between 0.0 and 1.0, got {depth!r}",
            file=sys.stderr,
        )
        return 1
```

---

### WR-05: Bare `except (ImportError, Exception)` silently swallows all exceptions

**File:** `src/shopify_forecast_mcp/mcp/tools.py:674`
**Issue:** The holiday-labeling block catches `(ImportError, Exception)` which is equivalent to a bare `except BaseException` (modulo `KeyboardInterrupt`/`SystemExit`) for practical purposes. Any bug inside the `try` block — including a `TypeError` or `AttributeError` from a bad API change — will be silently swallowed with a `pass`. The comment says "Covariates module not available" but the actual guard condition is import failure; runtime errors from `_get_country_holidays` (e.g., invalid country code) should not be silently ignored in the same way.

**Fix:** Be precise about what is expected to fail:
```python
try:
    from shopify_forecast_mcp.core.covariates import _get_country_holidays
    holiday_dict = _get_country_holidays("US")
    for d in actuals_series.index:
        d_date = d.date() if hasattr(d, "date") else d
        if d_date in holiday_dict:
            known_events.append(
                {"date": d_date.isoformat(), "label": holiday_dict[d_date]}
            )
except ImportError:
    pass  # Covariates module not available
except Exception:
    log.debug("Holiday labeling failed", exc_info=True)
```

---

## Info

### IN-01: File opened without explicit encoding in `_run_scenarios`

**File:** `src/shopify_forecast_mcp/cli.py:501`
**Issue:** `open(raw)` uses the platform default encoding. On Windows this can be `cp1252` instead of `UTF-8`, which will raise `UnicodeDecodeError` for scenario files containing non-ASCII characters (e.g., accented promo names).

**Fix:**
```python
with open(raw, encoding="utf-8") as f:
```

---

### IN-02: Side-effect import at module level in `server.py`

**File:** `src/shopify_forecast_mcp/mcp/server.py:128`
**Issue:** `import shopify_forecast_mcp.mcp.tools  # noqa: F401` registers tool handlers by executing module-level `@mcp.tool()` decorators as a side effect. This is a known FastMCP pattern but it creates a hidden ordering dependency: if the import is moved above the `mcp = FastMCP(...)` line by a future refactor (e.g., an auto-sort import tool), tool registration will fail silently. A comment already exists but it doesn't explain the precise risk.

**Fix:** Strengthen the comment to make the constraint explicit:
```python
# IMPORTANT: This import must come AFTER `mcp = FastMCP(...)` above.
# The tools module uses `@mcp.tool()` decorators at import time.
# Moving this import earlier will cause tools to register against a
# non-existent `mcp` object and fail silently at runtime.
import shopify_forecast_mcp.mcp.tools  # noqa: F401, E402
```

---

### IN-03: Magic number `0.5` in rounding formula for `suggested_reorder_qty`

**File:** `src/shopify_forecast_mcp/core/inventory.py:44`
**Issue:** `int(lead_time_days * daily_demand * safety_factor + 0.5)` uses `+ 0.5` to implement banker's rounding as "always round half up." This duplicates `math.ceil`'s intent but is subtly different from it (ceil would give different results for exact integers). The spec comment at line 9 says `ceil(lead_time_days * daily_demand * safety_factor)`, making `int(...+ 0.5)` inconsistent with the spec.

**Fix:** Use `math.ceil` as the spec documents:
```python
suggested_qty = math.ceil(lead_time_days * daily_demand * safety_factor)
```
Note: `math` is already imported at line 12.

---

_Reviewed: 2026-04-18T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
