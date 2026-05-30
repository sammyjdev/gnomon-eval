"""Regression gate: turn an evaluation into a CI pass/fail (RF-09).

Gates on the lower bound of the confidence interval, not the mean (ADR-006):
a metric passes only if we are confident — within the reported interval — that
it clears the threshold. A threshold for a metric absent from the report is a
failure, never a silent pass. Threshold range is validated upstream at config
load (VAL-05), so this layer trusts the numbers.
"""

from dataclasses import dataclass

from gnomon.domain.models import EvalReport


@dataclass(frozen=True)
class GateResult:
    passed: bool
    failures: list[str]


def evaluate_gate(report: EvalReport, thresholds: dict[str, float]) -> GateResult:
    failures: list[str] = []
    for metric, threshold in thresholds.items():
        try:
            result = report.metric(metric)
        except KeyError:
            failures.append(f"{metric}: required by gate but absent from report")
            continue
        if result.ci_low < threshold:
            failures.append(f"{metric}: ci_low={result.ci_low:.3f} < threshold={threshold:.3f}")
    return GateResult(passed=not failures, failures=failures)
