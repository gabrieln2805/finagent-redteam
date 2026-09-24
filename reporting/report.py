import html
from typing import Dict, List, Optional
from core.harness import RunResult
from core.test_cases import build_test_suite

_CASE_DESCRIPTIONS = {tc.id: tc.description for tc in build_test_suite()}

_BADGE = {"PASS": "#1a7f37", "FAIL": "#cf222e", "WARN": "#9a6700"}
_SEV_COLOR = {"low": "#57606a", "medium": "#9a6700", "high": "#cf222e", "critical": "#82071e"}
_CATEGORY_LABEL = {
    "injection": "Prompt Injection Resistance",
    "unauthorized_action": "Unauthorized Action Attempts",
    "hallucination": "Hallucinated Financial Figures",
}


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def generate_html_report(results: List[RunResult], descriptions: Optional[Dict[str, str]] = None,
                         subtitle: str = "automatically generated") -> str:
    descriptions = descriptions if descriptions is not None else _CASE_DESCRIPTIONS
    rows_all = []
    for r in results:
        s = r.summary()
        rows_all.append((r, s))

    agent_cards = ""
    for r, s in rows_all:
        cat_html = ""
        for cat, counts in s["by_category"].items():
            cat_html += f"""
            <div class="cat-row">
              <span class="cat-name">{_CATEGORY_LABEL.get(cat, cat)}</span>
              <span class="pill pass">{counts['PASS']} pass</span>
              <span class="pill warn">{counts['WARN']} warn</span>
              <span class="pill fail">{counts['FAIL']} fail</span>
            </div>"""

        agent_cards += f"""
        <div class="agent-card">
          <div class="agent-header">
            <h3>{_esc(r.agent_name)}</h3>
            <span class="risk-badge risk-{s['risk_rating'].lower()}">{s['risk_rating']} RISK</span>
          </div>
          <p class="muted">{s['total_tests']} tests run &middot; {s['total_fails']} failed
             ({s['critical_fails']} critical, {s['high_fails']} high severity)</p>
          {cat_html}
        </div>"""

    detail_sections = ""
    for r, s in rows_all:
        rows = ""
        for v in r.verdicts:
            desc = descriptions.get(v.test_id, "")
            rows += f"""
            <tr>
              <td><code>{_esc(v.test_id)}</code></td>
              <td>{_esc(_CATEGORY_LABEL.get(v.category, v.category))}</td>
              <td>{_esc(desc)}</td>
              <td><span class="sev sev-{v.severity}">{v.severity.upper()}</span></td>
              <td><span class="badge badge-{v.result.lower()}">{v.result}</span></td>
              <td class="rationale">{_esc(v.rationale)}</td>
              <td class="evidence">{_esc(v.evidence)}</td>
            </tr>"""
        detail_sections += f"""
        <h3 class="detail-header">{_esc(r.agent_name)} &mdash; full transcript-level findings</h3>
        <table class="detail-table">
          <thead><tr><th>ID</th><th>Category</th><th>Test</th><th>Severity</th><th>Result</th>
          <th>Rationale</th><th>Response excerpt</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Agent Red-Team Audit Report</title>
<style>
  :root {{
    --bg: #ffffff; --fg: #1b1f24; --muted: #57606a; --border: #d0d7de;
    --card-bg: #f6f8fa;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
    color: var(--fg); background: var(--bg); margin: 0; padding: 40px 24px;
    max-width: 1080px; margin-left: auto; margin-right: auto; line-height: 1.5;
  }}
  h1 {{ font-size: 1.6rem; margin-bottom: 4px; }}
  h2 {{ font-size: 1.15rem; margin-top: 40px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }}
  .muted {{ color: var(--muted); font-size: 0.92rem; }}
  .meta {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 24px; }}
  .agent-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }}
  .agent-card {{
    border: 1px solid var(--border); border-radius: 10px; padding: 16px 18px; background: var(--card-bg);
  }}
  .agent-header {{ display: flex; align-items: center; justify-content: space-between; }}
  .agent-header h3 {{ margin: 0; font-size: 1rem; }}
  .risk-badge {{ font-size: 0.72rem; font-weight: 700; padding: 3px 9px; border-radius: 999px; color: white; }}
  .risk-low {{ background: #1a7f37; }}
  .risk-medium {{ background: #9a6700; }}
  .risk-high {{ background: #cf222e; }}
  .risk-critical {{ background: #82071e; }}
  .cat-row {{ display: flex; align-items: center; gap: 8px; margin-top: 8px; font-size: 0.85rem; }}
  .cat-name {{ flex: 1; }}
  .pill {{ font-size: 0.72rem; font-weight: 600; padding: 2px 8px; border-radius: 999px; }}
  .pill.pass {{ background: #d4f4dd; color: #1a7f37; }}
  .pill.warn {{ background: #fff1c2; color: #9a6700; }}
  .pill.fail {{ background: #ffd7d5; color: #cf222e; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 12px; font-size: 0.83rem; }}
  th, td {{ border: 1px solid var(--border); padding: 8px 10px; text-align: left; vertical-align: top; }}
  th {{ background: var(--card-bg); }}
  code {{ background: #eef1f4; padding: 1px 5px; border-radius: 4px; }}
  .badge {{ font-weight: 700; padding: 2px 8px; border-radius: 6px; font-size: 0.78rem; color: white; }}
  .badge-pass {{ background: #1a7f37; }}
  .badge-warn {{ background: #9a6700; }}
  .badge-fail {{ background: #cf222e; }}
  .sev {{ font-weight: 700; font-size: 0.72rem; }}
  .sev-low {{ color: #57606a; }}
  .sev-medium {{ color: #9a6700; }}
  .sev-high {{ color: #cf222e; }}
  .sev-critical {{ color: #82071e; }}
  .rationale {{ max-width: 260px; }}
  .evidence {{ max-width: 260px; white-space: pre-wrap; overflow-wrap: anywhere; font-family: ui-monospace, monospace; font-size: 0.76rem; color: var(--muted); }}
  .detail-header {{ margin-top: 32px; }}
  .methodology {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: 16px 18px; }}
</style>
</head>
<body>
  <h1>Agent Red-Team Audit Report</h1>
  <div class="meta">Financial AI Agent Safety Harness &middot; {_esc(subtitle)}</div>

  <div class="methodology">
    <strong>Methodology.</strong> Each agent under test was run against a fixed suite of
    adversarial and control test cases across three risk categories regulated financial
    firms commonly audit for: (1) resistance to instructions embedded in observed content
    ("prompt injection"), (2) whether restricted actions (fund transfers, limit overrides,
    record deletion) require explicit human confirmation before execution, and
    (3) whether numeric financial figures are grounded in a system of record rather than
    fabricated. Every test was graded automatically against the agent's actual response
    text and any tool calls it attempted, using rule-based evaluators, not self-report.
  </div>

  <h2>Executive Summary</h2>
  <div class="agent-grid">
    {agent_cards}
  </div>

  <h2>Detailed Findings</h2>
  {detail_sections}

</body>
</html>"""
