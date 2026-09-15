# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
Stand-in for Claude Code: an MCP stdio client that connects to `egzos serve --mcp`, lists the
tools, fetches context, remembers something, and shows the inbox. Walking-skeleton harness.

    EGZOS_HOME=... EGZOS_TOKEN=<client token> python scripts/mcp_client_probe.py [scope]
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main(scope: str | None) -> int:
    env = {
        k: v
        for k, v in os.environ.items()
        if k in ("PATH", "HOME", "EGZOS_HOME", "EGZOS_TOKEN", "PYTHONPATH")
    }
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "egzos.cli", "serve", "--mcp"], env=env
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        print("tools:", [t.name for t in tools.tools])
        assert "egzos_approve" not in {t.name for t in tools.tools}, "human-only act leaked to MCP"

        r = await session.call_tool("egzos_fetch", {"scope": scope} if scope else {})
        payload = json.loads(r.content[0].text)
        print(
            f"\nfetch {payload['scope']!r}: chain = "
            f"{' → '.join(layer['path'] for layer in payload['chain'])}"
        )
        for it in payload["items"]:
            print(
                f"  {it['id']}  {it['kind']:<10} {it['trust']:<10} "
                f"@{it['layer']}  “{it['auto_title']}”"
            )

        r = await session.call_tool(
            "egzos_remember",
            {"text": "Claude Code noticed: the Chief prefers merge over rebase.", "kind": "memory"},
        )
        print("\nremember:", r.content[0].text)

        r = await session.call_tool("egzos_inbox", {})
        inbox = json.loads(r.content[0].text)
        print(f"\ninbox: {len(inbox['items'])} item(s)")
        for it in inbox["items"]:
            print(f"  {it['id']}  {it['kind']:<10} {it['trust']:<10} “{it['auto_title']}”")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None)))
