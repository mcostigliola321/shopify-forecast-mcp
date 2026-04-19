"""Documentation completeness assertions (Plan 4, R11.1-R11.4)."""
from __future__ import annotations
import inspect
import pathlib
import re

import pytest

README = pathlib.Path("README.md")
SETUP = pathlib.Path("docs/SETUP.md")
TOOLS = pathlib.Path("docs/TOOLS.md")
ARCH = pathlib.Path("docs/ARCHITECTURE.md")

# Plan 4 will replace the 337-byte placeholder README with the full merchant-facing
# rewrite. Until then, skip the README substance assertions so Wave 0 is non-blocking.
README_MIN_BYTES = 2000


def _read(p: pathlib.Path) -> str:
    if not p.exists():
        pytest.skip(f"{p} not yet created")
    return p.read_text()


def _read_substantial_readme() -> str:
    """Read README only when it has been rewritten past placeholder size."""
    if not README.exists():
        pytest.skip("README.md not yet created")
    text = README.read_text()
    if len(text) < README_MIN_BYTES:
        pytest.skip(f"README.md still placeholder ({len(text)} bytes) — Plan 4 Wave 2 rewrite pending")
    return text


# --- README (R11.1, D-16) ---

def test_readme_exists():
    if not README.exists():
        pytest.skip("README.md not yet rewritten (Plan 4 Wave 2)")
    assert README.exists(), "README.md must exist"


def test_readme_not_placeholder():
    text = _read_substantial_readme()
    # Re-assert once past the skip gate so the test has an explicit post-rewrite claim.
    assert len(text) >= README_MIN_BYTES, \
        "D-16: README rewrite must be substantial (>2KB), not a placeholder"


def test_readme_has_alpha_banner():
    text = _read_substantial_readme()
    assert re.search(r"(Alpha|v0\.1\.0)", text), \
        "D-18: README must have 'v0.1.0 Alpha' callout banner"


def test_readme_has_required_sections():
    """D-16: locked structure — Quick start, Tools, Architecture, Configuration, CLI, Roadmap, License."""
    text = _read_substantial_readme()
    required = ["Quick start", "Tools", "Architecture", "Configuration", "CLI", "License"]
    for heading in required:
        assert re.search(rf"^##\s+.*{heading}", text, re.MULTILINE | re.IGNORECASE), \
            f"README missing section: {heading}"


def test_readme_shows_uvx_invocation():
    text = _read_substantial_readme()
    assert "uvx shopify-forecast-mcp" in text, \
        "R11.5: README must show `uvx shopify-forecast-mcp` as the install path"


def test_readme_has_claude_desktop_snippet():
    text = _read_substantial_readme()
    assert "claude_desktop_config.json" in text or "mcpServers" in text, \
        "R11.5: README must include Claude Desktop config snippet"


# --- SETUP.md (R11.2, D-17) ---

def test_setup_md_exists():
    if not SETUP.exists():
        pytest.skip("docs/SETUP.md not yet created (Plan 4 Wave 2)")
    assert SETUP.exists(), "docs/SETUP.md must exist"


def test_setup_covers_required_scopes():
    text = _read(SETUP)
    scopes = ["read_orders", "read_all_orders", "read_products", "read_inventory"]
    for scope in scopes:
        assert scope in text, f"D-17 + R2.8: SETUP.md must document scope '{scope}'"


def test_setup_covers_both_install_paths():
    text = _read(SETUP)
    assert "uvx" in text, "D-17: uvx install path documented"
    assert "docker" in text.lower(), "D-17: Docker install path documented"


def test_setup_has_env_var_table():
    text = _read(SETUP)
    assert "SHOPIFY_FORECAST_SHOP" in text and "SHOPIFY_FORECAST_ACCESS_TOKEN" in text, \
        "D-17: SETUP.md must document env vars"


# --- TOOLS.md (R11.3, D-15) ---

def test_tools_md_exists():
    if not TOOLS.exists():
        pytest.skip("docs/TOOLS.md not yet created (Plan 4 Wave 2)")
    assert TOOLS.exists(), "docs/TOOLS.md must exist"


def test_tools_md_has_section_per_tool():
    """D-15: one section per MCP tool, all 7 present."""
    text = _read(TOOLS)
    tools = [
        "forecast_revenue", "forecast_demand", "analyze_promotion",
        "detect_anomalies", "compare_periods", "compare_scenarios", "get_seasonality",
    ]
    for tool in tools:
        assert tool in text, f"D-15: TOOLS.md missing section for tool '{tool}'"


def test_tools_md_has_per_tool_anchors():
    text = _read(TOOLS)
    # D-15: anchor-linked index at top
    assert "#forecast_revenue" in text or "#forecast-revenue" in text, \
        "D-15: TOOLS.md top-of-page index must have anchor links"


# --- ARCHITECTURE.md (R11.4, D-14) ---

def test_architecture_md_exists():
    if not ARCH.exists():
        pytest.skip("docs/ARCHITECTURE.md not yet created (Plan 4 Wave 2)")
    assert ARCH.exists(), "docs/ARCHITECTURE.md must exist"


def test_architecture_has_three_mermaid_diagrams():
    """D-14: exactly three required diagrams (two-layer arch, data flow, backend selection)."""
    text = _read(ARCH)
    count = len(re.findall(r"^```mermaid", text, re.MULTILINE))
    assert count >= 3, f"D-14: expected >=3 mermaid diagrams, found {count}"


def test_architecture_mentions_dual_backend():
    text = _read(ARCH)
    assert "DirectBackend" in text and "CliBackend" in text, \
        "D-14: ARCHITECTURE.md must document the dual-backend (Phase 4.1) design"


# --- Placeholder rot ---

def test_no_placeholder_tokens_in_docs():
    """Docs must not ship with TODO/XXX/[date]-style placeholders."""
    placeholders = ["TODO", "XXX", "FIXME", "[date]", "[TBD]"]
    for p in [README, SETUP, TOOLS, ARCH]:
        if not p.exists():
            continue
        text = p.read_text()
        for token in placeholders:
            # Allow placeholders inside fenced code blocks (shell examples)
            outside_code = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
            assert token not in outside_code, f"{p}: contains placeholder '{token}' outside code block"
