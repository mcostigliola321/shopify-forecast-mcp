# syntax=docker/dockerfile:1.9
# shopify-forecast-mcp — multi-stage Dockerfile
# Two buildable targets:
#   runtime-lazy     → :latest tag   (model downloads on first forecast call)
#   runtime-bundled  → :bundled tag  (TimesFM 2.5 baked into /opt/hf-cache)
# Multi-arch: linux/amd64 + linux/arm64 via buildx (see .github/workflows/publish.yml)
# Implements D-06, D-08, D-10 from phase 07-CONTEXT.md.

# =============================================================
# Stage 1: uv-builder — resolve + install deps into /app/.venv
# Shared by both runtime targets.
# =============================================================
FROM python:3.11-slim AS uv-builder

# Copy uv binaries from the official Astral image (no pip install needed).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# uv performance knobs documented in the Astral Docker guide.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Cache dep install layer: deps change less often than source.
COPY pyproject.toml uv.lock ./

# First sync: deps only, no project. Maximizes layer cache hit.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Second sync: with project code, as a real install (not editable).
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# =============================================================
# Stage 2: runtime-lazy — :latest tag (model download on first call)
# =============================================================
FROM python:3.11-slim AS runtime-lazy

# Create non-root user (ASVS V14).
RUN useradd -m -u 1000 app

# Copy venv + project from the builder.
COPY --from=uv-builder /app /app

# Copy entrypoint dispatcher.
COPY docker-entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh && chown -R app:app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/app/.cache/huggingface \
    PYTHONDONTWRITEBYTECODE=1

USER app
WORKDIR /app

# JSON-array ENTRYPOINT → SIGTERM reaches the Python process (Pitfall 8).
ENTRYPOINT ["/app/entrypoint.sh"]
CMD []

# =============================================================
# Stage 3: model-downloader — populates /opt/hf-cache with TimesFM weights
# Derived from uv-builder (already has .venv + torch + timesfm).
# =============================================================
FROM uv-builder AS model-downloader

ENV HF_HOME=/opt/hf-cache \
    PATH="/app/.venv/bin:$PATH"

# Download TimesFM 2.5 weights (~400MB) at build time.
# HF_HOME controls cache destination; from_pretrained writes the whole
# model repo into /opt/hf-cache/hub/models--google--timesfm-2.5-200m-pytorch/.
RUN mkdir -p /opt/hf-cache && \
    python -c "from timesfm import TimesFM_2p5_200M_torch; TimesFM_2p5_200M_torch.from_pretrained('google/timesfm-2.5-200m-pytorch')"

# =============================================================
# Stage 4: runtime-bundled — :bundled tag (offline-capable)
# Copies venv from uv-builder AND model weights from model-downloader.
# =============================================================
FROM python:3.11-slim AS runtime-bundled

RUN useradd -m -u 1000 app

# Copy venv + project.
COPY --from=uv-builder /app /app

# Copy pre-downloaded TimesFM weights (Pitfall 3: HF_HOME must match final stage).
COPY --from=model-downloader /opt/hf-cache /opt/hf-cache

# Copy entrypoint dispatcher.
COPY docker-entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh && \
    chown -R app:app /app /opt/hf-cache

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/opt/hf-cache \
    PYTHONDONTWRITEBYTECODE=1

USER app
WORKDIR /app

ENTRYPOINT ["/app/entrypoint.sh"]
CMD []
