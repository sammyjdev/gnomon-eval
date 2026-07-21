"""Explicit majority gate for panel reports (ADR-0012)."""

from gnomon.domain.models import PanelReport
from gnomon.gate.gate import GateResult


def evaluate_panel_gate(report: PanelReport, thresholds: dict[str, float]) -> GateResult:
    """Pass each metric when a strict majority clears its CI threshold."""
    failures: list[str] = []
    total = len(report.judge_reports)
    majority_needed = total // 2 + 1
    for metric, threshold in thresholds.items():
        passed_count = 0
        verdicts: list[str] = []
        for judge_report in report.judge_reports:
            try:
                result = judge_report.metric(metric)
            except KeyError:
                verdicts.append(f"{judge_report.judge_id}: absent (fail)")
                continue
            passed = result.ci_low >= threshold
            passed_count += passed
            verdicts.append(
                f"{judge_report.judge_id}: ci_low={result.ci_low:.3f} "
                f"({'pass' if passed else 'fail'})"
            )
        if passed_count < majority_needed:
            failures.append(
                f"{metric}: {passed_count}/{total} judges passed "
                f"(need {majority_needed}); {'; '.join(verdicts)}"
            )
    return GateResult(passed=not failures, failures=failures)
