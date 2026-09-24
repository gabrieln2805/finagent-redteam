"""
Connects to several local MCP stdio servers at once (e.g. finance-records,
eu-financial-records, financial-ops-mock) and presents their tools as one
unified, namespaced set -- so a single agent loop can call across all of
them, and results can be routed back to the correct server.

Namespacing follows the "{server}__{tool}" convention (matching the shape
Claude's own client uses for third-party MCP tools) so identically-named
tools across servers never collide.
"""
import json
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@dataclass
class ToolSpec:
    namespaced_name: str
    server: str
    original_name: str
    description: str
    input_schema: dict


class MultiMCPClient:
    """
    servers_config: {"server_name": {"command": "python3", "args": ["path/to/server.py"]}, ...}
    errlog: where the servers' stderr (their INFO request logs) goes; defaults to our stderr.
    """
    def __init__(self, servers_config: dict, errlog=None):
        self._config = servers_config
        self._errlog = errlog or sys.stderr
        self._sessions: dict[str, ClientSession] = {}
        self._stack: Optional[AsyncExitStack] = None
        self.tools: list[ToolSpec] = []

    async def __aenter__(self):
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        for name, cfg in self._config.items():
            try:
                listed = await self._connect(name, cfg)
            except Exception as e:
                await self._stack.aclose()
                raise ConnectionError(
                    f"Could not start MCP server '{name}' ({cfg['command']} {' '.join(cfg['args'])}): "
                    f"{type(e).__name__}: {e}"
                ) from e
            for t in listed.tools:
                self.tools.append(ToolSpec(
                    namespaced_name=f"{name}__{t.name}",
                    server=name,
                    original_name=t.name,
                    description=t.description or "",
                    input_schema=t.inputSchema or {"type": "object", "properties": {}},
                ))
        return self

    async def _connect(self, name: str, cfg: dict):
        params = StdioServerParameters(command=cfg["command"], args=cfg["args"])
        read, write = await self._stack.enter_async_context(stdio_client(params, errlog=self._errlog))
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._sessions[name] = session
        return await session.list_tools()

    @property
    def connected_servers(self) -> set[str]:
        return set(self._sessions)

    async def __aexit__(self, exc_type, exc, tb):
        await self._stack.__aexit__(exc_type, exc, tb)

    async def call_tool(self, namespaced_name: str, tool_input: dict) -> str:
        spec = next((t for t in self.tools if t.namespaced_name == namespaced_name), None)
        if spec is None:
            return json.dumps({"error": f"no such tool: {namespaced_name}"})
        session = self._sessions[spec.server]
        result = await session.call_tool(spec.original_name, tool_input)
        parts = []
        for block in result.content:
            parts.append(getattr(block, "text", str(block)))
        return "\n".join(parts)

    async def health_check(self, namespaced_name: str, tool_input: dict) -> Optional[str]:
        """Call a read-only tool once; return its error text if it failed, else None."""
        spec = next((t for t in self.tools if t.namespaced_name == namespaced_name), None)
        if spec is None:
            return f"tool {namespaced_name} not found"
        result = await self._sessions[spec.server].call_tool(spec.original_name, tool_input)
        if result.isError:
            return "\n".join(getattr(block, "text", str(block)) for block in result.content)
        return None

    # -- schema conversions for each LLM backend's tool-calling format --

    def as_anthropic_tools(self) -> list[dict]:
        return [
            {"name": t.namespaced_name, "description": t.description, "input_schema": t.input_schema}
            for t in self.tools
        ]

    def as_openai_tools(self) -> list[dict]:
        return [
            {"type": "function", "function": {
                "name": t.namespaced_name, "description": t.description, "parameters": t.input_schema,
            }}
            for t in self.tools
        ]
