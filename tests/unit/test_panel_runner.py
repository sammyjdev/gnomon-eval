"""Panel runner tests (ADR-0012)."""

import pytest

from gnomon.config.config import EvalConfig
from gnomon.domain.models import EvalCase
from gnomon.judge.stub import StubJudge
from gnomon.metrics.names import V1_METRICS
from gnomon.runner.panel_runner import PanelMember, run_panel_eval
from gnomon.targets.mock import MockTarget

CASES = [
    EvalCase(
        id="case-1",
        question="Who narrates?",
        expected_answer="The GM.",
        expected_contexts=["The GM narrates."],
    ),
    EvalCase(
        id="case-2",
        question="Who adjudicates?",
        expected_answer="The GM.",
        expected_contexts=["The GM adjudicates."],
    ),
]


def _target():
    return MockTarget(
        answer="The GM.", contexts=["The GM narrates."], total_tokens=100, latency_ms=20.0
    )


def test_panel_runner_reports_each_judge_independently():
    members = [
        PanelMember("judge-a", "vendor-a", StubJudge(base=0.9, jitter=0.0)),
        PanelMember("judge-b", "vendor-b", StubJudge(base=0.5, jitter=0.0)),
    ]
    report = run_panel_eval(
        CASES,
        _target(),
        members,
        EvalConfig(reproducible=True, seed=42, judge_runs=2),
    )
    assert len(report.judge_reports) == len(members)
    assert report.judge("judge-a").metric("faithfulness").mean == pytest.approx(0.9)
    assert report.judge("judge-b").metric("faithfulness").mean == pytest.approx(0.5)
    assert [stat.metric for stat in report.disagreement] == list(V1_METRICS)


class _CountingTarget:
    def __init__(self, inner):
        self.inner = inner
        self.calls = 0

    def query(self, question):
        self.calls += 1
        return self.inner.query(question)


def test_panel_runner_queries_target_once_per_case():
    target = _CountingTarget(_target())
    members = [
        PanelMember("judge-a", "vendor-a", StubJudge(base=0.9, jitter=0.0)),
        PanelMember("judge-b", "vendor-b", StubJudge(base=0.7, jitter=0.0)),
        PanelMember("judge-c", "vendor-c", StubJudge(base=0.5, jitter=0.0)),
    ]
    run_panel_eval(
        CASES,
        target,
        members,
        EvalConfig(reproducible=True, seed=42, judge_runs=2),
    )
    assert target.calls == len(CASES)


def test_panel_runner_denoises_runs_within_each_case():
    judge = StubJudge(base=0.7, jitter=0.2)
    config = EvalConfig(reproducible=True, seed=42, judge_runs=4)
    report = run_panel_eval(
        CASES,
        _target(),
        [PanelMember("judge-a", "vendor-a", judge)],
        config,
    )
    response = _target().query(CASES[0].question)
    for case, case_score in zip(
        CASES,
        report.judge("judge-a").case_scores["faithfulness"],
        strict=True,
    ):
        expected = (
            sum(
                judge.score(case, response, seed=config.seed, run=run).scores["faithfulness"]
                for run in range(config.judge_runs)
            )
            / config.judge_runs
        )
        assert case_score.score == pytest.approx(expected)
