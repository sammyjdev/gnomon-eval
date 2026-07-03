# ADR 0009: Token savings is validated by real multi-turn measurement

## Status
Accepted (2026-07-02)

## Context
AXON recall PREPENDS retrieved context to the query
(axon http/app.py: augmented_query). In a single-turn eval, recall
therefore INCREASES input tokens per request. GNOMON is single-turn:
it measures quality lift (faithfulness, context_precision) and the
input-token COST of recall. A previously published 52.3% savings figure
came from a deterministic model, not measurement.

## Decision
ADR 0009 requires that any "AXON saves tokens" claim be backed by a real
multi-turn measurement: an N-turn session runner comparing WITH AXON
(fixed recall budget per turn) against WITHOUT AXON (re-sending the full
growing context each turn), counting real provider tokens per turn.

ADR 0009 requires that single-turn A/B results (gnomon
config/axon-recall-on.toml vs axon-recall-off.toml) be framed as quality
lift plus recall cost, never as savings.

## Rationale
- Single-turn: recall adds prompt tokens; "savings" is structurally
  impossible to observe.
- Multi-turn: the baseline's context grows linearly with turns while the
  recall arm's stays bounded; only there can savings exist and be measured.
- A deterministic model is a projection, not evidence; it cannot survive
  a skeptical reviewer.

## Relations
- Relates to: ADR 0004 (cost and latency are first-class in EvalReport).
- Relates to: ADR 0005 (openai_compat contexts contract used by the A/B).
- Requires: AXON recall telemetry (axon observability/recall_telemetry.py)
  as the source of the prompt/completion split.
