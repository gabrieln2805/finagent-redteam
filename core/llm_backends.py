"""
Pluggable tool-calling LLM backends. Each maintains its own conversation
state internally and exposes a small, uniform interface:

    turn = await llm.start(user_message)
    while turn.tool_calls:
        results = [(call["call_id"], execute(call)) for call in turn.tool_calls]
        turn = await llm.submit_tool_results(results)
    final_text = turn.text

AnthropicToolLLM speaks the real Anthropic Messages API. OpenAICompatibleToolLLM
speaks the OpenAI-style chat-completions tool-calling protocol, which covers
both Ollama (local, free, via its OpenAI-compatible endpoint) and Groq
(hosted, free tier) with the same code path.
"""
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMTurn:
    text: Optional[str]
    tool_calls: list  # [{"call_id": str, "name": str, "input": dict}]

    @property
    def is_final(self):
        return not self.tool_calls


class ToolCallingLLM:
    def __init__(self, system_prompt: str, anthropic_tools: list, openai_tools: list):
        self.system_prompt = system_prompt
        self._anthropic_tools = anthropic_tools
        self._openai_tools = openai_tools

    async def start(self, user_message: str) -> LLMTurn:
        raise NotImplementedError

    async def submit_tool_results(self, results: list) -> LLMTurn:
        """results: [(call_id, output_text), ...]"""
        raise NotImplementedError


class AnthropicToolLLM(ToolCallingLLM):
    def __init__(self, system_prompt, anthropic_tools, openai_tools, model="claude-sonnet-4-6", api_key=None):
        super().__init__(system_prompt, anthropic_tools, openai_tools)
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._messages = []

    def _parse(self, response) -> LLMTurn:
        self._messages.append({"role": "assistant", "content": response.content})
        text_parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
        tool_calls = [
            {"call_id": b.id, "name": b.name, "input": b.input}
            for b in response.content if getattr(b, "type", None) == "tool_use"
        ]
        return LLMTurn(text="\n".join(text_parts) or None, tool_calls=tool_calls)

    async def start(self, user_message: str) -> LLMTurn:
        self._messages = [{"role": "user", "content": user_message}]
        resp = self._client.messages.create(
            model=self._model, max_tokens=1024, system=self.system_prompt,
            messages=self._messages, tools=self._anthropic_tools,
        )
        return self._parse(resp)

    async def submit_tool_results(self, results: list) -> LLMTurn:
        content = [{"type": "tool_result", "tool_use_id": cid, "content": out} for cid, out in results]
        self._messages.append({"role": "user", "content": content})
        resp = self._client.messages.create(
            model=self._model, max_tokens=1024, system=self.system_prompt,
            messages=self._messages, tools=self._anthropic_tools,
        )
        return self._parse(resp)


class OpenAICompatibleToolLLM(ToolCallingLLM):
    """Works for Ollama (base_url='http://localhost:11434/v1', api_key can be any
    non-empty string), Groq/OpenRouter/etc (real base_url + real api_key), and a
    client's own agent exposing an OpenAI-compatible endpoint. base_url may also be
    the full .../chat/completions URL. system_prompt=None sends no system message,
    so an agent endpoint keeps its own prompt."""

    def __init__(self, system_prompt, anthropic_tools, openai_tools, base_url, model, api_key="ollama",
                 extra_headers: Optional[dict] = None):
        super().__init__(system_prompt, anthropic_tools, openai_tools)
        base_url = base_url.rstrip("/")
        self._url = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
        self._model = model
        self._api_key = api_key
        self._extra_headers = extra_headers or {}
        self._messages = [{"role": "system", "content": system_prompt}] if system_prompt else []

    def _post(self):
        import urllib.request
        payload = {"model": self._model, "messages": self._messages, "tools": self._openai_tools}
        headers = {"Content-Type": "application/json",
                   # Explicit User-Agent: Groq's Cloudflare front end rejects urllib's default one (error 1010 / HTTP 403).
                   "User-Agent": "finagent-redteam/0.1"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        headers.update(self._extra_headers)
        req = urllib.request.Request(self._url, data=json.dumps(payload).encode(), headers=headers)
        # Free tiers (e.g. Groq) rate-limit per minute; honour Retry-After instead of aborting the run.
        import time
        import urllib.error
        for attempt in range(8):
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as e:
                if e.code != 429 or attempt == 7:
                    raise RuntimeError(f"HTTP {e.code} from {self._url}: {e.read()[:1000]!r}") from e
                time.sleep(float(e.headers.get("retry-after") or 2 ** attempt) + 1)

    def _parse(self, data) -> LLMTurn:
        msg = data["choices"][0]["message"]
        self._messages.append(msg)
        raw_calls = msg.get("tool_calls") or []
        tool_calls = []
        for i, c in enumerate(raw_calls):
            args = c["function"].get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append({"call_id": c.get("id", f"call_{i}"), "name": c["function"]["name"], "input": args})
        return LLMTurn(text=msg.get("content"), tool_calls=tool_calls)

    async def start(self, user_message: str) -> LLMTurn:
        self._messages.append({"role": "user", "content": user_message})
        return self._parse(self._post())

    async def submit_tool_results(self, results: list) -> LLMTurn:
        for call_id, output in results:
            self._messages.append({"role": "tool", "tool_call_id": call_id, "content": output})
        return self._parse(self._post())
