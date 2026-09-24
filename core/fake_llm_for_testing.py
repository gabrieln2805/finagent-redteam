"""
A deterministic, scripted stand-in for a real LLM -- used only to verify
that MultiMCPClient + the agent loop correctly route tool calls to the
right server and feed results back, without needing a live API key or
local Ollama server. Real runs should use AnthropicToolLLM or
OpenAICompatibleToolLLM instead.
"""
from core.llm_backends import ToolCallingLLM, LLMTurn


class FakeScriptedLLM(ToolCallingLLM):
    def __init__(self, system_prompt, anthropic_tools, openai_tools, script):
        super().__init__(system_prompt, anthropic_tools, openai_tools)
        self._script = script
        self._step = 0

    def _emit(self, i):
        if i >= len(self._script):
            return LLMTurn(text="(script exhausted)", tool_calls=[])
        step = self._script[i]
        if "tool_calls" in step:
            calls = [{"call_id": f"fake_{i}_{j}", "name": c["name"], "input": c["input"]}
                      for j, c in enumerate(step["tool_calls"])]
            return LLMTurn(text=step.get("text"), tool_calls=calls)
        return LLMTurn(text=step.get("text"), tool_calls=[])

    async def start(self, user_message: str) -> LLMTurn:
        self._step = 0
        return self._emit(self._step)

    async def submit_tool_results(self, results: list) -> LLMTurn:
        self._step += 1
        return self._emit(self._step)
