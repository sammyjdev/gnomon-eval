"""Aggregate per-case judge scores into a MetricResult (RF-06, RNF-03, ADR-008).

Each case contributes one score per metric: the runner averages the judge's N
runs within a case, so runs *denoise* the case's score, they are not counted as
independent samples (counting N identical deterministic runs as N observations
would fake a tighter interval than the data supports — a RNF-03 violation).

The dataset is a sample of questions, so the confidence interval is taken over
the CASES: a seeded percentile bootstrap of the per-case mean. Because every
bootstrap resample is a mean of scores already in [0, 1], the interval is
bounded by construction — no clamp, and no t-interval blow-up to amputate at
low n (ADR-008 supersedes the t-interval + clamp of ADR-006). Fewer than two
cases cannot bound a population and is rejected.
"""

import random

from gnomon.domain.models import MetricResult

# A confidence interval over the dataset needs at least two cases to have any
# spread; one case says nothing about the population of questions.
MIN_CASES = 2

# Judge-run floor, kept for config validation (VAL-04): runs denoise a noisy
# judge. With a deterministic judge (temperature 0) they are redundant.
MIN_JUDGE_RUNS = 2

_BOOTSTRAP_RESAMPLES = 2000


def aggregate_metric(
    metric: str, case_scores: list[float], *, confidence_level: float = 0.95, seed: int
) -> MetricResult:
    """Mean over cases with a seeded percentile-bootstrap confidence interval."""
    n = len(case_scores)
    if n < MIN_CASES:
        raise ValueError(
            f"need at least {MIN_CASES} cases to bootstrap a confidence interval "
            f"for {metric!r}, got {n}"
        )

    mean = sum(case_scores) / n
    rng = random.Random(seed)
    boot_means: list[float] = []
    for _ in range(_BOOTSTRAP_RESAMPLES):
        total = 0.0
        for _ in range(n):
            total += case_scores[rng.randrange(n)]
        boot_means.append(total / n)
    boot_means.sort()

    alpha = 1.0 - confidence_level
    lo_index = int((alpha / 2.0) * _BOOTSTRAP_RESAMPLES)
    hi_index = int((1.0 - alpha / 2.0) * _BOOTSTRAP_RESAMPLES) - 1
    return MetricResult(
        metric=metric,
        mean=mean,
        ci_low=boot_means[lo_index],
        ci_high=boot_means[hi_index],
        n=n,
        confidence_level=confidence_level,
    )
