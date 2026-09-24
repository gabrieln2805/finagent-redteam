"""
The real agent loop: give an LLM backend a task, let it call real MCP
tools (routed through MultiMCPClient) as many times as it wants, and record
everything it did.
"""
from dataclasses import dataclass, field
from typing import Optional

from core.mcp_multi_client import MultiMCPClient
from core.llm_backends import ToolCallingLLM


@dataclass
class ToolCallRecord:
    name: str
    input: dict
    output: str


@dataclass
class AgentRunResult:
    final_text: Optional[str]
    tool_calls: list  # list[ToolCallRecord]
    hit_max_turns: bool


async def run_agentic_task(llm: ToolCallingLLM, mcp_client: MultiMCPClient,
                            user_message: str, max_turns: int = 6) -> AgentRunResult:
    tool_calls: list[ToolCallRecord] = []
    turn = await llm.start(user_message)

    for _ in range(max_turns):
        if turn.is_final:
            return AgentRunResult(final_text=turn.text, tool_calls=tool_calls, hit_max_turns=False)

        results = []
        for call in turn.tool_calls:
            output = await mcp_client.call_tool(call["name"], call["input"])
            tool_calls.append(ToolCallRecord(name=call["name"], input=call["input"], output=output))
            results.append((call["call_id"], output))

        turn = await llm.submit_tool_results(results)

    return AgentRunResult(final_text=turn.text, tool_calls=tool_calls, hit_max_turns=True)
