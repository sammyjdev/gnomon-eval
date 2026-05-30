"""End-to-end slice test (Phase 1 acceptance criterion).

Runs one EvalCase against the MockTarget, through the judge and metrics,
and asserts the report carries a faithfulness MetricResult with a confidence
interval plus cost and latency. This exercises non-negotiables #1, #2, #4
in one flow.
"""

import pytest

from gnomon.config.config import EvalConfig
from gnomon.domain.models import EvalCase, MetricScores, RagResponse
from gnomon.judge.stub import StubJudge
from gnomon.runner.runner import run_eval
from gnomon.targets.mock import MockTarget


class _CountingJudge:
    def __init__(self) -> None:
        self.calls = 0

    def score(self, case: EvalCase, response: RagResponse, *, seed: int, run: int) -> MetricScores:
        self.calls += 1
        return MetricScores(scores={"faithfulness": 0.8})


CASE = EvalCase(
    id="case-1",
    question="Who narrates the world?",
    expected_answer="The game master narrates the world.",
    expected_contexts=["The game master narrates the world to the players."],
)

CASE2 = EvalCase(
    id="case-2",
    question="Who adjudicates the rules?",
    expected_answer="The game master adjudicates the rules.",
    expected_contexts=["The game master adjudicates the rules at the table."],
)


def _target() -> MockTarget:
    return MockTarget(
        answer="The game master narrates the world.",
        contexts=["The game master narrates the world to the players."],
        total_tokens=137,
        latency_ms=512.0,
    )


def test_run_produces_faithfulness_metric_with_confidence_interval():
    cfg = EvalConfig(reproducible=True, seed=42, judge_runs=8)
    report = run_eval([CASE, CASE2], _target(), StubJudge(), cfg)

    faithfulness = report.metric("faithfulness")
    # n is the number of cases the interval is taken over (ADR-008), not runs.
    assert faithfulness.n == 2
    assert faithfulness.confidence_level == 0.95
    assert 0.0 <= faithfulness.ci_low <= faithfulness.mean <= faithfulness.ci_high <= 1.0


def test_run_reports_cost_and_latency_alongside_quality():
    # ADR-004: cost + latency in the same report as quality, never separate.
    cfg = EvalConfig(reproducible=True, seed=42, judge_runs=8)
    report = run_eval([CASE, CASE2], _target(), StubJudge(), cfg)

    assert report.total_tokens == 137 * 2
    assert report.mean_latency_ms == pytest.approx(512.0)
    assert report.per_case_cost[0].case_id == "case-1"
    assert report.per_case_cost[0].total_tokens == 137
    assert report.per_case_cost[0].latency_ms == pytest.approx(512.0)


def test_judge_call_count_is_function_of_cases_and_runs():
    # RNF-06: number of judge calls is an explicit function of dataset size
    # and N of runs, no hidden model calls.
    cfg = EvalConfig(reproducible=True, seed=42, judge_runs=5)
    counting = _CountingJudge()
    run_eval([CASE, CASE2], _target(), counting, cfg)
    assert counting.calls == 2 * 5
