---
phase: 01-scaffold-config
plan: 03
subsystem: config
tags: [config, pydantic-settings, secrets, env]
requires:
  - "01-scaffold-config/01"  # uv venv + project skeleton
  - "01-scaffold-config/02"  # pyproject + pytest config (pythonpath=src)
provides:
  - "shopify_forecast_mcp.config.Settings"
  - "shopify_forecast_mcp.config.get_settings"
affects:
  - "Phase 2 Shopify client (consumes shop, access_token, api_version)"
  - "Phase 3 forecaster (consumes timesfm_* and forecast_cache_ttl)"
  - "Phase 4 MCP server (consumes log_level, hf_home)"
tech_stack:
  added: [pydantic-settings, pydantic.SecretStr]
  patterns: [BaseSettings env loading, SecretStr token wrapping, factory function get_settings()]
key_files:
  created:
    - src/shopify_forecast_mcp/config.py
    - tests/__init__.py
    - tests/test_config.py
    - .env.example
  modified: []
decisions:
  - "api_version default = 2026-04 (per research correction, not PRD's 2026-01)"
  - "timesfm_device default = cpu; no mps option exposed (TimesFM 2.5 has no mps backend on Apple Silicon)"
  - "Token uses SecretStr — verified to mask in repr, str, model_dump, and model_dump_json"
  - "Tests pass _env_file=None to bypass .env file lookup so test isolation is hermetic"
metrics:
  duration: ~3 min
  tasks_completed: 2
  files_changed: 4
  tests_added: 7
  tests_passing: 7
  completed: 2026-04-13
---

# Phase 01 Plan 03: Settings module Summary

**One-liner:** Pydantic-settings `Settings` class with `SHOPIFY_FORECAST_*` env prefix, `SecretStr`-wrapped access token, and 7 unit tests covering load, validation, defaults, secret masking (incl. model_dump), factory, and case-insensitivity.

## What shipped

- **`src/shopify_forecast_mcp/config.py`** — `Settings(BaseSettings)` with:
  - Required: `shop: str`, `access_token: SecretStr`
  - Defaults: `api_version="2026-04"`, `timesfm_device="cpu"`, `timesfm_context_length=1024`, `timesfm_horizon=90`, `forecast_cache_ttl=3600`, `log_level="INFO"`, `hf_home: str | None = None`
  - `model_config`: `env_prefix="SHOPIFY_FORECAST_"`, `env_file=".env"`, `case_sensitive=False`, `extra="ignore"`
  - `get_settings()` factory
- **`tests/test_config.py`** — 7 tests, all green:
  1. `test_loads_required_vars`
  2. `test_missing_required_raises` (ValidationError names both fields)
  3. `test_defaults`
  4. `test_secret_str_hides_token`
  5. `test_model_dump_hides_token` (R7.8 — Phase 4 logging discipline)
  6. `test_get_settings_returns_instance`
  7. `test_case_insensitive`
- **`tests/__init__.py`** — pytest package marker
- **`.env.example`** — required vars uncommented, optional vars commented, no-mps note inline

## Verification

```
$ uv run pytest tests/test_config.py -x -q
.......                                                                  [100%]
7 passed in 0.13s
```

Whole-suite `uv run pytest -x -q` → 7 passed.

## Deviations from Plan

None — plan executed exactly as written. Plan called for 6 tests; the inlined test file (added in F-05 revision) included a 7th test (`test_model_dump_hides_token`) which was implemented and passes.

## Downstream contract

Any module in Phase 2/3/4 that needs config should:

```python
from shopify_forecast_mcp.config import get_settings

settings = get_settings()
# settings.shop, settings.access_token.get_secret_value(), etc.
```

Never log `settings` directly — `model_dump()` is safe (token masked) but explicit field access is preferred.

## Commits

- `f4d1e07` — feat(01-03): add Settings module with pydantic-settings
- `be07999` — chore(01-03): add .env.example documenting all config vars

## Self-Check: PASSED

- src/shopify_forecast_mcp/config.py — FOUND
- tests/test_config.py — FOUND
- tests/__init__.py — FOUND
- .env.example — FOUND
- f4d1e07 — FOUND in git log
- be07999 — FOUND in git log
- 7/7 tests passing
