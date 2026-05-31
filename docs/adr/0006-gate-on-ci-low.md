# ADR-006: Gate compares against the confidence interval lower bound

**Date:** 2026-05-30
**Status:** Accepted

## Context

RF-09 fails the gate when a metric falls below a defined threshold. Every metric produced by the eval is a mean with a confidence interval (RNF-03). Gating by the point mean would let through results whose uncertainty still crosses the threshold — that is, a result that is statistically indistinguishable from a failure would be reported as passing.

## Decision

The gate passes only if `ci_low >= threshold`. The lower bound of the confidence interval must be above (or equal to) the threshold for the gate to approve. A metric with a defined threshold that is absent from the report is treated as a failure, not as a silent pass.

## Consequences

**Upsides:**
- Statistical honesty preserved at the gate: an ambiguous result (CI that crosses the threshold) does not pass.
- An absent metric is an explicit failure, which prevents incomplete configurations from going unnoticed.

**Downsides / trade-offs:**
- Stricter gate with few cases, because the CI is wider. With few cases in the dataset, real metrics above the threshold may fail the gate due to high uncertainty.
- Mitigated by **more cases** in the dataset (ADR-008). Increasing the judge `runs` count does **not** narrow the CI — runs only reduce noise within a case; CI width is a function of the number of cases.

**Neutral / to watch:**
- Choosing `ci_low` as the criterion is conservative by design. Operators who accept greater risk can set lower thresholds, but the comparison criterion remains `ci_low`.
- `ci_low` now comes from the percentile bootstrap over cases (ADR-008), bounded to [0,1] by construction. Clamping the CI to the metric range (the original decision in this ADR) has been **retired**: the bootstrap does not produce bounds outside [0,1].

## Alternatives considered

| Alternative | Why it was rejected |
|---|---|
| Compare by point mean | Would let through statistically ambiguous results; a metric of 0.70 ± 0.05 with threshold 0.68 would pass, even though the CI crosses the threshold. |
| Compare by the CI midpoint | Equivalent to the mean; does not capture uncertainty on the low side. |
| Silent pass for absent metric | Allows incomplete configurations or errors in the collection pipeline to pass the gate without signaling the problem. |
