"""Runs ChatEval cases through a target and judge, aggregating into the same
EvalReport shape the RAG and session arms already produce (RF-06/RNF-03),
via the shared aggregate_metric bootstrap-CI helper unchanged."""

from gnomon.domain.chat import ChatCase
from gnomon.domain.models import CaseCost, EvalReport, MetricResult
from gnomon.metrics.confidence import aggregate_metric


def run_chat_eval(
    cases: list[ChatCase],
    target,
    judge,
    *,
    seed: int,
    confidence_level: float = 0.95,
) -> EvalReport:
    per_case_cost: list[CaseCost] = []
    scores_by_metric: dict[str, list[float]] = {}

    for case in cases:
        result = target.run(case)
        per_case_cost.append(
            CaseCost(
                case_id=case.id,
                total_tokens=result.total_tokens,
                latency_ms=result.latency_ms,
            )
        )
        case_scores = judge.score(case, result)
        for metric_name, value in case_scores.items():
            scores_by_metric.setdefault(metric_name, []).append(value)

    metrics: list[MetricResult] = [
        aggregate_metric(
            metric_name,
            values,
            confidence_level=confidence_level,
            seed=seed,
        )
        for metric_name, values in scores_by_metric.items()
    ]

    return EvalReport(metrics=metrics, per_case_cost=per_case_cost)
