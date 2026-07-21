"""Panel domain model tests (ADR-0012)."""

import pytest
from pydantic import ValidationError

from gnomon.domain.models import (
    CaseCost,
    DisagreementStat,
    MetricResult,
    PanelJudgeReport,
    PanelReport,
)

METRIC = MetricResult(
    metric="faithfulness",
    mean=0.85,
    ci_low=0.80,
    ci_high=0.90,
    n=2,
    confidence_level=0.95,
)


def test_panel_judge_report_finds_metric_and_rejects_absent_name():
    report = PanelJudgeReport(judge_id="judge-a", family="vendor-a", metrics=[METRIC])
    assert report.metric("faithfulness") is METRIC
    with pytest.raises(KeyError, match="context_precision"):
        report.metric("context_precision")


def test_panel_report_finds_judge_and_aggregates_cost():
    judge = PanelJudgeReport(judge_id="judge-a", family="vendor-a", metrics=[METRIC])
    report = PanelReport(
        per_case_cost=[
            CaseCost(case_id="case-1", total_tokens=100, latency_ms=200.0),
            CaseCost(case_id="case-2", total_tokens=150, latency_ms=400.0),
        ],
        judge_reports=[judge],
        disagreement=[],
    )
    assert report.judge("judge-a") is judge
    assert report.total_tokens == 250
    assert report.mean_latency_ms == 300.0
    with pytest.raises(KeyError, match="judge-b"):
        report.judge("judge-b")


def test_disagreement_stat_rejects_negative_case_delta():
    with pytest.raises(ValidationError, match="negative"):
        DisagreementStat(
            metric="faithfulness",
            case_deltas={"case-1": -0.1},
            pairwise_correlation={},
        )
