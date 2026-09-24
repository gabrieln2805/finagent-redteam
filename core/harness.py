from dataclasses import dataclass, asdict
from typing import List, Dict, Any
from datetime import datetime, timezone

from core.agents import AgentUnderTest
from core.test_cases import TestCase, build_test_suite
from core.evaluators import evaluate, Verdict


@dataclass
class RunResult:
    agent_name: str
    generated_at: str
    verdicts: List[Verdict]

    def summary(self) -> Dict[str, Any]:
        by_cat: Dict[str, Dict[str, int]] = {}
        for v in self.verdicts:
            by_cat.setdefault(v.category, {"PASS": 0, "FAIL": 0, "WARN": 0})
            by_cat[v.category][v.result] += 1

        total = len(self.verdicts)
        fails = sum(1 for v in self.verdicts if v.result == "FAIL")
        critical_fails = sum(1 for v in self.verdicts if v.result == "FAIL" and v.severity == "critical")
        high_fails = sum(1 for v in self.verdicts if v.result == "FAIL" and v.severity == "high")

        if critical_fails > 0:
            risk_rating = "CRITICAL"
        elif high_fails > 0:
            risk_rating = "HIGH"
        elif fails > 0:
            risk_rating = "MEDIUM"
        else:
            risk_rating = "LOW"

        return {
            "total_tests": total,
            "total_fails": fails,
            "critical_fails": critical_fails,
            "high_fails": high_fails,
            "by_category": by_cat,
            "risk_rating": risk_rating,
        }


class RedTeamHarness:
    def __init__(self, agent: AgentUnderTest, test_suite: List[TestCase] = None):
        self.agent = agent
        self.test_suite = test_suite or build_test_suite()

    def run(self) -> RunResult:
        verdicts = []
        for tc in self.test_suite:
            resp = self.agent.respond(tc.system_prompt, tc.user_message, tc.injected_content)
            verdicts.append(evaluate(tc, resp))
        return RunResult(
            agent_name=self.agent.name,
            generated_at=datetime.now(timezone.utc).isoformat(),
            verdicts=verdicts,
        )
