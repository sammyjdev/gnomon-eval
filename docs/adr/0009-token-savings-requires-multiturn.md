# ADR-009: Token savings is validated by real multi-turn measurement

**Date:** 2026-07-02
**Status:** Accepted

## Context

AXON recall PREPENDS retrieved context to the query
(axon http/app.py: augmented_query). In a single-turn eval, recall
therefore INCREASES input tokens per request. GNOMON is single-turn:
it measures quality lift (faithfulness, context_precision) and the
input-token COST of recall. A previously published 52.3% savings figure
came from a deterministic model, not measurement.

Savings can only exist, and only be measured, across turns: a
without-AXON baseline resends the full growing context every turn, while
a with-AXON arm resends a fixed recall budget. Single-turn measurement
cannot observe this because there is no growing context to compare
against.

## Decision

ADR 0009 requires that any "AXON saves tokens" claim be backed by a real
multi-turn measurement: an N-turn session runner comparing WITH AXON
(fixed recall budget per turn) against WITHOUT AXON (re-sending the full
growing context each turn), counting real provider tokens per turn.

ADR 0009 requires that single-turn A/B results (gnomon
config/axon-recall-on.toml vs axon-recall-off.toml) be framed as quality
lift plus recall cost, never as savings.

## Consequences

**Upsides:**
- Claims survive skeptical review: no reviewer can point to a wrong-metric
  relapse (single-turn cost mislabeled as savings).
- The withdrawn 52.3% figure is retired from any decision-facing report
  until measured, closing the deterministic-model-as-evidence gap.

**Downsides / trade-offs:**
- The savings number is blocked until the Wave 2 multi-turn harness
  exists; no "AXON saves tokens" claim can ship in the meantime.
- Single-turn runs still need explicit framing (quality lift plus recall
  cost) in every report, one more thing report authors must get right.

**Neutral / to watch:**
- Once the multi-turn harness lands, it becomes the sole source for any
  token-savings claim; the single-turn A/B stays the source for quality
  lift and recall cost.

## Alternatives considered

| Alternative | Why it was rejected |
|---|---|
| Keep the deterministic model's 52.3% projection as the savings figure | A projection is not evidence; it cannot survive a skeptical reviewer and was already withdrawn once. |
| Treat the single-turn token delta (recall on vs off) as savings | Structurally impossible: recall prepends context, so single-turn input tokens increase, not decrease, when recall is on. |

## Relations
- Relates to: ADR 0004 (cost and latency are first-class in EvalReport).
- Relates to: ADR 0005 (openai_compat contexts contract used by the A/B).
- Requires: AXON recall telemetry (axon observability/recall_telemetry.py)
  as the source of the prompt/completion split.
