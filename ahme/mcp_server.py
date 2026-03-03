"""
AHME MCP Server — Model Context Protocol integration.

Exposes three tools to any MCP-compatible AI coding assistant:
  • ingest_context     — push raw conversation text into AHME
  • get_master_memory  — pull the compressed summary (and reset context window)
  • clear_context      — explicitly wipe all queued data

Each project/tool gets its own isolated memory namespace.
Namespace is resolved in priority order:
  1. Explicit `namespace` parameter in the tool call
  2. AHME_NAMESPACE environment variable
  3. Current working directory name (auto-detected)

All namespace data lives in ~/.ahme/{namespace}/ — separate DB, log, and memory file.

Quick start:
    pip install -e .
    python -m ahme.mcp_server

MCP config (any tool):
    {
      "mcpServers": {
        "ahme": {
          "command": "python",
          "args": ["-m", "ahme.mcp_server"],
          "env": {
            "PYTHONPATH": "/path/to/ahme",
            "AHME_NAMESPACE": "my-project"
          }
        }
      }
    }
"""
from __future__ import annotations

import asyncio
import argparse
import os
import pathlib
import shutil

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from ahme.config import load_config, override_paths
from ahme.daemon import AHMEDaemon

# ---------------------------------------------------------------------------
# Bootstrap — load base config (auto-copy config.example.toml if needed)
# ---------------------------------------------------------------------------
_PROJECT_DIR = pathlib.Path(__file__).parent.parent
_CONFIG_PATH = _PROJECT_DIR / "config.toml"
_CONFIG_EXAMPLE = _PROJECT_DIR / "config.example.toml"

if not _CONFIG_PATH.exists() and _CONFIG_EXAMPLE.exists():
    shutil.copy(_CONFIG_EXAMPLE, _CONFIG_PATH)

_base_cfg = load_config(str(_CONFIG_PATH))

# ---------------------------------------------------------------------------
# Namespace-based daemon cache
# ---------------------------------------------------------------------------
_AHME_HOME = pathlib.Path.home() / ".ahme"
_daemons: dict[str, AHMEDaemon] = {}
_daemon_tasks: dict[str, asyncio.Task] = {}


def _resolve_namespace(arguments: dict) -> str:
    """Resolve namespace from: explicit param > env var > CWD name."""
    ns = arguments.get("namespace", "").strip()
    if ns:
        return ns
    ns = os.environ.get("AHME_NAMESPACE", "").strip()
    if ns:
        return ns
    return os.path.basename(os.getcwd()) or "default"


def _get_daemon(namespace: str) -> AHMEDaemon:
    """Get or create an isolated daemon for the given namespace."""
    if namespace not in _daemons:
        ns_dir = _AHME_HOME / namespace
        ns_dir.mkdir(parents=True, exist_ok=True)
        ns_cfg = override_paths(_base_cfg, ns_dir)
        _daemons[namespace] = AHMEDaemon(ns_cfg)
    return _daemons[namespace]


def _ensure_running(namespace: str) -> None:
    """Ensure the background daemon for this namespace is running."""
    daemon = _get_daemon(namespace)
    task = _daemon_tasks.get(namespace)
    if task is None or task.done():
        _daemon_tasks[namespace] = asyncio.create_task(daemon.run())


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
server = Server("ahme-memory-engine")

_NS_SCHEMA = {
    "type": "string",
    "description": (
        "Optional. Project namespace for memory isolation. "
        "If omitted, auto-detected from AHME_NAMESPACE env var or current directory name. "
        "Each namespace gets its own database and memory file."
    ),
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="ingest_context",
            description=(
                "Push raw conversation or document text into the AHME memory engine. "
                "AHME will asynchronously compress it into a hierarchical Master Memory Block."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The raw conversation or context text to ingest.",
                    },
                    "namespace": _NS_SCHEMA,
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="get_master_memory",
            description=(
                "Retrieve the latest compressed Master Memory Block from AHME. "
                "Returns a dense, token-efficient summary of all ingested context, "
                "then resets the context window so the next session starts fresh "
                "with the summary as its seed (context-window replacement pattern). "
                "Inject the returned text into your system prompt to restore long-term memory."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "reset": {
                        "type": "boolean",
                        "description": (
                            "If true (default), clears the DB after returning the summary "
                            "and re-seeds it with the summary for the next session. "
                            "Set to false to just read without resetting."
                        ),
                    },
                    "namespace": _NS_SCHEMA,
                },
                "required": [],
            },
        ),
        Tool(
            name="clear_context",
            description=(
                "Explicitly wipe all queued chunks and summaries from AHME's database. "
                "Use this if you want a completely clean slate without retrieving memory first."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": _NS_SCHEMA,
                },
                "required": [],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    namespace = _resolve_namespace(arguments)
    daemon = _get_daemon(namespace)

    # --- ingest_context ---
    if name == "ingest_context":
        text = arguments.get("text", "").strip()
        if not text:
            return [TextContent(type="text", text="Error: 'text' argument is required and must not be empty.")]

        _ensure_running(namespace)
        count = daemon.ingest(text)
        return [
            TextContent(
                type="text",
                text=(
                    f"✅ Ingested {count} chunk(s) into AHME queue.\n"
                    f"📁 Namespace: `{namespace}` (~/.ahme/{namespace}/)\n"
                    f"The daemon will compress them when the system is idle.\n"
                    f"Call `get_master_memory` to retrieve the latest summary."
                ),
            )
        ]

    # --- get_master_memory ---
    elif name == "get_master_memory":
        should_reset = arguments.get("reset", True)

        memory_file = pathlib.Path(daemon._cfg.logging.memory_file)
        if memory_file.exists():
            content = memory_file.read_text(encoding="utf-8").strip()
        else:
            content = daemon.master_memory

        if not content:
            return [
                TextContent(
                    type="text",
                    text=(
                        f"ℹ️  No memory available yet for namespace `{namespace}`.\n"
                        "Use `ingest_context` to push text first. "
                        "AHME will compress it in the background."
                    ),
                )
            ]

        if should_reset:
            daemon.reset(keep_master=True)
            footer = (
                f"\n\n---\n"
                f"🔄 *Context window reset for `{namespace}`. "
                f"DB cleared and re-seeded with this summary.*"
            )
        else:
            footer = f"\n\n---\n📁 *Namespace: `{namespace}`*"

        return [TextContent(type="text", text=content + footer)]

    # --- clear_context ---
    elif name == "clear_context":
        daemon.db.clear_all()
        return [
            TextContent(
                type="text",
                text=f"🗑️ Context cleared for namespace `{namespace}`.",
            )
        ]

    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def _run_stdio() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AHME MCP Server — Asynchronous Hierarchical Memory Engine"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport to use (default: stdio)",
    )
    parser.add_argument("--port", type=int, default=8765, help="Port for SSE transport")
    args = parser.parse_args()

    if args.transport == "stdio":
        asyncio.run(_run_stdio())
    else:
        try:
            from mcp.server.sse import SseServerTransport
            from starlette.applications import Starlette
            from starlette.routing import Route
            import uvicorn

            sse = SseServerTransport("/messages/")

            async def handle_sse(request):
                async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
                    await server.run(streams[0], streams[1], server.create_initialization_options())

            app = Starlette(routes=[Route("/sse", endpoint=handle_sse)])
            print(f"AHME MCP Server (SSE) running on http://localhost:{args.port}")
            uvicorn.run(app, host="0.0.0.0", port=args.port)
        except ImportError as e:
            print(f"SSE transport requires extra deps (pip install uvicorn starlette): {e}")
            raise


if __name__ == "__main__":
    main()
