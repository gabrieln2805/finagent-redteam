"""
Re-render a saved run_live.py results file as the static HTML report, with no
new model calls. Verdicts are shown as recorded in the file.

    python scripts/render_report.py live_results.json report.html

Files written before run details were recorded (a bare JSON list) need the
agent described on the command line:

    python scripts/render_report.py live_results_groq_gpt-oss-20b.json docs/example_report.html \
        --agent "groq / openai/gpt-oss-20b" --detail "Groq API (OpenAI-compatible), model openai/gpt-oss-20b" \
        --note "Re-rendered from the saved transcripts of a live run on 2026-09-24."
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent_loop import AgentRunResult, ToolCallRecord  # noqa: E402
from core.live_evaluators import LiveVerdict  # noqa: E402
from core.live_test_cases import LIVE_SYSTEM_PROMPT, LiveTestCase, build_live_test_suite  # noqa: E402
from reporting.live_report import generate_live_report  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results_json")
    parser.add_argument("out_html")
    parser.add_argument("--agent", help="Agent name (required for legacy list-format files)")
    parser.add_argument("--detail", default="", help="How the agent was connected (legacy files)")
    parser.add_argument("--note", help="Extra line under the report title")
    args = parser.parse_args()

    with open(args.results_json, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        if not args.agent:
            raise SystemExit("This is a legacy results file with no run details; pass --agent (and ideally --detail)")
        rows = data
        # Legacy runs always used the harness default prompt and both standard servers.
        run_info = {"agent": args.agent, "agent_detail": args.detail, "system_prompt_source": "Harness default",
                    "system_prompt": LIVE_SYSTEM_PROMPT,
                    "system_prompt_sha256": hashlib.sha256(LIVE_SYSTEM_PROMPT.encode()).hexdigest(),
                    "servers": ["eu-financial-records", "financial-ops-mock"], "max_turns": 6}
    else:
        rows = data["results"]
        run_info = dict(data["run"])
        if args.agent:
            run_info["agent"] = args.agent
        if args.detail:
            run_info["agent_detail"] = args.detail
    run_info["generated_at"] = datetime.now(timezone.utc)
    if args.note:
        run_info["note"] = args.note

    known = {tc.id: tc for tc in build_live_test_suite()}
    results = []
    for r in rows:
        tc = known.get(r["test_id"]) or LiveTestCase(id=r["test_id"], category=r["category"],
                                                     description=r["description"], user_message=r["user_message"])
        run = AgentRunResult(final_text=r["final_text"], tool_calls=[ToolCallRecord(**t) for t in r["tool_calls"]],
                             hit_max_turns=r["hit_max_turns"])
        results.append((tc, run, LiveVerdict(**r["verdict"])))

    with open(args.out_html, "w", encoding="utf-8") as f:
        f.write(generate_live_report(results, run_info))
    print(f"Wrote {args.out_html}")


if __name__ == "__main__":
    main()
