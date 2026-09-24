"""
Usage:
    python run.py                        # runs the two mock agents only (no key/network needed)
    python run.py --anthropic            # + a real Claude agent via the Anthropic API
                                          #   (requires ANTHROPIC_API_KEY)
    python run.py --ollama --ollama-model llama3.1
                                          # + a real, fully free local model via Ollama
                                          #   (requires `ollama serve` running locally)
    python run.py --groq --groq-model openai/gpt-oss-20b
                                          # + a real model via Groq's free tier
                                          #   (requires GROQ_API_KEY)

Writes: report.html, results.json into the current directory. API keys can go in a .env file.
"""
import os
import sys
import json
import argparse
from dataclasses import asdict

from core.agents import (
    MockVulnerableAgent, MockHardenedAgent, AnthropicAgent, OllamaAgent, OpenAICompatibleAgent,
)
from core.env import load_dotenv
from core.harness import RedTeamHarness
from reporting.report import generate_html_report


def main():
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

    parser = argparse.ArgumentParser()
    parser.add_argument("--anthropic", action="store_true", help="also test a real Claude agent via the Anthropic API")
    parser.add_argument("--ollama", action="store_true", help="also test a real local model via Ollama (free)")
    parser.add_argument("--ollama-model", default="llama3.1")
    parser.add_argument("--groq", action="store_true", help="also test a real model via Groq's free tier")
    parser.add_argument("--groq-model", default="openai/gpt-oss-20b")
    parser.add_argument("--out-html", default="report.html")
    parser.add_argument("--out-json", default="results.json")
    args = parser.parse_args()

    agents = [MockVulnerableAgent(), MockHardenedAgent()]

    if args.anthropic:
        try:
            agents.append(AnthropicAgent())
        except Exception as e:
            print(f"[warn] skipping Anthropic agent: {e}", file=sys.stderr)

    if args.ollama:
        try:
            agents.append(OllamaAgent(model=args.ollama_model))
        except Exception as e:
            print(f"[warn] skipping Ollama agent: {e}", file=sys.stderr)

    if args.groq:
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            print("[warn] skipping Groq agent: set GROQ_API_KEY", file=sys.stderr)
        else:
            try:
                agents.append(OpenAICompatibleAgent(
                    base_url="https://api.groq.com/openai/v1",
                    model=args.groq_model, api_key=key, name=f"groq-{args.groq_model}",
                ))
            except Exception as e:
                print(f"[warn] skipping Groq agent: {e}", file=sys.stderr)

    results = []
    for agent in agents:
        harness = RedTeamHarness(agent)
        run_result = harness.run()
        results.append(run_result)
        s = run_result.summary()
        print(f"{agent.name}: {s['risk_rating']} risk "
              f"({s['total_fails']}/{s['total_tests']} tests failed)")

    html_report = generate_html_report(results)
    with open(args.out_html, "w", encoding="utf-8") as f:
        f.write(html_report)

    json_out = [
        {
            "agent_name": r.agent_name,
            "generated_at": r.generated_at,
            "summary": r.summary(),
            "verdicts": [asdict(v) for v in r.verdicts],
        }
        for r in results
    ]
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(json_out, f, indent=2)

    print(f"\nWrote {args.out_html} and {args.out_json}")


if __name__ == "__main__":
    main()
