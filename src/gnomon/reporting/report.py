"""Serialise an EvalReport for machines and for humans.

Both forms read from the same EvalReport, so the number a machine parses and
the number a person reads cannot diverge (ARCHITECTURE: Reporting).
"""

from gnomon.domain.models import EvalReport


def to_dict(report: EvalReport) -> dict:
    """Machine-readable form: JSON-serialisable plain dict."""
    return {
        "metrics": [
            {
                "metric": m.metric,
                "mean": m.mean,
                "ci_low": m.ci_low,
                "ci_high": m.ci_high,
                "n": m.n,
                "confidence_level": m.confidence_level,
            }
            for m in report.metrics
        ],
        "cost": {
            "total_tokens": report.total_tokens,
            "mean_latency_ms": report.mean_latency_ms,
        },
        "per_case": [
            {
                "case_id": c.case_id,
                "total_tokens": c.total_tokens,
                "latency_ms": c.latency_ms,
            }
            for c in report.per_case_cost
        ],
    }


def to_text(report: EvalReport) -> str:
    """Human-readable form, derived from the same report object."""
    lines = ["Evaluation report", "=================", "", "Quality (judge metrics):"]
    for m in report.metrics:
        lines.append(
            f"  {m.metric}: mean={m.mean:.3f} "
            f"[{m.ci_low:.3f}, {m.ci_high:.3f}] "
            f"({int(m.confidence_level * 100)}% CI, N={m.n})"
        )
    lines += [
        "",
        "Cost & latency:",
        f"  total tokens: {report.total_tokens}",
        f"  mean latency: {report.mean_latency_ms} ms",
        "",
        "Per case:",
    ]
    lines += [
        f"  {c.case_id}: {c.total_tokens} tokens, {c.latency_ms} ms" for c in report.per_case_cost
    ]
    return "\n".join(lines)
