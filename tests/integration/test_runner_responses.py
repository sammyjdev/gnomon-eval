"""Integration tests for response recording in run_eval and run_panel_eval (issue #71)."""

import json

from gnomon.config.config import EvalConfig
from gnomon.domain.models import EvalCase, RagResponse
from gnomon.judge.stub import StubJudge
from gnomon.reporting.panel_report import panel_to_dict
from gnomon.reporting.report import to_dict
from gnomon.runner.panel_runner import PanelMember, run_panel_eval
from gnomon.runner.runner import run_eval


class _PerQuestionTarget:
    """Returns a different response per question, so order and content are provable."""

    def __init__(self, by_question: dict[str, RagResponse]) -> None:
        self._by_question = by_question

    def query(self, question: str) -> RagResponse:
        return self._by_question[question]


CASES = [
    EvalCase(id="case-b", question="q-b", expected_answer="x", expected_contexts=["x"]),
    EvalCase(id="case-a", question="q-a", expected_answer="x", expected_contexts=["x"]),
    EvalCase(id="case-c", question="q-c", expected_answer="x", expected_contexts=["x"]),
]
BY_QUESTION = {
    "q-b": RagResponse(
        answer="answer-b", contexts=["ctx-b1", "ctx-b2"], total_tokens=11, latency_ms=1.0
    ),
    "q-a": RagResponse(answer="answer-a", contexts=["ctx-a1"], total_tokens=22, latency_ms=2.0),
    "q-c": RagResponse(answer="answer-c", contexts=[], total_tokens=33, latency_ms=3.0),
}
EXPECTED = [
    {"case_id": "case-b", "answer": "answer-b", "contexts": ["ctx-b1", "ctx-b2"]},
    {"case_id": "case-a", "answer": "answer-a", "contexts": ["ctx-a1"]},
    {"case_id": "case-c", "answer": "answer-c", "contexts": []},
]
CONFIG = EvalConfig(reproducible=True, seed=42, judge_runs=2)


def test_run_eval_report_carries_target_responses_in_case_order() -> None:
    payload = json.loads(
        json.dumps(to_dict(run_eval(CASES, _PerQuestionTarget(BY_QUESTION), StubJudge(), CONFIG)))
    )
    assert payload["responses"] == EXPECTED
    assert [r["case_id"] for r in payload["responses"]] == [
        c["case_id"] for c in payload["per_case"]
    ]


def test_run_panel_eval_report_carries_target_responses_once_per_case() -> None:
    members = [
        PanelMember("judge-a", "vendor-a", StubJudge(base=0.9, jitter=0.0)),
        PanelMember("judge-b", "vendor-b", StubJudge(base=0.5, jitter=0.0)),
    ]
    payload = json.loads(
        json.dumps(
            panel_to_dict(run_panel_eval(CASES, _PerQuestionTarget(BY_QUESTION), members, CONFIG))
        )
    )
    assert payload["responses"] == EXPECTED
