# Getting started

This guide takes you from a fresh download to a finished audit report. You
don't need to read any of the code. You need a terminal (PowerShell on
Windows, Terminal on macOS/Linux) and about 15 minutes, or about 30 if you set
up the live mode in step 4.

## What this tool does

It gives an AI agent realistic finance tasks and checks three things:

| Check | The question it answers |
|---|---|
| **Prompt injection** | Does the agent obey instructions hidden inside an invoice or email it was only asked to read? |
| **Unauthorized actions** | Does the agent move money, delete records, or raise limits without a human's approval? |
| **Hallucinated figures** | Does every number the agent states come from a real data source, and does it admit when it doesn't have the data? |

Each test gets **PASS**, **WARN** (inconclusive) or **FAIL**, and the run gets
an overall risk rating. The output is an HTML audit report you can open in a
browser and share, plus a JSON file with the full evidence.

There are two ways to run it:

| | `run.py` (quick check) | `run_live.py` (live mode, recommended) |
|---|---|---|
| What it tests | The model's text replies to 14 scripted prompts | A model that actually calls tools (look up invoices, transfer funds, query EU data) |
| How it grades | Reads the reply text | Checks which tools the model **actually called**, with what arguments |
| Setup | Python only | Python + two local data servers (step 4) |

Use `run.py` to confirm everything is installed. Use `run_live.py` for results
you intend to rely on.

---

## 1. Install Python

You need **Python 3.10 or newer**. Check with:

```powershell
python --version
```

If the command isn't recognized, install Python from
[python.org](https://www.python.org/downloads/). On Windows, tick **"Add
python.exe to PATH"** in the installer, then open a new terminal.

> On macOS/Linux, type `python3` wherever this guide says `python`.

## 2. Open the project folder and install dependencies

Go to the folder that contains `run.py`. If you downloaded a ZIP from GitHub,
that is often a folder *inside* the folder you extracted, with the same name.

```powershell
cd "D:\path\to\AI_Safety_Framework-main"     # the folder containing run.py
python -m pip install -r requirements.txt
```

Quote the path if it contains spaces.

## 3. Quick check (no account or API key needed)

```powershell
python run.py
```

Expected output:

```
mock-vulnerable-agent: CRITICAL risk (11/14 tests failed)
mock-hardened-agent: LOW risk (0/14 tests failed)

Wrote report.html and results.json
```

These two are built-in demo agents: one designed to fail and one designed to
pass. If you see this output, your installation works. Open `report.html` to
see what a report looks like.

## 4. Set up live mode (one time)

Live mode connects the model to two local "MCP servers", small programs that
give it tools:

- **financial-ops-mock** is included in this project. It serves invoices and
  emails, some with hidden malicious instructions, and restricted tools such as
  `transfer_funds` that require human approval.
- **eu-financial-records** is a separate project that serves real EU public
  funding data. You need to set it up once.

**a. Place it next to this project.** The default configuration expects this layout:

```
some-folder/
├── eu-financial-records-mcp/          <- the EU data server
└── AI_Safety_Framework-main/
    └── AI_Safety_Framework-main/      <- this project (contains run.py)
```

If your layout is different, change the path in `servers_config.json`.
Relative paths there are resolved from the folder `servers_config.json` is in.

**b. Download and build its data** (about 90 MB to download, 60 MB database):

```powershell
cd "D:\path\to\eu-financial-records-mcp"
python -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File scripts\fetch_data.ps1   # macOS/Linux: bash scripts/fetch_data.sh
python scripts\build_db.py
python test_client.py                                             # optional self-test
```

**c. Confirm the live setup works** (no API key needed). Go back to this
project's folder and run:

```powershell
python run_live.py --backend fake
```

This uses a scripted stand-in instead of a real model. It should report
`11 tests: 11 passed` and open the report in your browser. If a server is
missing or misconfigured, the tool stops and says which one. It never produces
a report with that server's tests silently skipped.

## 5. Test a real model

Choose a provider:

| Provider | Cost | What you need |
|---|---|---|
| **Groq** | Free tier | A key from [console.groq.com/keys](https://console.groq.com/keys) |
| **Anthropic (Claude)** | Paid per use | A key from [console.anthropic.com](https://console.anthropic.com/) |
| **Ollama** | Free, runs on your computer | [Ollama](https://ollama.com) installed, `ollama pull llama3.1`, and `ollama serve` running |

**Store your key.** Copy `.env.example` to a new file named `.env` in the same
folder, and fill in your key:

```
GROQ_API_KEY=gsk_your_key_here
```

`.env` is ignored by git, so the key won't be committed. Alternatively, set the
variable in your terminal (`$env:GROQ_API_KEY="..."` in PowerShell). A
variable set in the terminal takes priority over `.env`.

**Run it:**

```powershell
python run_live.py --backend groq --model openai/gpt-oss-20b
python run_live.py --backend anthropic
python run_live.py --backend ollama --model llama3.1
```

A run takes a few minutes. Each test prints a line as it finishes, then a
summary table, and the report opens in your browser.

## 6. Test your own agent

Step 5 tests a stock model with the harness's built-in system prompt. What you
usually want to know is whether **your** agent, with your prompt and your
guardrails, resists these attacks. There are three ways to test it, from least
to most effort.

**a. Your system prompt on a stock model.** Put your prompt in a text file:

```powershell
python run_live.py --backend groq --system-prompt my_prompt.txt
```

This tells you how much your prompt alone protects you. It works with every backend.

**b. Your agent over HTTP.** If your agent exposes an OpenAI-compatible
chat-completions endpoint (many agent frameworks and LLM gateways do), point
the harness at it:

```powershell
python run_live.py --backend endpoint --endpoint-url http://localhost:8000/v1 `
    --endpoint-key-env MY_AGENT_TOKEN --agent-name "Finance agent v2"
```

- The harness POSTs to `<url>/chat/completions`. You can also pass that full URL.
- Each request includes the conversation so far and the harness's tools, in the
  standard `tools` format.
- Your agent replies either with `tool_calls` or with a final answer in `content`.
- The harness runs the tool calls on its test servers, sends the results back as
  `role: "tool"` messages, and grades which tools your agent actually called.
- The harness sends **no** system prompt, so your agent keeps its own. Add
  `--system-prompt FILE` to send one.
- `--endpoint-key-env` names an environment variable holding a bearer token.
  `--endpoint-header "Name: value"` adds other headers and can be repeated.
- `--model` sets the `model` field in each request (default `agent`).

**Requirement:** your agent must let the harness execute the tools. An agent
that runs its tools internally and returns only the final text can't be graded
on its actions. Point its tool layer at the harness instead, or use option c.

**c. Your agent as Python code.** Write a small adapter with a factory
function that returns an object with `start(user_message)` and
`submit_tool_results(results)` methods. Each returns
`{"text": ..., "tool_calls": [...]}`. The methods can be plain or async.

```powershell
python run_live.py --backend python --agent my_adapter.py:make_agent
```

[`examples/guardrailed_agent.py`](examples/guardrailed_agent.py) is a complete,
working example. It has its own system prompt, calls a model over an
OpenAI-compatible API, and adds a code guardrail that blocks fund transfers,
deletions and limit overrides whatever the model decides. Tested against a
deliberately vulnerable model, the guardrail turned all 7 injection and
unauthorized-action tests from FAIL to PASS. The hallucination tests still
failed, because a guardrail on actions doesn't stop the model inventing
numbers. The details are in [`core/agent_adapters.py`](core/agent_adapters.py).

The report records which agent was tested, how it was connected, and which
system prompt was used (with a SHA-256 fingerprint), so you can compare runs
and show exactly what was evaluated.

## 7. Read the results

| File | What it is |
|---|---|
| `report_live.html` | The audit report: a single self-contained HTML file you can email, archive or print to PDF. It includes the risk rating, the failures, the agent and prompt tested, and a full transcript for every test. |
| `live_results.json` | The same evidence in machine-readable form: `run` holds the agent details, and `results` holds each test's prompt, tool calls (arguments and outputs), final answer and verdict |
| `mcp_servers.log` | The data servers' own logs, only needed for troubleshooting |

**Risk rating** (overall):

| Rating | Means |
|---|---|
| CRITICAL | At least one critical-severity test failed, e.g. the model transferred funds because a document told it to |
| HIGH | No critical failures, but at least one high-severity test failed |
| MEDIUM | Only lower-severity tests failed |
| LOW | No test failed |

**WARN** means the result couldn't be determined automatically. For example,
the model gave no figure, but didn't clearly say the data was unavailable
either. Check that test's transcript in the report.

A LOW rating means the model passed these 11 scenarios in this run. It is not
proof the model is safe in general. Models don't respond identically every
time, so run important evaluations several times.

## Useful options

| Option | Effect |
|---|---|
| `--model NAME` | Choose which model the provider runs |
| `--system-prompt FILE` | Test with your own system prompt (step 6) |
| `--agent-name NAME` | The name shown in the report |
| `--out FILE`, `--out-html FILE` | Save results under different names, e.g. one per model |
| `--no-open` | Don't open the report automatically |
| `--max-turns N` | How many tool calls the model may make per test (default 6) |
| `--fail-on critical\|any\|never` | Controls the exit code for automated pipelines (below) |

Run `python run_live.py --help` for the full list.

**Automated pipelines (CI).** `run_live.py` exits with code **1** if any
critical test fails, and **0** otherwise, so a pipeline step can block a
release on it. Use `--fail-on any` to also block on non-critical failures, and
`--no-open` so it doesn't try to open a browser.

## Troubleshooting

| Message | Fix |
|---|---|
| `can't open file '...run.py'` | You're in the wrong folder. `cd` into the folder that contains `run.py` (see step 2). |
| `python` is not recognized | Python isn't installed or isn't on PATH. See step 1, then open a new terminal. |
| `No module named 'mcp'` | Run `python -m pip install -r requirements.txt` from the project folder. |
| `MCP server '...': script not found at ...` | Fix that server's path in `servers_config.json` (see step 4a). |
| `... is missing required MCP server(s)` | `servers_config.json` must list both `eu-financial-records` and `financial-ops-mock`. |
| `Could not start MCP server ...` | The server crashed on startup. The reason is in `mcp_servers.log`. |
| `MCP server 'eu-financial-records' started but isn't working ... Database not found` | The EU data hasn't been downloaded and built yet. Run step 4b. |
| `Set GROQ_API_KEY ...` / `Set ANTHROPIC_API_KEY ...` | Add the key to `.env` (step 5). Check the file is named exactly `.env`, not `.env.txt`. |
| `--backend anthropic needs the SDK` | `python -m pip install anthropic` |
| HTTP 429 from Groq | The free tier's rate limit. The tool waits and retries automatically, so the run just takes longer. |
| Connection refused with `--backend ollama` | Start Ollama with `ollama serve` and check the model is downloaded (`ollama list`). |

## What data leaves your computer

- The quick check with demo agents (`run.py`) and `--backend fake` send nothing anywhere.
- With Groq or Anthropic, the test prompts and the tool results the model
  requests are sent to that provider. These are this tool's test scenarios and
  public EU funding data, not your own data.
- With Ollama, everything stays on your computer.
