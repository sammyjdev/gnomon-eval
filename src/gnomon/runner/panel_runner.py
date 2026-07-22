"""Fan one target response out to independent panel judges (ADR-0012)."""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import NamedTuple

from gnomon.config.config import EvalConfig
from gnomon.domain.interfaces import Judge, RagTarget
from gnomon.domain.models import (
    CaseCost,
    CaseScore,
    EvalCase,
    PanelJudgeReport,
    PanelReport,
)
from gnomon.metrics.confidence import aggregate_metric
from gnomon.metrics.disagreement import compute_disagreement


class PanelMember(NamedTuple):
    judge_id: str
    family: str
    judge: Judge


def run_panel_eval(
    cases: list[EvalCase], target: RagTarget, members: list[PanelMember], config: EvalConfig
) -> PanelReport:
    """Query each case once, score it with every judge, and aggregate per judge."""
    per_case_cost: list[CaseCost] = []
    member_case_scores: list[dict[str, list[CaseScore]]] = [defaultdict(list) for _ in members]

    def _score_member(member: PanelMember, case: EvalCase, response) -> dict[str, float]:
        # Denoise within the case exactly as run_eval does (ADR-008).
        runs_by_metric: dict[str, list[float]] = defaultdict(list)
        for run in range(config.judge_runs):
            run_scores = member.judge.score(case, response, seed=config.seed, run=run)
            for metric_name, value in run_scores.scores.items():
                runs_by_metric[metric_name].append(value)
        return {name: sum(values) / len(values) for name, values in runs_by_metric.items()}

    # Members are independent HTTP-bound judges (ADR-0012): score them
    # concurrently per case, collected in member order so results are
    # identical to the sequential run.
    with ThreadPoolExecutor(max_workers=len(members)) as pool:
        for case in cases:
            response = target.query(case.question)
            per_case_cost.append(
                CaseCost(
                    case_id=case.id,
                    total_tokens=response.total_tokens,
                    latency_ms=response.latency_ms,
                )
            )
            futures = [pool.submit(_score_member, member, case, response) for member in members]
            for future, case_scores in zip(futures, member_case_scores, strict=True):
                for metric_name, score in future.result().items():
                    case_scores[metric_name].append(CaseScore(case_id=case.id, score=score))

    judge_reports = [
        PanelJudgeReport(
            judge_id=member.judge_id,
            family=member.family,
            metrics=[
                aggregate_metric(
                    name,
                    [case_score.score for case_score in scores],
                    confidence_level=config.confidence_level,
                    seed=config.seed,
                )
                for name, scores in case_scores.items()
            ],
            case_scores=dict(case_scores),
        )
        for member, case_scores in zip(members, member_case_scores, strict=True)
    ]
    return PanelReport(
        per_case_cost=per_case_cost,
        judge_reports=judge_reports,
        disagreement=compute_disagreement(judge_reports),
    )
