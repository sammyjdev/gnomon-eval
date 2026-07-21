"""Panel disagreement tests (ADR-0012)."""

import pytest

from gnomon.domain.models import CaseScore, PanelJudgeReport
from gnomon.metrics.disagreement import compute_disagreement


def _judge(judge_id, scores_by_metric):
    return PanelJudgeReport(
        judge_id=judge_id,
        family=f"family-{judge_id}",
        metrics=[],
        case_scores={
            metric: [CaseScore(case_id=case_id, score=score) for case_id, score in scores.items()]
            for metric, scores in scores_by_metric.items()
        },
    )


def test_case_delta_is_real_score_spread():
    stats = compute_disagreement(
        [
            _judge("judge-a", {"faithfulness": {"case-1": 0.9}}),
            _judge("judge-b", {"faithfulness": {"case-1": 0.5}}),
        ]
    )
    assert stats[0].case_deltas["case-1"] == 0.4


def test_case_deltas_preserve_different_spreads_per_case():
    stat = compute_disagreement(
        [
            _judge(
                "judge-a",
                {"faithfulness": {"case-1": 0.9, "case-2": 0.8, "case-3": 0.7}},
            ),
            _judge(
                "judge-b",
                {"faithfulness": {"case-1": 0.8, "case-2": 0.5, "case-3": 0.2}},
            ),
        ]
    )[0]
    assert stat.case_deltas["case-1"] == pytest.approx(0.1)
    assert stat.case_deltas["case-2"] == pytest.approx(0.3)
    assert stat.case_deltas["case-3"] == pytest.approx(0.5)


def test_perfectly_correlated_judges_have_correlation_one():
    stat = compute_disagreement(
        [
            _judge("judge-a", {"faithfulness": {"case-1": 0.2, "case-2": 0.5, "case-3": 0.9}}),
            _judge("judge-b", {"faithfulness": {"case-1": 0.2, "case-2": 0.5, "case-3": 0.9}}),
        ]
    )[0]
    assert stat.pairwise_correlation["judge-a|judge-b"] == pytest.approx(1.0)


def test_perfectly_anti_correlated_judges_have_correlation_negative_one():
    stat = compute_disagreement(
        [
            _judge("judge-a", {"faithfulness": {"case-1": 0.1, "case-2": 0.5, "case-3": 0.9}}),
            _judge("judge-b", {"faithfulness": {"case-1": 0.9, "case-2": 0.5, "case-3": 0.1}}),
        ]
    )[0]
    assert stat.pairwise_correlation["judge-a|judge-b"] == pytest.approx(-1.0)


def test_constant_judge_has_zero_correlation():
    stat = compute_disagreement(
        [
            _judge("judge-a", {"faithfulness": {"case-1": 0.4, "case-2": 0.4, "case-3": 0.4}}),
            _judge("judge-b", {"faithfulness": {"case-1": 0.2, "case-2": 0.5, "case-3": 0.9}}),
        ]
    )[0]
    assert stat.pairwise_correlation["judge-a|judge-b"] == 0.0


def test_metric_missing_from_one_judge_is_handled():
    stat = compute_disagreement(
        [
            _judge("judge-a", {"faithfulness": {"case-1": 0.8, "case-2": 0.9}}),
            _judge("judge-b", {}),
        ]
    )[0]
    assert stat.case_deltas == {"case-1": 0.0, "case-2": 0.0}
    assert stat.pairwise_correlation["judge-a|judge-b"] == 0.0
