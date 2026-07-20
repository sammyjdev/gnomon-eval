# ADR-008: Aggregation unit is the case; CI by bootstrap over cases

**Date:** 2026-05-30
**Status:** Accepted (supersedes the t-interval + clamp part of ADR-006)

## Context

Running the real Ollama judge (`temperature=0`) exposed two problems in the original aggregation (Phase 1):

1. **Inflated `n`.** The runner stacked all `cases × runs` scores into a single vector and computed a t-interval with `n = cases × runs`. With the deterministic judge, the N runs for a case are **identical**. Counting 8 identical copies as 8 independent observations artificially narrows the CI — a direct violation of RNF-03 (statistical honesty), the central invariant of the project. Measurement: with 2 cases `[1.0, 0.0]` and 8 runs, the old method reported `[0.225, 0.775]`; the honest real-information result (2 observations) is `[0.0, 1.0]`.
2. **T-interval clamp.** With few points, the t-interval of a metric bounded to [0,1] overflows the range (e.g., `[-5.85, 6.85]`) and ADR-006 clamped it to [0,1]. The clamp hides the overflow and, near the extremes, **lies about the upper bound** (it lets the gate assert "could be 100%" even with observed failures).

The two sources of variation were conflated: judge noise (Q1 — recurrence on the same scene) and spread across cases (Q2 — the dataset is a sample from the population of questions). The gate (RF-09) only cares about Q2.

## Decision

**Aggregation (A): the case is the sampling unit.** The N runs for a case are collapsed into their mean (denoise within the case, not independent samples). The dataset metric aggregates over **cases**: `n = number of cases`. Fewer than 2 cases does not bound a population and is rejected.

**Interval (F2): percentile bootstrap over cases.** The CI is the (α/2, 1−α/2) percentile of means of resamples of the per-case scores. Since each resample mean is the mean of values already in [0,1], the interval is **bounded by construction — no clamp**. The bootstrap is **seeded** (`config.seed`) to preserve reproducibility (RNF-01).

The gate continues comparing `ci_low >= threshold` (ADR-006), now over the bootstrap `ci_low`.

## Consequences

**Upsides:**
- Honesty restored (RNF-03): `n` reflects real observations (cases); identical runs do not fabricate confidence.
- No clamp and no lying upper bound: the interval is born within [0,1].
- Trivial and perfect reproducibility with a deterministic judge (`temperature=0`), via the bootstrap seed.
- Method-agnostic with respect to confidence level: the bootstrap accepts any `confidence_level` in (0,1), without a t-table.

**Downsides / trade-offs:**
- With few cases the CI is wide (correct, but may be frustrating). The lever for a narrower CI is **more cases** in the dataset (RF-01), not more runs.
- The bootstrap is more expensive than a closed-form formula (2000 resamples), but negligible compared to a model call.
- Number of runs only becomes useful with a noisy judge (`temperature>0`); with `temperature=0` it is redundant. The floor `judge_runs>=2` (VAL-04) was kept for now; relaxing it to 1 is a follow-up open question.

**Neutral / to watch:**
- `MetricResult.n` changes semantics: it was runs, now it is cases.

## Alternatives considered

| Alternative | Why it was rejected |
|---|---|
| Keep `cases × runs` pooling with t-interval | Inflates `n` with deterministic copies and artificially narrows the CI (violates RNF-03). |
| Keep t-interval + clamp to range | The clamp lies about the upper bound near the extremes (asserts 100% with observed failures). |
| Wilson/Jeffreys (F1, binary) | Would require binarizing the judge score (✓/✗), losing the 0–1 gradation; this is a product change. Reserved if extra robustness against a weak judge is desired. |
| Judge variance with `temperature>0` (measuring Q1) | Measures the less useful question for the gate; our measurement showed variance ≈0 even at temp=0.8 for clear cases, and temp>0 complicates reproducibility. |
| Hierarchical model (2 levels, Q1+Q2) | Statistically more complete, but with a deterministic judge collapses exactly to the bootstrap over cases; implementation cost is not justified in v1. |

## Amendment (2026-07-19)

A hypothesis property test found that the percentile bootstrap is bounded
within [0, 1] by construction, but NOT bounded relative to the mean: at a low
`confidence_level` with asymmetric per-case scores, floating point rounding
in the resample sums can place `ci_low` above the mean (or `ci_high` below
it) - an ordering violation, not the range overflow this ADR's clamp
discussion is about. Fixed by clamping both endpoints against the mean
(`ci_low = min(ci_low, mean)`, `ci_high = max(ci_high, mean)`) in
`aggregate_metric`. This does not reintroduce the clamp rejected above: that
one hid a t-interval overflowing past [0, 1] near the extremes and lied
about the upper bound; this one only fixes percentile ordering around the
mean, never fires at the `confidence_level` used in practice (0.95), and the
interval still never overflows [0, 1].
