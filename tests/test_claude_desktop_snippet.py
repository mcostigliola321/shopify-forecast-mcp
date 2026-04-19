"""Claude Desktop config snippet extraction + JSON validation (R11.5, D-13)."""
from __future__ import annotations
import json
import pathlib
import re

import pytest

README = pathlib.Path("README.md")
SETUP = pathlib.Path("docs/SETUP.md")


def _extract_first_json_block(text: str) -> str | None:
    """Extract the first ```json fenced block from markdown."""
    m = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
    return m.group(1) if m else None


@pytest.mark.parametrize("path", [README, SETUP])
def test_claude_desktop_snippet_is_valid_json(path: pathlib.Path):
    if not path.exists():
        pytest.skip(f"{path} not yet created")
    text = path.read_text()
    if "mcpServers" not in text:
        pytest.skip(f"{path} does not include an MCP client config snippet")
    block = _extract_first_json_block(text)
    assert block is not None, f"{path}: has 'mcpServers' reference but no ```json code block"
    data = json.loads(block)  # raises on parse failure
    assert "mcpServers" in data, f"{path}: snippet must be a full mcpServers config fragment"


def test_readme_snippet_uses_uvx_command():
    if not README.exists():
        pytest.skip()
    text = README.read_text()
    block = _extract_first_json_block(text)
    if not block or "mcpServers" not in block:
        pytest.skip("README does not include Claude Desktop snippet yet")
    data = json.loads(block)
    server_entries = list(data.get("mcpServers", {}).values())
    assert any(e.get("command") == "uvx" for e in server_entries), \
        "R11.5 + D-13: Claude Desktop snippet must use 'command': 'uvx'"
