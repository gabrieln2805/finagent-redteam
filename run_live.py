"""
Usage:
    python run_live.py --backend fake                          # sanity-check the plumbing, no API key needed
    python run_live.py --backend anthropic                      # real Claude, needs ANTHROPIC_API_KEY
    python run_live.py --backend ollama --model llama3.1        # real, free, local (needs `ollama serve`)
    python run_live.py --backend groq --model openai/gpt-oss-20b  # real, free tier (needs GROQ_API_KEY)

Testing your own agent:
    python run_live.py --backend groq --system-prompt my_prompt.txt          # your prompt, a stock model
    python run_live.py --backend endpoint --endpoint-url http://localhost:8000/v1   # your agent over HTTP
    python run_live.py --backend python --agent examples/guardrailed_agent.py:make_agent  # your agent in Python

Reads servers_config.json for which local MCP servers to connect to (relative
script paths resolve from the config file's folder), and API keys from a .env
file next to this script if present. Writes live_results.json and a static
HTML report (report_live.html), and exits non-zero if a critical test fails
(see --fail-on).
"""
import argparse
import asyncio
import hashlib
import json
import os
import sys
import webbrowser
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from core.env import load_dotenv
from core.mcp_multi_client import MultiMCPClient
from core.agent_loop import run_agentic_task
from core.live_test_cases import build_live_test_suite, required_servers, LIVE_SYSTEM_PROMPT
from core.live_evaluators import evaluate
from reporting.live_report import generate_live_report

HERE = os.path.dirname(os.path.abspath(__file__))


def load_servers_config(path: str) -> dict:
    """Load servers_config.json, resolving relative script paths against the config's folder,
    expanding ~ and $VARS, and running Python servers with this same interpreter."""
    if not os.path.exists(path):
        raise SystemExit(f"Server config not found: {path}")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    base = os.path.dirname(os.path.abspath(path))

    resolved = {}
    for name, cfg in raw.items():
        command = cfg["command"]
        if command in ("python", "python3"):
            # Guarantees the servers see the same installed packages (mcp) as this process.
            command = sys.executable
        args = []
        for arg in cfg.get("args", []):
            arg = os.path.expanduser(os.path.expandvars(arg))
            if arg.endswith(".py"):
                if not os.path.isabs(arg):
                    arg = os.path.normpath(os.path.join(base, arg))
                if not os.path.exists(arg):
                    raise SystemExit(
                        f"MCP server '{name}': script not found at\n    {arg}\n"
                        f"Fix its path in {path} (relative paths resolve from that file's folder)."
                    )
            args.append(arg)
        resolved[name] = {"command": command, "args": args}
    return resolved


# A server can start fine and still be unusable (e.g. the EU server with no database built),
# which would quietly turn every lookup into an error. One read-only call per server catches that.
HEALTH_CHECKS = {
    "eu-financial-records": ("eu-financial-records__list_ro_regions", {}),
    "financial-ops-mock": ("financial-ops-mock__list_pending_approvals", {}),
}

REQUIRED_KEY_BY_BACKEND = {"anthropic": "ANTHROPIC_API_KEY", "groq": "GROQ_API_KEY"}
DEFAULT_MODELS = {"anthropic": "claude-sonnet-4-6", "ollama": "llama3.1", "groq": "openai/gpt-oss-20b"}


def check_backend_ready(args):
    """Fail fast, before any MCP server is started, if the backend is missing a key, SDK or setting."""
    key = REQUIRED_KEY_BY_BACKEND.get(args.backend)
    if key and not os.environ.get(key):
        raise SystemExit(f"Set {key} (in your shell, or in a .env file next to run_live.py) to use --backend {args.backend}")
    if args.backend == "anthropic":
        try:
            import anthropic  # noqa: F401
        except ImportError:
            raise SystemExit("--backend anthropic needs the SDK: pip install anthropic")
    if args.backend == "endpoint":
        if not args.endpoint_url:
            raise SystemExit("--backend endpoint needs --endpoint-url (your agent's OpenAI-compatible URL)")
        if args.endpoint_key_env and not os.environ.get(args.endpoint_key_env):
            raise SystemExit(f"--endpoint-key-env names {args.endpoint_key_env}, but that variable isn't set")
    if args.backend == "python":
        if not args.agent:
            raise SystemExit("--backend python needs --agent path/to/file.py:make_agent")
        from core.agent_adapters import load_agent_factory
        args.agent_factory = load_agent_factory(args.agent)
    if args.system_prompt and not os.path.exists(args.system_prompt):
        raise SystemExit(f"--system-prompt file not found: {args.system_prompt}")


def resolve_system_prompt(args):
    """Returns (prompt text or None, how the report should describe it)."""
    if args.system_prompt:
        with open(args.system_prompt, encoding="utf-8") as f:
            return f.read().strip(), f"From {os.path.basename(args.system_prompt)}"
    if args.backend in ("endpoint", "python"):
        return None, "The agent's own (the harness sent none)"
    return LIVE_SYSTEM_PROMPT, "Harness default"


def describe_agent(args) -> tuple:
    """(name, connection detail) for the console and the report."""
    model = args.model or DEFAULT_MODELS.get(args.backend)
    if args.backend == "fake":
        name, detail = f"Scripted test agent ({args.persona})", "No model: scripted responses, for checking the setup"
    elif args.backend == "endpoint":
        name, detail = args.endpoint_url, f"OpenAI-compatible endpoint {args.endpoint_url}" + (f" (model: {args.model})" if args.model else "")
    elif args.backend == "python":
        name, detail = args.agent, f"Python adapter {args.agent}"
    else:
        name = f"{args.backend} / {model}"
        detail = {"anthropic": "Anthropic API", "groq": "Groq API (OpenAI-compatible)",
                  "ollama": "Local Ollama server"}[args.backend] + f", model {model}"
    return args.agent_name or name, detail


def parse_headers(raw_headers) -> dict:
    headers = {}
    for h in raw_headers or []:
        if ":" not in h:
            raise SystemExit(f"--endpoint-header must look like 'Name: value', got {h!r}")
        k, _, v = h.partition(":")
        headers[k.strip()] = os.path.expandvars(v.strip())
    return headers


def build_llm(args, tc, system_prompt, anthropic_tools, openai_tools):
    """A fresh agent for each test case, so no conversation state leaks between tests."""
    from core.llm_backends import AnthropicToolLLM, OpenAICompatibleToolLLM
    model = args.model or DEFAULT_MODELS.get(args.backend)
    if args.backend == "fake":
        from core.fake_llm_for_testing import FakeScriptedLLM
        from scripted_fake_agents import get_script_for
        return FakeScriptedLLM(system_prompt, anthropic_tools, openai_tools, get_script_for(tc.id, args.persona))
    if args.backend == "anthropic":
        return AnthropicToolLLM(system_prompt, anthropic_tools, openai_tools, model=model)
    if args.backend == "ollama":
        return OpenAICompatibleToolLLM(system_prompt, anthropic_tools, openai_tools,
                                        base_url="http://localhost:11434/v1", model=model)
    if args.backend == "groq":
        return OpenAICompatibleToolLLM(system_prompt, anthropic_tools, openai_tools,
                                        base_url="https://api.groq.com/openai/v1", model=model,
                                        api_key=os.environ["GROQ_API_KEY"])
    if args.backend == "endpoint":
        return OpenAICompatibleToolLLM(system_prompt, anthropic_tools, openai_tools,
                                        base_url=args.endpoint_url, model=args.model or "agent",
                                        api_key=os.environ.get(args.endpoint_key_env) if args.endpoint_key_env else None,
                                        extra_headers=parse_headers(args.endpoint_header))
    if args.backend == "python":
        from core.agent_adapters import PythonAgentAdapter
        agent = args.agent_factory(system_prompt=system_prompt, openai_tools=openai_tools,
                                   anthropic_tools=anthropic_tools)
        return PythonAgentAdapter(agent)
    raise SystemExit(f"Unknown backend: {args.backend}")


async def main_async(args, system_prompt) -> tuple:
    servers_config = load_servers_config(args.config)
    test_suite = build_live_test_suite()

    # A test whose server isn't configured would still produce a verdict -- just a meaningless one.
    missing = required_servers(test_suite) - set(servers_config)
    if missing:
        raise SystemExit(
            f"{args.config} is missing required MCP server(s): {', '.join(sorted(missing))}.\n"
            f"Every test category needs its server; see servers_config.json in the repo for the expected entries."
        )

    results, problem, servers = [], None, []
    with open(args.server_log, "w", encoding="utf-8") as server_log:
        try:
            async with MultiMCPClient(servers_config, errlog=server_log) as mcp_client:
                servers = sorted(mcp_client.connected_servers)
                # Exiting from inside the MCP client's task group would surface as an
                # exception-group traceback, so report problems only after it has closed.
                problem = await preflight(test_suite, mcp_client)
                if not problem:
                    results, problem = await run_suite(args, test_suite, mcp_client, system_prompt)
        except ConnectionError as e:
            problem = f"{e}\nServer output is in {args.server_log}."
    if problem:
        raise SystemExit(problem)
    return results, servers


async def preflight(test_suite, mcp_client):
    """Return a description of the first problem that would make results meaningless, or None."""
    for server in sorted(mcp_client.connected_servers):
        n_tools = sum(1 for t in mcp_client.tools if t.server == server)
        print(f"Connected: {server} ({n_tools} tools)")
    empty = required_servers(test_suite) - {t.server for t in mcp_client.tools}
    if empty:
        return f"Required MCP server(s) connected but exposed no tools: {', '.join(sorted(empty))}"
    for server in sorted(required_servers(test_suite)):
        tool, tool_input = HEALTH_CHECKS[server]
        error = await mcp_client.health_check(tool, tool_input)
        if error:
            return f"MCP server '{server}' started but isn't working -- {tool} failed:\n    {error}"
    return None


async def run_suite(args, test_suite, mcp_client, system_prompt) -> tuple:
    anthropic_tools = mcp_client.as_anthropic_tools()
    openai_tools = mcp_client.as_openai_tools()

    print(f"Running {len(test_suite)} tests against {describe_agent(args)[0]}...\n")

    results = []
    for tc in test_suite:
        try:
            llm = build_llm(args, tc, system_prompt, anthropic_tools, openai_tools)
            run = await run_agentic_task(llm, mcp_client, tc.user_message, max_turns=args.max_turns)
        except Exception as e:
            # Usually the agent is unreachable or returned something malformed; either way the
            # remaining tests would fail the same way, so stop with the reason instead of a traceback.
            return results, f"The agent failed during {tc.id}: {type(e).__name__}: {e}"
        verdict = evaluate(tc, run)
        results.append((tc, run, verdict))
        print(f"[{verdict.result:4s}] {tc.id:12s} {verdict.rationale}")
    return results, None


def print_summary(results):
    rows = [(tc.id, tc.category, v.severity, v.result) for tc, _, v in results]
    headers = ("Test", "Category", "Severity", "Result")
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    line = "  ".join("{:<%d}" % w for w in widths)
    print("\n" + line.format(*headers))
    print(line.format(*("-" * w for w in widths)))
    for r in rows:
        print(line.format(*r))

    counts = {k: sum(1 for r in rows if r[3] == k) for k in ("PASS", "WARN", "FAIL")}
    critical_fails = sum(1 for _, _, v in results if v.result == "FAIL" and v.severity == "critical")
    print(f"\n{len(rows)} tests: {counts['PASS']} passed, {counts['WARN']} warned, "
          f"{counts['FAIL']} failed ({critical_fails} critical)")


def write_json(results, run_info, path):
    out = {
        "run": {**run_info, "generated_at": run_info["generated_at"].isoformat()},
        "results": [
            {"test_id": tc.id, "category": tc.category, "description": tc.description,
             "user_message": tc.user_message, "final_text": run.final_text,
             "tool_calls": [asdict(t) for t in run.tool_calls], "hit_max_turns": run.hit_max_turns,
             "verdict": asdict(v)}
            for tc, run, v in results
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str, ensure_ascii=False)


def exit_code(results, fail_on: str) -> int:
    if fail_on == "never":
        return 0
    if fail_on == "any":
        return int(any(v.result == "FAIL" for _, _, v in results))
    return int(any(v.result == "FAIL" and v.severity == "critical" for _, _, v in results))


def main():
    load_dotenv(os.path.join(HERE, ".env"))

    parser = argparse.ArgumentParser(description="Red-team a tool-calling LLM agent against real MCP servers.")
    parser.add_argument("--backend", choices=["fake", "anthropic", "ollama", "groq", "endpoint", "python"], default="fake",
                         help="fake: scripted setup check; anthropic/ollama/groq: a bare model; "
                              "endpoint/python: your own agent")
    parser.add_argument("--persona", choices=["hardened", "vulnerable"], default="hardened",
                         help="Only used with --backend fake")
    parser.add_argument("--model", default=None, help="Model name (for endpoint: the 'model' field sent to your agent)")

    agent = parser.add_argument_group("testing your own agent")
    agent.add_argument("--system-prompt", metavar="FILE",
                        help="Use this system prompt instead of the harness default (or of your agent's own)")
    agent.add_argument("--endpoint-url", help="--backend endpoint: your agent's OpenAI-compatible base URL "
                                               "or full .../chat/completions URL")
    agent.add_argument("--endpoint-key-env", metavar="VAR",
                        help="--backend endpoint: environment variable holding a bearer token for your agent")
    agent.add_argument("--endpoint-header", action="append", metavar="'NAME: VALUE'",
                        help="--backend endpoint: extra HTTP header, repeatable ($VARS are expanded)")
    agent.add_argument("--agent", metavar="FILE.py:FACTORY",
                        help="--backend python: your agent factory, e.g. examples/guardrailed_agent.py:make_agent")
    agent.add_argument("--agent-name", help="Name shown in the report (defaults to the model, URL or adapter)")

    parser.add_argument("--config", default=os.path.join(HERE, "servers_config.json"))
    parser.add_argument("--max-turns", type=int, default=6)
    parser.add_argument("--out", default="live_results.json", help="Full transcripts and verdicts (JSON)")
    parser.add_argument("--out-html", default="report_live.html", help="Static HTML report")
    parser.add_argument("--no-html", action="store_true", help="Skip the HTML report")
    parser.add_argument("--no-open", action="store_true", help="Don't open the HTML report in a browser")
    parser.add_argument("--server-log", default="mcp_servers.log", help="Where the MCP servers' own logs go")
    parser.add_argument("--fail-on", choices=["critical", "any", "never"], default="critical",
                         help="Exit with code 1 on a critical FAIL (default), on any FAIL, or never")
    args = parser.parse_args()

    check_backend_ready(args)
    system_prompt, prompt_source = resolve_system_prompt(args)
    results, servers = asyncio.run(main_async(args, system_prompt))
    print_summary(results)

    agent_name, agent_detail = describe_agent(args)
    run_info = {
        "agent": agent_name, "agent_detail": agent_detail, "backend": args.backend,
        "system_prompt_source": prompt_source, "system_prompt": system_prompt,
        "system_prompt_sha256": hashlib.sha256(system_prompt.encode()).hexdigest() if system_prompt else None,
        "servers": servers, "max_turns": args.max_turns, "generated_at": datetime.now(timezone.utc),
    }
    write_json(results, run_info, args.out)
    print(f"\nWrote {args.out}")
    if not args.no_html:
        with open(args.out_html, "w", encoding="utf-8") as f:
            f.write(generate_live_report(results, run_info))
        print(f"Wrote {args.out_html}")
        if not args.no_open:
            webbrowser.open(Path(args.out_html).resolve().as_uri())

    sys.exit(exit_code(results, args.fail_on))


if __name__ == "__main__":
    main()
