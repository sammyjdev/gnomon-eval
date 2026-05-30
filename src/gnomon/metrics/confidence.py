"""Turn N judge scores into a MetricResult with a confidence interval.

Small-N regime: the judge runs are few, so the interval is a Student-t
interval, not a normal approximation. Reporting a normal interval for n=5
would understate the uncertainty and quietly violate RNF-03.

The interval is clamped to the metric's [0, 1] range: a faithfulness
"upper bound" of 1.48 is an artifact of the t critical value at low df, not
a meaningful claim about a bounded metric.
"""

import math

from gnomon.domain.models import MetricResult

# VAL-04: a confidence interval needs a sample variance, which needs n >= 2.
MIN_JUDGE_RUNS = 2

# Two-sided Student-t critical values by degrees of freedom (df = n - 1).
# df beyond the table fall back to the normal approximation (z at 95%).
_T_CRITICAL_95 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}
_Z_95 = 1.960

# Only 0.95 is supported in the v1 slice. Other levels are rejected rather
# than silently computed against the wrong table.
_SUPPORTED_LEVELS = {0.95: (_T_CRITICAL_95, _Z_95)}


def _t_critical(df: int, level: float) -> float:
    table, z = _SUPPORTED_LEVELS[level]
    return table.get(df, z)


def aggregate_metric(
    metric: str, scores: list[float], *, confidence_level: float = 0.95
) -> MetricResult:
    """Aggregate per-run judge scores into a mean and confidence interval."""
    if confidence_level not in _SUPPORTED_LEVELS:
        raise ValueError(
            f"unsupported confidence level {confidence_level}; supported: "
            f"{sorted(_SUPPORTED_LEVELS)}"
        )
    n = len(scores)
    if n < MIN_JUDGE_RUNS:
        raise ValueError(
            f"need at least {MIN_JUDGE_RUNS} judge runs to compute a confidence "
            f"interval for {metric!r}, got {n}"
        )

    mean = sum(scores) / n
    variance = sum((s - mean) ** 2 for s in scores) / (n - 1)
    std_error = math.sqrt(variance) / math.sqrt(n)
    margin = _t_critical(n - 1, confidence_level) * std_error

    return MetricResult(
        metric=metric,
        mean=mean,
        ci_low=max(0.0, mean - margin),
        ci_high=min(1.0, mean + margin),
        n=n,
        confidence_level=confidence_level,
    )
