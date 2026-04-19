# Python Packaging & Distribution Research

**Confidence:** HIGH on uv/pyproject/MCP basics; MEDIUM on Docker+TimesFM specifics.

## TL;DR

- **`uv`** as single toolchain: `uv init --package`, `uv add`, `uv run`, `uv build`, `uv publish`. Default `hatchling` build backend, `src/` layout, lockfile.
- Two console scripts: `shopify-forecast` (CLI) + `shopify-forecast-mcp` (MCP server). Users launch via `uvx shopify-forecast-mcp` from Claude Desktop config.
- **PyTorch:** declare via `[tool.uv.sources]` + explicit `[[tool.uv.index]]` for CPU wheels; GPU as opt-in extra.
- **Skip npx wrapper.** `uvx` is the 2026 idiomatic equivalent. Ship PyPI + Docker.
- **Docker:** multistage with `python:3.12-slim` + `uv` from `ghcr.io/astral-sh/uv`, CPU-only torch, model baked in middle layer (~2.0–2.5 GB final).
- **Pytest:** strict asyncio mode, fixtures under `tests/fixtures/`, all config in `pyproject.toml`.
- **Config:** `pydantic-settings` v2 with `env_prefix="SHOPIFY_FORECAST_"`, `SecretStr` for token.
- **License:** PEP 639 SPDX `license = "MIT"` + `license-files = ["LICENSE"]`.

## Critical PRD corrections

| PRD says | Reality |
|---|---|
| `src/core/` and `src/mcp/` as top-level | **Wrong** — can't have two top-level namespaces in one distribution, and `src/mcp/` collides with the installed `mcp` SDK. Rename to `src/shopify_forecast_mcp/{core,mcp,cli.py}`. |
| Optional npx wrapper | Skip — `uvx` is the equivalent and works natively in Claude Desktop configs. |
| TimesFM via `pip install timesfm` (implicit) | TimesFM 2.5 not on PyPI. Use git dependency with pinned commit SHA. |

## `pyproject.toml` skeleton

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "shopify-forecast-mcp"
version = "0.1.0"
description = "MCP server connecting Google TimesFM 2.5 to Shopify Admin GraphQL for forecasting, demand planning, and anomaly detection."
readme = "README.md"
requires-python = ">=3.11,<3.12"   # pinned for upstream timesfm constraint
license = "MIT"
license-files = ["LICENSE"]
authors = [{ name = "Mark", email = "mark@omnialta.com" }]
keywords = ["mcp", "shopify", "forecasting", "timesfm", "timeseries", "ecommerce"]
classifiers = [
  "Development Status :: 3 - Alpha",
  "Intended Audience :: Developers",
  "License :: OSI Approved :: MIT License",
  "Programming Language :: Python :: 3.11",
  "Topic :: Scientific/Engineering",
  "Topic :: Office/Business :: Financial",
]
dependencies = [
  "mcp>=1.27,<2.0",
  "httpx>=0.27",
  "pandas>=2.2",
  "numpy>=1.26,<3",
  "pydantic>=2.7",
  "pydantic-settings>=2.3",
  "holidays>=0.50",
  "python-dateutil>=2.9",
  "torch>=2.4",
  "timesfm @ git+https://github.com/google-research/timesfm.git@<PIN_COMMIT_SHA>",
]

[project.optional-dependencies]
gpu = []
dev = ["pytest>=8", "pytest-asyncio>=0.24", "respx>=0.22", "ruff>=0.6", "mypy>=1.11"]

[project.scripts]
shopify-forecast      = "shopify_forecast_mcp.cli:main"
shopify-forecast-mcp  = "shopify_forecast_mcp.mcp.server:main"

[project.urls]
Homepage   = "https://github.com/mcostigliola321/shopify-forecast-mcp"
Repository = "https://github.com/mcostigliola321/shopify-forecast-mcp"
Issues     = "https://github.com/mcostigliola321/shopify-forecast-mcp/issues"

[tool.uv]
default-groups = ["dev"]

[[tool.uv.index]]
name = "pytorch-cpu"
url = "https://download.pytorch.org/whl/cpu"
explicit = true

[tool.uv.sources]
torch = [
  { index = "pytorch-cpu", marker = "sys_platform == 'linux' or sys_platform == 'win32'" },
]

[tool.hatch.build.targets.wheel]
packages = ["src/shopify_forecast_mcp"]

[tool.pytest.ini_options]
minversion = "8.0"
asyncio_mode = "strict"
testpaths = ["tests"]
addopts = "-ra --strict-markers --strict-config"
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.mypy]
python_version = "3.11"
strict = true
```

## Revised source layout

```
shopify-forecast-mcp/
├── src/
│   └── shopify_forecast_mcp/        # SINGLE importable distribution
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py                   # `shopify-forecast` entry
│       ├── config.py                # pydantic-settings BaseSettings
│       ├── core/
│       │   ├── __init__.py
│       │   ├── shopify_client.py
│       │   ├── timeseries.py
│       │   ├── covariates.py
│       │   ├── forecaster.py
│       │   └── analytics.py
│       └── mcp/
│           ├── __init__.py
│           ├── server.py            # `shopify-forecast-mcp` entry
│           └── tools.py
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── sample_orders.json
│   │   ├── sample_daily_revenue.csv
│   │   └── sample_skus.csv
│   ├── test_shopify_client.py
│   ├── test_timeseries.py
│   ├── test_forecaster.py
│   ├── test_analytics.py
│   └── test_mcp_tools.py
├── examples/
├── docker/
│   └── Dockerfile
├── .env.example
├── .python-version
├── LICENSE
├── README.md
├── pyproject.toml
└── uv.lock
```

## PyTorch strategy

CPU wheel by default via `tool.uv.sources` index override. GPU as opt-in extra. Both `main` functions in entry points must be **synchronous wrappers** that call `asyncio.run(...)` internally.

## HuggingFace cache strategy

- Default cache: `$HF_HOME` or `~/.cache/huggingface/hub`.
- In CI: cache `~/.cache/huggingface` with key `hf-timesfm-2.5-v1`.
- In Docker: separate build stage runs `snapshot_download('google/timesfm-2.5-200m-pytorch')`, copy `/opt/hf-cache` into final stage.
- Two image tags: `:latest` (lazy download on first run, smaller) and `:bundled` (model baked in, fast cold start).
- First-run UX: log `Downloading TimesFM 2.5 (~400MB, one-time)…` so users don't think it hung.

## `pydantic-settings` config

```python
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SHOPIFY_FORECAST_",
        extra="ignore",
        case_sensitive=False,
    )
    shop: str = Field(..., description="mystore.myshopify.com")
    access_token: SecretStr
    api_version: str = "2026-04"
    timesfm_device: str = "cpu"
    timesfm_context_length: int = 1024
    timesfm_horizon: int = 90
    forecast_cache_ttl: int = 3600
    log_level: str = "INFO"
    hf_home: str | None = None

def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

`.env.example`:

```dotenv
SHOPIFY_FORECAST_SHOP=mystore.myshopify.com
SHOPIFY_FORECAST_ACCESS_TOKEN=shpat_xxx
SHOPIFY_FORECAST_API_VERSION=2026-04
SHOPIFY_FORECAST_LOG_LEVEL=INFO
# Optional:
# SHOPIFY_FORECAST_TIMESFM_DEVICE=cpu
# SHOPIFY_FORECAST_HF_HOME=/opt/hf-cache
```

## Docker (multistage)

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY src ./src
RUN uv sync --frozen --no-dev

FROM builder AS models
ENV HF_HOME=/opt/hf-cache
RUN uv run python -c "from huggingface_hub import snapshot_download; \
  snapshot_download('google/timesfm-2.5-200m-pytorch', cache_dir='/opt/hf-cache')"

FROM python:3.12-slim
RUN useradd -m app
ENV HF_HOME=/opt/hf-cache PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
COPY --from=builder /app /app
COPY --from=models  /opt/hf-cache /opt/hf-cache
USER app
WORKDIR /app
ENTRYPOINT ["shopify-forecast-mcp"]
```

## License

- PEP 639 SPDX: `license = "MIT"` + `license-files = ["LICENSE"]`.
- Plain `LICENSE` file with standard MIT text + `Copyright (c) 2026 OmniAlta LLC`.
- Trove classifier still required: `License :: OSI Approved :: MIT License`.

## Distribution priority

1. **PyPI** → `uvx shopify-forecast-mcp` (primary)
2. **Docker** → `ghcr.io/mcostigliola321/shopify-forecast-mcp:latest` (containerized / self-hosted)
3. **`uv tool install`** → persistent local install
4. **(Skip)** npm shim — only if user demand emerges

## Open questions (defer to phase)

1. TimesFM commit SHA to pin (verify at scaffold time with `uv add --dry-run`).
2. GH Actions OIDC + PyPI Trusted Publisher setup (~15 min spike).
3. Windows path quoting in Claude Desktop — known gotcha; document in SETUP.md.

## Sources

- https://docs.astral.sh/uv/guides/package/
- https://docs.astral.sh/uv/guides/integration/pytorch/
- https://github.com/modelcontextprotocol/create-python-server
- https://docs.pydantic.dev/latest/concepts/pydantic_settings/
