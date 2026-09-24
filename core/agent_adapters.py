"""
Loads a client's own agent, written in Python, so the harness can test it
(--backend python --agent path/to/file.py:make_agent).

The factory is called once per test case with keyword arguments:

    make_agent(system_prompt=str | None,   # --system-prompt text, or None (keep your own)
               openai_tools=[...],         # the harness tools, OpenAI function-calling format
               anthropic_tools=[...])      # the same tools, Anthropic format

and returns an object with two methods (plain or async):

    start(user_message) -> turn
    submit_tool_results([(call_id, output_text), ...]) -> turn

where a turn is an LLMTurn or a dict:

    {"text": "final or interim text", "tool_calls": [{"call_id": "...", "name": "...", "input": {...}}]}

Returning tool calls hands them to the harness, which executes them on the
MCP servers and passes the results back via submit_tool_results. A turn with
no tool calls is the agent's final answer. See examples/guardrailed_agent.py.
"""
import importlib
import importlib.util
import inspect
import os

from core.llm_backends import LLMTurn


def load_agent_factory(spec: str):
    """spec: 'path/to/file.py:factory' or 'package.module:factory'."""
    if ":" not in spec.replace(":\\", "").replace(":/", ""):
        raise SystemExit(f"--agent must look like path/to/file.py:make_agent or my_package.module:make_agent, got {spec!r}")
    module_ref, _, attr = spec.rpartition(":")

    if module_ref.endswith(".py"):
        path = os.path.abspath(module_ref)
        if not os.path.exists(path):
            raise SystemExit(f"--agent file not found: {path}")
        module_spec = importlib.util.spec_from_file_location("client_agent", path)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
    else:
        module = importlib.import_module(module_ref)

    factory = getattr(module, attr, None)
    if not callable(factory):
        raise SystemExit(f"--agent: {module_ref} has no callable named {attr!r}")
    return factory


class PythonAgentAdapter:
    """Wraps a client agent so the agent loop sees the ToolCallingLLM interface."""

    def __init__(self, agent):
        for method in ("start", "submit_tool_results"):
            if not callable(getattr(agent, method, None)):
                raise SystemExit(f"The agent returned by your factory needs a {method}() method")
        self._agent = agent

    @staticmethod
    async def _resolve(value) -> LLMTurn:
        if inspect.isawaitable(value):
            value = await value
        if isinstance(value, LLMTurn):
            return value
        if isinstance(value, dict):
            calls = [
                {"call_id": c.get("call_id") or f"call_{i}", "name": c["name"], "input": c.get("input") or {}}
                for i, c in enumerate(value.get("tool_calls") or [])
            ]
            return LLMTurn(text=value.get("text"), tool_calls=calls)
        if isinstance(value, str):
            return LLMTurn(text=value, tool_calls=[])
        raise TypeError(f"Agent returned {type(value).__name__}; expected an LLMTurn, a dict or a string")

    async def start(self, user_message: str) -> LLMTurn:
        return await self._resolve(self._agent.start(user_message))

    async def submit_tool_results(self, results: list) -> LLMTurn:
        return await self._resolve(self._agent.submit_tool_results(results))
