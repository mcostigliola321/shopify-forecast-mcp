"""Structural assertions for .github/workflows/publish.yml (Phase 7 Plan 2).

Skips when file absent (Wave 0 infrastructure ahead of Plan 2 landing).
"""
from __future__ import annotations
import pathlib
import re

import pytest

try:
    import yaml  # pyyaml is a transitive dep via pydantic/mcp; if missing, skip hard
except ImportError:
    yaml = None

WORKFLOW = pathlib.Path(".github/workflows/publish.yml")


def _load() -> dict:
    if not WORKFLOW.exists():
        pytest.skip("publish.yml not yet created (Plan 2 Wave 2)")
    if yaml is None:
        pytest.skip("pyyaml not available in test env")
    return yaml.safe_load(WORKFLOW.read_text())


def _read_text() -> str:
    if not WORKFLOW.exists():
        pytest.skip("publish.yml not yet created (Plan 2 Wave 2)")
    return WORKFLOW.read_text()


def test_publish_workflow_exists():
    if not WORKFLOW.exists():
        pytest.skip("publish.yml not yet created (Plan 2 Wave 2)")
    assert WORKFLOW.exists(), "Plan 2 must create .github/workflows/publish.yml"


def test_publish_workflow_triggers_on_version_tag():
    data = _load()
    # YAML 'on' parses as True in Python — use the actual key 'on' or True fallback
    on = data.get(True, data.get("on"))
    assert on is not None, "workflow missing 'on' trigger"
    tags = on.get("push", {}).get("tags", [])
    assert any("v*" in t for t in tags), f"expected tag trigger 'v*', got {tags}"


def test_publish_workflow_has_oidc_permission():
    text = _read_text()
    assert "id-token: write" in text, \
        "Trusted Publisher OIDC requires 'id-token: write' permission (D-05, R12.1)"


def test_publish_workflow_has_ghcr_write_permission():
    text = _read_text()
    assert "packages: write" in text, \
        "GHCR Docker push requires 'packages: write' permission (R12.2)"


def test_publish_workflow_uses_pypi_environment():
    text = _read_text()
    assert re.search(r"environment:\s*\n?\s*(name:\s*)?pypi", text), \
        "Trusted Publisher best practice: scope publish job to environment: pypi (D-05)"


def test_publish_workflow_waits_for_ci():
    """D-01/D-03: publish must gate on ci.yml being green for same SHA."""
    text = _read_text()
    # Accept either the wait-on-check community action or hand-rolled gh-api polling
    assert ("wait-on-check-action" in text or "gh api" in text and "check-runs" in text), \
        "publish.yml must wait on ci.yml for same SHA (D-01, D-03)"


def test_publish_workflow_has_no_static_pypi_token():
    text = _read_text()
    forbidden = ["PYPI_TOKEN", "PYPI_API_TOKEN", "TWINE_PASSWORD"]
    for bad in forbidden:
        assert bad not in text, f"D-05: publish workflow must NOT reference {bad} (OIDC only)"


def test_publish_workflow_has_docker_multi_arch():
    """R12.2: multi-arch build (linux/amd64 + linux/arm64)."""
    text = _read_text()
    assert "linux/amd64" in text and "linux/arm64" in text, \
        "Docker build must target both linux/amd64 and linux/arm64 (D-07)"


def test_publish_workflow_has_release_creation():
    """D-04: GitHub Release created from tag with dist/* attached."""
    text = _read_text()
    assert ("softprops/action-gh-release" in text or "gh release create" in text), \
        "D-04: must create GitHub Release with artifacts attached"
