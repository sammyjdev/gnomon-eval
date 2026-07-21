"""Panel majority gate tests (ADR-0012)."""

from gnomon.domain.models import MetricResult, PanelJudgeReport, PanelReport
from gnomon.gate.panel_gate import evaluate_panel_gate


def _metric(ci_low):
    return MetricResult(
        metric="faithfulness",
        mean=0.8,
        ci_low=ci_low,
        ci_high=1.0,
        n=2,
        confidence_level=0.95,
    )


def _report(ci_lows):
    return PanelReport(
        per_case_cost=[],
        judge_reports=[
            PanelJudgeReport(
                judge_id=f"judge-{index}",
                family=f"vendor-{index}",
                metrics=[] if ci_low is None else [_metric(ci_low)],
            )
            for index, ci_low in enumerate(ci_lows, start=1)
        ],
        disagreement=[],
    )


def test_two_of_three_passing_judges_pass_the_gate():
    result = evaluate_panel_gate(_report([0.8, 0.7, 0.6]), {"faithfulness": 0.7})
    assert result.passed is True
    assert result.failures == []


def test_one_of_three_passing_judges_fails_the_gate():
    result = evaluate_panel_gate(_report([0.8, 0.6, 0.5]), {"faithfulness": 0.7})
    assert result.passed is False
    assert "1/3 judges passed (need 2)" in result.failures[0]


def test_all_passing_judges_pass_the_gate():
    result = evaluate_panel_gate(_report([0.9, 0.8, 0.7]), {"faithfulness": 0.7})
    assert result.passed is True


def test_all_failing_judges_fail_the_gate_and_name_metric():
    result = evaluate_panel_gate(_report([0.6, 0.5, 0.4]), {"faithfulness": 0.7})
    assert result.passed is False
    assert "faithfulness" in result.failures[0]
    assert "0/3 judges passed (need 2)" in result.failures[0]


def test_missing_metric_counts_as_a_failed_vote():
    result = evaluate_panel_gate(_report([0.8, 0.6, None]), {"faithfulness": 0.7})
    assert result.passed is False
    assert "1/3 judges passed (need 2)" in result.failures[0]
    assert "judge-3: absent" in result.failures[0]
