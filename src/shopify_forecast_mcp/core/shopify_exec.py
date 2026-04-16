"""Execute GraphQL queries via the Shopify CLI subprocess.

Wraps ``shopify store execute --json`` as an async subprocess call,
parsing the JSON output and raising :class:`ShopifyCliError` on
non-zero exit codes or unparseable output.
"""

from __future__ import annotations

import asyncio
import json
import logging

from shopify_forecast_mcp.core.exceptions import ShopifyCliError

logger = logging.getLogger(__name__)


async def execute_graphql(
    store: str,
    query: str,
    variables: dict | None = None,
    allow_mutations: bool = False,
) -> dict:
    """Execute a GraphQL query via the Shopify CLI subprocess.

    Builds and runs::

        shopify store execute --store <store> --json --query <query>
            [--variables <json>] [--allow-mutations]

    Args:
        store: The Shopify store domain (e.g. ``mystore.myshopify.com``).
        query: The GraphQL query string.
        variables: Optional variables dict to pass as JSON.
        allow_mutations: If True, adds ``--allow-mutations`` flag.

    Returns:
        Parsed JSON dict from CLI stdout.

    Raises:
        ShopifyCliError: On non-zero exit code or unparseable JSON output.
    """
    cmd = [
        "shopify", "store", "execute",
        "--store", store,
        "--json",
        "--query", query,
    ]

    if variables is not None and len(variables) > 0:
        cmd += ["--variables", json.dumps(variables)]

    if allow_mutations:
        cmd += ["--allow-mutations"]

    logger.debug("Executing Shopify CLI: %s", " ".join(cmd[:6]) + " ...")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise ShopifyCliError(
            f"shopify store execute failed (exit {proc.returncode}): "
            f"{stderr.decode().strip()}"
        )

    try:
        result = json.loads(stdout)
    except json.JSONDecodeError:
        raise ShopifyCliError(
            f"Invalid JSON from shopify CLI: {stdout.decode()[:200]}"
        )

    return result
