"""Machine and human serialisation for panel reports (ADR-0012)."""

from gnomon.domain.models import PanelReport


def panel_to_dict(report: PanelReport) -> dict:
    """Return a JSON-serialisable panel report without blending judge scores."""
    return {
        "judges": [
            {
                "judge_id": judge_report.judge_id,
                "family": judge_report.family,
                "metrics": [
                    {
                        "metric": metric.metric,
                        "mean": metric.mean,
                        "ci_low": metric.ci_low,
                        "ci_high": metric.ci_high,
                        "n": metric.n,
                        "confidence_level": metric.confidence_level,
                    }
                    for metric in judge_report.metrics
                ],
            }
            for judge_report in report.judge_reports
        ],
        "disagreement": [
            {
                "metric": stat.metric,
                "case_deltas": stat.case_deltas,
                "pairwise_correlation": stat.pairwise_correlation,
            }
            for stat in report.disagreement
        ],
        "cost": {
            "total_tokens": report.total_tokens,
            "mean_latency_ms": report.mean_latency_ms,
        },
        "per_case": [
            {
                "case_id": cost.case_id,
                "total_tokens": cost.total_tokens,
                "latency_ms": cost.latency_ms,
            }
            for cost in report.per_case_cost
        ],
    }


def panel_to_text(report: PanelReport) -> str:
    """Return a human-readable panel report from the same source object."""
    lines = ["Panel evaluation report", "=======================", "", "Judges:"]
    for judge_report in report.judge_reports:
        lines += ["", f"  {judge_report.judge_id} ({judge_report.family}):"]
        for metric in judge_report.metrics:
            lines.append(
                f"    {metric.metric}: mean={metric.mean:.3f} "
                f"[{metric.ci_low:.3f}, {metric.ci_high:.3f}] "
                f"({int(metric.confidence_level * 100)}% CI, N={metric.n})"
            )
    lines += ["", "Disagreement:"]
    for stat in report.disagreement:
        lines.append(f"  {stat.metric}:")
        lines += [
            f"    {case_id}: delta={delta:.3f}" for case_id, delta in stat.case_deltas.items()
        ]
        lines += [
            f"    {pair}: correlation={correlation:.3f}"
            for pair, correlation in stat.pairwise_correlation.items()
        ]
    lines += [
        "",
        "Cost & latency:",
        f"  total tokens: {report.total_tokens}",
        f"  mean latency: {report.mean_latency_ms} ms",
        "",
        "Per case:",
    ]
    lines += [
        f"  {cost.case_id}: {cost.total_tokens} tokens, {cost.latency_ms} ms"
        for cost in report.per_case_cost
    ]
    return "\n".join(lines)
