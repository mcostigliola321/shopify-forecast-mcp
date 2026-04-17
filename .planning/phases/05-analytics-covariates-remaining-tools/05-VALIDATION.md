---
phase: 5
slug: analytics-covariates-remaining-tools
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-17
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8+ with pytest-asyncio strict mode |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_analytics.py tests/test_covariates.py -x` |
| **Full suite command** | `uv run pytest -x` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_analytics.py tests/test_covariates.py -x`
- **After every plan wave:** Run `uv run pytest -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| T-01 | 05-01 | 1 | R6.1 | unit | `uv run pytest tests/test_analytics.py::test_analyze_promotion -x` | Wave 0 | pending |
| T-02 | 05-01 | 1 | R6.2 | unit | `uv run pytest tests/test_analytics.py::test_detect_anomalies -x` | Wave 0 | pending |
| T-03 | 05-01 | 1 | R6.3 | unit | `uv run pytest tests/test_analytics.py::test_compare_periods -x` | Wave 0 | pending |
| T-04 | 05-01 | 1 | R6.4 | unit | `uv run pytest tests/test_analytics.py::test_cohort_retention -x` | Wave 0 | pending |
| T-05 | 05-02 | 1 | R5.1 | unit | `uv run pytest tests/test_covariates.py::test_build_covariates -x` | Wave 0 | pending |
| T-06 | 05-02 | 1 | R5.2 | unit | `uv run pytest tests/test_covariates.py::test_builtin_covariates -x` | Wave 0 | pending |
| T-07 | 05-02 | 1 | R5.3 | unit | `uv run pytest tests/test_covariates.py::test_custom_events -x` | Wave 0 | pending |
| T-08 | 05-02 | 1 | R5.4 | unit | `uv run pytest tests/test_covariates.py::test_future_covariates -x` | Wave 0 | pending |
| T-09 | 05-03 | 2 | R5.5 | integration | `uv run pytest tests/test_covariates.py::test_xreg_integration -x` | Wave 0 | pending |
| T-10 | 05-02 | 1 | R5.6 | unit | `uv run pytest tests/test_covariates.py::test_feature_flag -x` | Wave 0 | pending |
| T-11 | 05-04 | 3 | R8.3 | integration | `uv run pytest tests/test_mcp_tools_analytics.py::test_analyze_promotion_tool -x` | Wave 0 | pending |
| T-12 | 05-04 | 3 | R8.4 | integration | `uv run pytest tests/test_mcp_tools_analytics.py::test_detect_anomalies_tool -x` | Wave 0 | pending |
| T-13 | 05-04 | 3 | R8.5 | integration | `uv run pytest tests/test_mcp_tools_analytics.py::test_compare_periods_tool -x` | Wave 0 | pending |
| T-14 | 05-04 | 3 | R8.7 | integration | `uv run pytest tests/test_mcp_tools_analytics.py::test_get_seasonality_tool -x` | Wave 0 | pending |
| T-15 | 05-04 | 3 | R9.2 | unit | `uv run pytest tests/test_cli.py::test_promo_subcommand tests/test_cli.py::test_compare_subcommand -x` | Wave 0 | pending |

---

## Wave 0 Gaps

- [ ] `tests/test_analytics.py` — covers R6.1, R6.2, R6.3, R6.4
- [ ] `tests/test_covariates.py` — covers R5.1–R5.6
- [ ] `tests/test_mcp_tools_analytics.py` — covers R8.3, R8.4, R8.5, R8.7
- [ ] Extended `tests/conftest.py` — fixtures with promo periods, discount codes, multi-month data for cohort testing
- [ ] `tests/fixtures/sample_orders.json` may need expansion for cohort/seasonality testing
