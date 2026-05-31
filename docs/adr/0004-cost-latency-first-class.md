# ADR-004: Cost and latency as first-class metrics

**Date:** 2026-05-29
**Status:** Accepted

## Context

The real decision a RAG operator faces is never "which configuration answers best" but rather "which one answers well enough for what it costs". Existing evaluation tools report quality in isolation. A high-quality response that consumes far more tokens and far more time appears as the winner in the report, even when the cheaper and faster option would be the right choice for the use case.

Treating cost and latency as an appendix -- outside the quality report or optional -- leads the operator to optimize for quality and discover the cost only when the invoice arrives.

## Decision

Cost, measured in tokens, and latency, measured in milliseconds, are first-class metrics. The target adapter collects tokens and latency for every response. The report for any run includes these numbers -- aggregated and per question -- in the same report and alongside quality, never in a separate output and never as an optional step.

## Consequences

**Upsides:**
- The operator decides on the real trade-off: quality versus cost versus latency, in a single view.
- Comparing two RAG configurations exposes the cost of each quality point gained.
- The number of judge calls per run is an explicit function of dataset size and N of runs, making the cost of running the eval itself predictable.

**Downsides / trade-offs:**
- Requires every target adapter to report tokens and latency. A target that does not expose a token count forces a handling policy, defined in validation VAL-03, rather than assuming zero.
- Couples cost collection to the adapter, which must measure latency consistently for the numbers to be comparable across targets.

**Neutral / to watch:**
- Latency comparability across runs depends on machine and network conditions. It is worth documenting that latency is comparable within an environment, not across different environments.

## Alternatives considered

| Alternative | Why it was rejected |
|---|---|
| Report quality only | Hides the trade-off that is the operator's real decision; optimizing quality blindly leads to cost discovered late. |
| Cost and latency as a separate optional report | Separating the two dimensions from quality causes the operator to compare quality without cost in the same view, which is the exact error this decision corrects. |
| Measure cost in currency only, not in tokens | Price per token varies by provider and changes over time; tokens is the stable, convertible unit and is therefore the base, with currency as an optional derivation. |
