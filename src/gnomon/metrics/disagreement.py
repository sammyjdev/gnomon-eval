"""Cross-judge disagreement statistics for panel reports (ADR-0012)."""

from itertools import combinations
from math import sqrt

from gnomon.domain.models import DisagreementStat, PanelJudgeReport


def _pearson(left: dict[str, float], right: dict[str, float]) -> float:
    shared = [case_id for case_id in left if case_id in right]
    if len(shared) < 2:
        return 0.0
    if (
        len({left[case_id] for case_id in shared}) == 1
        or len({right[case_id] for case_id in shared}) == 1
    ):
        return 0.0
    left_mean = sum(left[case_id] for case_id in shared) / len(shared)
    right_mean = sum(right[case_id] for case_id in shared) / len(shared)
    covariance = sum(
        (left[case_id] - left_mean) * (right[case_id] - right_mean) for case_id in shared
    ) / len(shared)
    left_variance = sum((left[case_id] - left_mean) ** 2 for case_id in shared) / len(shared)
    right_variance = sum((right[case_id] - right_mean) ** 2 for case_id in shared) / len(shared)
    if left_variance == 0.0 or right_variance == 0.0:
        return 0.0
    return covariance / sqrt(left_variance * right_variance)


def compute_disagreement(judge_reports: list[PanelJudgeReport]) -> list[DisagreementStat]:
    """Compute per-case score spread and pairwise correlation for each metric."""
    metric_names = list(
        dict.fromkeys(metric for report in judge_reports for metric in report.case_scores)
    )
    stats: list[DisagreementStat] = []
    for metric in metric_names:
        scores_by_judge = [
            {score.case_id: score.score for score in report.case_scores.get(metric, [])}
            for report in judge_reports
        ]
        case_ids = list(dict.fromkeys(case_id for scores in scores_by_judge for case_id in scores))
        case_deltas = {
            case_id: max(values) - min(values) if len(values) >= 2 else 0.0
            for case_id in case_ids
            if (values := [scores[case_id] for scores in scores_by_judge if case_id in scores])
        }
        pairwise_correlation = {
            f"{judge_reports[a].judge_id}|{judge_reports[b].judge_id}": _pearson(
                scores_by_judge[a], scores_by_judge[b]
            )
            for a, b in combinations(range(len(judge_reports)), 2)
        }
        stats.append(
            DisagreementStat(
                metric=metric,
                case_deltas=case_deltas,
                pairwise_correlation=pairwise_correlation,
            )
        )
    return stats
