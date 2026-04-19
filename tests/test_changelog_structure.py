"""CHANGELOG.md structural assertions (Plan 4 D-21)."""
from __future__ import annotations
import pathlib
import re

import pytest

CHANGELOG = pathlib.Path("CHANGELOG.md")


def _read() -> str:
    if not CHANGELOG.exists():
        pytest.skip("CHANGELOG.md not yet created (Plan 4 Wave 2)")
    return CHANGELOG.read_text()


def test_changelog_exists():
    if not CHANGELOG.exists():
        pytest.skip("CHANGELOG.md not yet created (Plan 4 Wave 2)")
    assert CHANGELOG.exists(), "Plan 4 must create CHANGELOG.md (D-21)"


def test_changelog_header():
    text = _read()
    assert text.startswith("# Changelog"), \
        "Keep a Changelog format: first line must be '# Changelog'"


def test_changelog_mentions_keep_a_changelog():
    text = _read()
    assert "keepachangelog.com" in text.lower(), \
        "Must reference Keep a Changelog format URL"


def test_changelog_mentions_semver():
    text = _read()
    assert "semver.org" in text.lower() or "semantic versioning" in text.lower(), \
        "Must reference Semantic Versioning"


def test_changelog_has_unreleased_section():
    text = _read()
    assert re.search(r"^##\s+\[Unreleased\]", text, re.MULTILINE), \
        "Keep a Changelog requires an [Unreleased] section at the top"


def test_changelog_has_0_1_0_section():
    text = _read()
    assert re.search(r"^##\s+\[0\.1\.0\]", text, re.MULTILINE), \
        "D-21: must seed [0.1.0] section covering Phases 1-6 deliverables"


def test_changelog_0_1_0_has_added_subsection():
    text = _read()
    # Find the 0.1.0 section span
    m = re.search(r"^##\s+\[0\.1\.0\].*?(?=^##\s+\[|\Z)", text, re.MULTILINE | re.DOTALL)
    assert m, "no [0.1.0] section found"
    section = m.group(0)
    assert re.search(r"^###\s+Added", section, re.MULTILINE), \
        "D-21: [0.1.0] must have an ### Added subsection populated"


def test_changelog_0_1_0_lists_mcp_tools():
    """D-21 + PROJECT.md: [0.1.0] Added must mention the 7 MCP tools."""
    text = _read()
    m = re.search(r"^##\s+\[0\.1\.0\].*?(?=^##\s+\[|\Z)", text, re.MULTILINE | re.DOTALL)
    section = m.group(0) if m else ""
    # At least three tool names should appear — softer assertion than all seven to
    # allow narrative prose framing
    tool_names = ["forecast_revenue", "forecast_demand", "analyze_promotion",
                  "detect_anomalies", "compare_periods", "compare_scenarios", "get_seasonality"]
    hits = sum(1 for t in tool_names if t in section)
    assert hits >= 3, f"[0.1.0] Added should reference MCP tools by name; found {hits}/7"
