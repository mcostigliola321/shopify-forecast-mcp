"""Dockerfile structural assertions (Plan 3 D-06, D-08, D-10)."""
from __future__ import annotations
import pathlib
import pytest

DOCKERFILE = pathlib.Path("Dockerfile")
ENTRYPOINT = pathlib.Path("docker-entrypoint.sh")
DOCKERIGNORE = pathlib.Path(".dockerignore")


def _dockerfile() -> str:
    if not DOCKERFILE.exists():
        pytest.skip("Dockerfile not yet created (Plan 3 Wave 2)")
    return DOCKERFILE.read_text()


def test_dockerfile_exists():
    if not DOCKERFILE.exists():
        pytest.skip("Dockerfile not yet created (Plan 3 Wave 2)")
    assert DOCKERFILE.exists(), "Plan 3 must create Dockerfile"


def test_dockerfile_uses_python_311_slim():
    text = _dockerfile()
    assert "python:3.11-slim" in text, \
        "D-06: base image must be python:3.11-slim (NOT 3.12 — pyproject is pinned to <3.12)"


def test_dockerfile_has_uv_from_official_image():
    text = _dockerfile()
    assert "ghcr.io/astral-sh/uv" in text, \
        "D-08: copy uv binaries from ghcr.io/astral-sh/uv"


def test_dockerfile_multistage_has_runtime_lazy_and_bundled_targets():
    text = _dockerfile()
    assert "AS runtime-lazy" in text, \
        "D-08: must have a 'runtime-lazy' stage for :latest"
    assert "AS runtime-bundled" in text, \
        "D-08: must have a 'runtime-bundled' stage for :bundled"


def test_dockerfile_bundled_stage_sets_hf_home():
    text = _dockerfile()
    assert "HF_HOME=/opt/hf-cache" in text, \
        "D-08 + RESEARCH Pitfall 3: HF_HOME must be /opt/hf-cache in both downloader + final stage"


def test_dockerfile_entrypoint_is_json_array_form():
    text = _dockerfile()
    assert 'ENTRYPOINT ["/app/entrypoint.sh"]' in text, \
        "RESEARCH Pitfall 8: ENTRYPOINT must use JSON array form for SIGTERM propagation"


def test_dockerfile_runs_as_non_root():
    text = _dockerfile()
    assert "USER app" in text, \
        "Security: containers must run as non-root (ASVS V14)"


def test_entrypoint_script_exists():
    if not ENTRYPOINT.exists():
        pytest.skip("docker-entrypoint.sh not yet created (Plan 3 Wave 2)")
    assert ENTRYPOINT.exists(), "Plan 3 must create docker-entrypoint.sh"


def test_entrypoint_dispatches_all_verbs():
    """D-10: entrypoint must handle mcp, CLI verbs, and help."""
    if not ENTRYPOINT.exists():
        pytest.skip("docker-entrypoint.sh not yet created")
    text = ENTRYPOINT.read_text()
    required = ["mcp", "revenue", "demand", "promo", "compare", "scenarios", "auth", "--help"]
    for verb in required:
        assert verb in text, f"D-10: entrypoint must dispatch on '{verb}'"


def test_entrypoint_uses_exec_for_signal_propagation():
    if not ENTRYPOINT.exists():
        pytest.skip("docker-entrypoint.sh not yet created")
    text = ENTRYPOINT.read_text()
    assert "exec " in text, \
        "RESEARCH Pitfall 8: entrypoint must use 'exec' so SIGTERM reaches the Python process"


def test_dockerignore_exists():
    if not DOCKERIGNORE.exists():
        pytest.skip(".dockerignore not yet created (Plan 3 Wave 2)")
    assert DOCKERIGNORE.exists(), "Plan 3 must create .dockerignore"


def test_dockerignore_excludes_planning_and_venv():
    if not DOCKERIGNORE.exists():
        pytest.skip()
    text = DOCKERIGNORE.read_text()
    for pattern in [".planning", ".venv", "tests/", ".pytest_cache"]:
        assert pattern in text, f".dockerignore must exclude '{pattern}'"
