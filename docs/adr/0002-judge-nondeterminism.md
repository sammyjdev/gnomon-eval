# ADR-002: Handling LLM judge nondeterminism

**Date:** 2026-05-29
**Status:** Accepted (N of runs and cache granularity parameters open, see Open questions section)

## Context

The v1 quality metrics use an LLM as a judge. LLMs are nondeterministic: the same input produces different scores across different runs, even at low temperature. Reporting a single quality number hides that noise and leads to deploy decisions based on a value that fluctuates without the operator knowing.

This is the central differentiator of the harness. Most existing tools report a single score. Addressing nondeterminism head-on -- measuring and exposing variance -- is what sets this harness apart from the alternatives.

The constraint is the tension between statistical confidence and cost. More judge runs per metric tighten the confidence interval but multiply model calls, time, and cost. The decision must balance statistical honesty with execution viability, including the offline path with Ollama, which is slower.

## Decision

The judge scores each case/metric pair N times. The system reports the mean with a confidence interval calculated over those N scores. No judge-based metric is emitted as a single number; the output always carries mean, lower threshold, upper threshold, and N.

To sustain reproducibility within this scheme, the judge runs under a declared seed and uses a cache. The cache key is the identity tuple that uniquely defines a score: case, response, judge model, and seed. An input whose key does not match that tuple is a miss, never an approximate hit.

Reproducible mode requires an explicit seed. Running in reproducible mode without a seed fails, rather than generating an implicit seed that would break reproducibility across runs.

## Consequences

**Upsides:**
- The operator sees the judge's noise instead of ignoring it, and makes deploy decisions over an interval, not a point.
- Reproducibility becomes a verifiable invariant: the same seed and the same judge model produce the same result within variance, tested in the reproducibility suite.
- The cache cuts re-execution cost when the input has not changed.

**Downsides / trade-offs:**
- N runs per metric multiply cost and time. On the offline path with Ollama, time is the most sensitive constraint.
- Cache keyed by seed means that changing the seed invalidates the entire cache. This is correct behavior, but it incurs re-execution cost when deliberately varying the seed.

**Neutral / to watch:**
- The appropriate value of N depends on the stability of the chosen judge model. A more stable model allows a smaller N for the same interval tightening. It is worth measuring the default judge's variance before fixing N.

## Open questions

Two parameters of this decision remain open and depend on measurement with the default judge model before being fixed:

1. **N of judge runs per metric.** ~~Trade-off between CI tightening and cost.~~ **Resolved (ADR-008):** we measured the variance of the default judge (Ollama, `temperature=0`) and it is **zero** -- the judge is deterministic by seed. Therefore the N runs are identical copies and **cannot** count as independent samples (doing so would inflate `n` and artificially narrow the CI, violating RNF-03). N became a *denoise* knob within the case (useful only with a noisy judge, `temperature>0`); with `temperature=0`, N=1 suffices. The CI width is a function of the **number of cases**, not of runs -- see ADR-008.
2. **Cache granularity.** The current decision defines the key as (case, response, judge model, seed). It remains to confirm whether that granularity is correct or whether a coarser key that shares scores across similar runs is worthwhile. The finer key is safer against contamination; the coarser key saves more. The safe choice is the fine key, and it is the default until there is evidence that the cost justifies relaxing it.

## Alternatives considered

| Alternative | Why it was rejected |
|---|---|
| Report a single quality number | Hides the judge's nondeterminism; this is the central flaw of existing tools that this harness exists to fix. |
| Force temperature zero and assume determinism | Temperature zero reduces but does not eliminate variance in many providers; assuming determinism that does not exist is statistical dishonesty. |
| Implicit seed generated when absent | Would break reproducibility across runs without the operator noticing, violating the central invariant. |
