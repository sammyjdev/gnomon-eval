from gnomon.domain.models import EvalReport, MetricResult
from gnomon.gate.gate import evaluate_gate


def _report(metric, ci_low, ci_high, mean):
    return EvalReport(
        metrics=[
            MetricResult(
                metric=metric,
                mean=mean,
                ci_low=ci_low,
                ci_high=ci_high,
                n=8,
                confidence_level=0.95,
            )
        ],
        per_case_cost=[],
    )


def test_passes_when_ci_low_clears_threshold():
    report = _report("faithfulness", ci_low=0.75, ci_high=0.9, mean=0.82)
    result = evaluate_gate(report, {"faithfulness": 0.7})
    assert result.passed is True
    assert result.failures == []


def test_fails_when_ci_low_below_threshold_even_if_mean_clears():
    report = _report("faithfulness", ci_low=0.65, ci_high=0.99, mean=0.82)
    result = evaluate_gate(report, {"faithfulness": 0.7})
    assert result.passed is False
    assert any("faithfulness" in f for f in result.failures)


def test_missing_metric_is_a_failure():
    report = _report("faithfulness", ci_low=0.8, ci_high=0.9, mean=0.85)
    result = evaluate_gate(report, {"context_precision": 0.6})
    assert result.passed is False
    assert any("context_precision" in f for f in result.failures)
