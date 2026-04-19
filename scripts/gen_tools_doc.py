#!/usr/bin/env python3
"""Generate docs/TOOLS.md per-tool sections from Pydantic ParamsModels.

Source of truth: src/shopify_forecast_mcp/mcp/tools.py

Usage:
    uv run python scripts/gen_tools_doc.py                # print to stdout
    uv run python scripts/gen_tools_doc.py -o docs/TOOLS.md  # write to file

Run manually whenever a tool's Pydantic schema changes. Not a CI gate — the
committed docs/TOOLS.md file is the artifact; this script is the renderer.
"""

from __future__ import annotations

import argparse
import inspect
import sys
from pathlib import Path
from typing import Any

# --- Tool display metadata: name -> (ParamsClassName) ---
# Order matches README Tools table order.
TOOLS: list[tuple[str, str]] = [
    ("forecast_revenue",    "ForecastRevenueParams"),
    ("forecast_demand",     "ForecastDemandParams"),
    ("analyze_promotion",   "AnalyzePromotionParams"),
    ("detect_anomalies",    "DetectAnomaliesParams"),
    ("compare_periods",     "ComparePeriodsParams"),
    ("compare_scenarios",   "CompareScenariosParams"),
    ("get_seasonality",     "GetSeasonalityParams"),
]


def _format_type(spec: dict[str, Any]) -> str:
    """Human-readable type label from a JSON Schema property dict."""
    if "enum" in spec:
        return " \u2502 ".join(f"`{v}`" for v in spec["enum"])
    if "type" in spec:
        t = spec["type"]
        if t == "array":
            inner = spec.get("items", {}).get("type", "any")
            return f"array[{inner}]"
        return str(t)
    if "anyOf" in spec:
        parts = [_format_type(o) for o in spec["anyOf"] if o.get("type") != "null"]
        nullable = any(o.get("type") == "null" for o in spec["anyOf"])
        suffix = " | null" if nullable else ""
        return " | ".join(parts) + suffix
    if "$ref" in spec:
        return spec["$ref"].rsplit("/", 1)[-1]
    return "any"


def _format_default(spec: dict[str, Any]) -> str:
    if "default" not in spec:
        return "\u2014"
    default = spec["default"]
    if default is None:
        return "`null`"
    if isinstance(default, str):
        return f"`\"{default}\"`"
    return f"`{default}`"


def render_schema_table(model_cls: type) -> str:
    schema = model_cls.model_json_schema()
    props: dict[str, Any] = schema.get("properties", {})
    required: set[str] = set(schema.get("required", []))
    if not props:
        return "_(no parameters)_\n"
    rows = [
        "| Field | Type | Required | Default | Description |",
        "|-------|------|----------|---------|-------------|",
    ]
    for name, spec in props.items():
        typ = _format_type(spec)
        req = "\u2713" if name in required else ""
        default = _format_default(spec)
        desc = spec.get("description", "").replace("|", "\\|").replace("\n", " ")
        rows.append(f"| `{name}` | {typ} | {req} | {default} | {desc} |")
    return "\n".join(rows) + "\n"


def render_tool_section(tool_name: str, params_cls: type, handler_doc: str) -> str:
    anchor = tool_name.replace("_", "-")
    lines = [
        f"## `{tool_name}` <a id=\"{anchor}\"></a>",
        "",
        handler_doc.strip(),
        "",
        "### Parameters",
        "",
        render_schema_table(params_cls),
    ]
    return "\n".join(lines)


def render_index(tool_names: list[str]) -> str:
    lines = ["## Tools", ""]
    for name in tool_names:
        anchor = name.replace("_", "-")
        lines.append(f"- [`{name}`](#{anchor})")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate docs/TOOLS.md from Pydantic models")
    ap.add_argument("-o", "--output", type=Path, default=None,
                    help="Write to file (default: stdout)")
    args = ap.parse_args()

    # Import is late so --help works without project install
    from shopify_forecast_mcp.mcp import tools as tools_module

    out = [
        "# MCP Tools Reference",
        "",
        "Auto-generated from `src/shopify_forecast_mcp/mcp/tools.py`.",
        "Run `uv run python scripts/gen_tools_doc.py -o docs/TOOLS.md` to refresh.",
        "",
    ]
    out.append(render_index([n for n, _ in TOOLS]))
    out.append("")

    for tool_name, params_class_name in TOOLS:
        params_cls = getattr(tools_module, params_class_name, None)
        if params_cls is None:
            print(f"WARNING: {params_class_name} not found in tools module", file=sys.stderr)
            continue
        handler = getattr(tools_module, tool_name, None)
        handler_doc = (inspect.getdoc(handler) or f"MCP tool `{tool_name}`.") if handler else ""
        out.append(render_tool_section(tool_name, params_cls, handler_doc))
        out.append("")

    rendered = "\n".join(out)
    if args.output:
        args.output.write_text(rendered)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
