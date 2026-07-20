"""Orchestrates one evaluation run.

The only component that knows all the others (ARCHITECTURE: Runner). It
depends on the domain contracts (RagTarget, Judge), never on concrete
implementations, so swapping the target or judge is a wiring change, not a
runner change.

Judge-call accounting is explicit (RNF-06): the runner calls judge.score()
exactly len(cases) * config.judge_runs times, and the Ollama judge makes one
model call per score() (all metrics scored in that single call) — so the
billable model-call count is exactly len(cases) * config.judge_runs, with no
hidden per-metric multiplier.
"""

from collections import defaultdict

from gnomon.config.config import EvalConfig
from gnomon.domain.interfaces import Judge, RagTarget
from gnomon.domain.models import CaseCost, CaseScore, EvalCase, EvalReport
from gnomon.metrics.confidence import aggregate_metric


def run_eval(
    cases: list[EvalCase], target: RagTarget, judge: Judge, config: EvalConfig
) -> EvalReport:
    """Run every case against the target, score with the judge, aggregate."""
    per_case_cost: list[CaseCost] = []
    case_scores: dict[str, list[CaseScore]] = defaultdict(list)

    for case in cases:
        response = target.query(case.question)
        per_case_cost.append(
            CaseCost(
                case_id=case.id,
                total_tokens=response.total_tokens,
                latency_ms=response.latency_ms,
            )
        )
        # Denoise within the case: the case's score for a metric is the mean of
        # its N judge runs (ADR-008). Runs are repeated measures of one case,
        # not independent samples, so they are collapsed here, not pooled.
        runs_by_metric: dict[str, list[float]] = defaultdict(list)
        for run in range(config.judge_runs):
            run_scores = judge.score(case, response, seed=config.seed, run=run)
            for metric_name, value in run_scores.scores.items():
                runs_by_metric[metric_name].append(value)
        for metric_name, values in runs_by_metric.items():
            case_scores[metric_name].append(
                CaseScore(case_id=case.id, score=sum(values) / len(values))
            )

    metrics = [
        aggregate_metric(
            name,
            [cs.score for cs in scores],
            confidence_level=config.confidence_level,
            seed=config.seed,
        )
        for name, scores in case_scores.items()
    ]
    return EvalReport(metrics=metrics, per_case_cost=per_case_cost, case_scores=dict(case_scores))
