"""MCP server adapter (ROADMAP M4-T1, brief §5).

Exposes the shared tool registry over the Model Context Protocol so Claude Code
can call CAIRN. The `mcp` SDK is an *optional* dependency (`pip install
".[mcp]"`) — it's imported lazily inside `build_server`, so this module never
burdens the stdlib-only Layer-0 gate. The CLI (`cli.py`) is the dependency-free
mirror of the same registry.

Run:  python -m cairn.mcp_server         # starts the server over stdio
"""

from __future__ import annotations

import json
from pathlib import Path

from .tools import default_registry


def threshold_from_env(environ) -> float | None:
    """The support floor the OPERATOR chose, or None to use the store's calibration.

    None is the load-bearing default. This used to fall back to the EDGAR constant, so
    every MCP session passed an explicit float, `default_registry` never read the
    store's calibration record (RT-9), and every audit entry was stamped "EXPLICIT
    OVERRIDE … supplied by the caller" — false, since nobody supplied it. On the patent
    engagement that meant deciding at 15.0 instead of the store's calibrated 6.2, and
    the MCP path is the one the agent loop and Layer-E both use. (Audit 2026-09-26.)
    """
    raw = (environ.get("CAIRN_SUPPORT_THRESHOLD") or "").strip()
    return float(raw) if raw else None


def build_server(store_dir: Path | str = "corpus/store", audit_path: Path | str | None = None,
                 *, support_threshold: float | None = None):
    """Build an MCP Server exposing the CAIRN tools. Requires the `mcp` SDK.

    `support_threshold=None` resolves the floor from the store's calibration record;
    pass a float only for a deliberate, operator-chosen override.
    """
    import mcp.types as types
    from mcp.server import Server

    registry = default_registry(store_dir, audit_path, support_threshold=support_threshold)
    server = Server("cairn")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=t.name,
                description=t.description,
                inputSchema=t.input_schema,  # per-tool contract (M4-T2)
            )
            for t in registry.values()
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
        result = registry[name].handler(arguments or {})
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    return server


def main() -> int:  # pragma: no cover - requires the mcp SDK + a stdio client
    import os

    import anyio
    from mcp.server.stdio import stdio_server

    # Log interactions so a session is auditable/replayable (I5) and Layer-E can
    # score from the audit log. Configurable for tests/CI.
    store_dir = os.environ.get("CAIRN_STORE", "corpus/store")
    audit_path = os.environ.get("CAIRN_AUDIT", "audit_log/agent.jsonl")

    # Session delimiter (RT-1): each server spawn = one working session. The clock
    # lives here in the adapter (I6 cores stay clock-free); label via env.
    import time

    from .audit import AuditLog
    from .session import session_start_record

    Path(audit_path).parent.mkdir(parents=True, exist_ok=True)
    AuditLog(audit_path).append(session_start_record(
        label=os.environ.get("CAIRN_SESSION_LABEL"),
        ts=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    ))

    server = build_server(store_dir, audit_path,
                          support_threshold=threshold_from_env(os.environ))

    async def _run() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(_run)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
