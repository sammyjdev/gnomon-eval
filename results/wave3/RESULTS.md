# Wave 3 Extended results - 2026-07-03/04

Setup: same stack as 2026-07-02-ab-recall (target AXON `/v1/chat/completions`,
completion `ollama/llama3.1:8b` on the GPU box, judge `llama3.1:8b`, seed 42,
95% CI). Two rulers: single-turn Wave 1 harness (17 cases, judge_runs=8) for
retrieval quality; dual-arm session harness (10 sessions x 10 turns,
judge_runs=6) for cost. All runs on the merged chain (axon PRs #49/#51,
gnomon #2/#3).

## Validated claims

1. Retrieval ladder (single-turn, on-arm): faithfulness 0.711 [0.665] ->
   0.775 [0.735, 0.814]; context_precision 0.752 -> 0.792 (peak 0.822 at rung
   3b). Promoted config: index hygiene + skeleton-chunk suppression +
   AXON_HYBRID_SEARCH=1. Reproduce: `gnomon -c config/axon-recall-on.toml`.
2. Session cost vs re-sending the conversation (recall budget 500): cost
   parity - cumulative -0.079 / +0.031 / +0.167 across 3 runs (pooled +0.040),
   means mutually within CIs (stability PASS); crossover at turn 6-9; quality
   gate pass in all runs; 1200/1200 turn records usage_source=provider.
   Reproduce: `gnomon session -c config/axon-session-b500.toml`.

## Per-rung artifacts

| rung | file | verdict |
|------|------|---------|
| baseline (old index) | rung3a-old-index.json | reference |
| 3a index hygiene | rung3a-new-index.json | PROMOTED |
| 3b skeleton suppression | rung3b-skeleton.json | PROMOTED |
| 3c hybrid lexical | rung3c-hybrid.json | PROMOTED (best config) |
| 3d cross-encoder rerank | rung3d-rerank.json | REVERTED (worsened both metrics) |
| session b1000 | t12-session-3c-budget1000.json | reference |
| session b500 x3 | t12-session-3c-budget500.json, t12-b500-replicate{1,2}.json | PUBLISHED |

## Negative results (recorded so nobody retries them)

- Cosine score thresholds: junk scores 0.60-0.65 overlap gold 0.54-0.62 across
  queries - no separating floor exists.
- Delta-recall/dedup: 0/401 lexical drops (answers paraphrase, not quote);
  within-session chunk-hash reuse median 0% - nothing to dedup by any method.
- Cross-encoder rerank (jina-reranker-v2-base-multilingual, in-process):
  faithfulness 0.775 -> 0.748, precision 0.792 -> 0.760. Code kept env-gated OFF.

## Caveats (stated, not hidden)

- Single-turn gate (ADR-0006, faith ci_low >= 0.75) remains red by 0.015:
  0.735 measured. Residual gap is n=17 case-variance as much as retrieval
  (gnomon#6 tracks the honest fix: expand the case set).
- 2026-07-04 on-arm runs are single runs per rung (the ladder protocol), not
  3x replicates; only the published session claim carries the full stability
  protocol.
- Judge and target share llama3.1:8b (same caveat as 2026-07-02-ab-recall);
  gnomon#4 tracks the second judge.
- Sessions are scripted (LLM-drafted, owner-reviewed), not live traffic
  (ADR-0010 provenance).

Full decision trail: docs/adr/0011-three-counterfactual-claims-and-retrieval-ladder.md.
