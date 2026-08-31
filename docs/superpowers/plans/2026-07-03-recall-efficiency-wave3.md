# Recall Efficiency - Wave 3 Implementation Plan (Ablation Ladder)

**Goal:** Move the savings crossover earlier (lower the AXON arm's per-turn cost floor) and fix retrieval precision, validating EVERY change with a measured `gnomon session` run before stacking the next one. No fix ships on faith; the Wave 2 harness is the instrument.

**Method:** One rung at a time. Each rung = implement -> full measured run (10x10, seed 42, same dataset) -> compare against the previous rung -> keep or revert. "Definitive" = the set of rungs that survives.

## Evidence base (2026-07-03, all on feat/session-savings-* branches)

- **Baseline (rung 0), recall_max_tokens=2000:** cumulative savings -1.396 [-2.205, -0.634]; per-turn improves monotonically from -19.9 (turn 0) to +0.06 (turn 9); no formal crossover inside 10 turns; faithfulness axon 0.606 [0.446, 0.731] vs baseline 0.620 [0.340, 0.860] - statistical parity, gate pass; validity clean (400/400 provider). Artifact: `results/wave3/rung0-baseline-2000.json`.
- **Retrieval precision problem (live probes):** broad questions fill the budget with irrelevant chunks (5/6 junk on "como funciona o density gate") and can induce factually wrong answers; consecutive same-topic turns share ~2% of retrieved content (fully stateless retrieval).
- **Naive score threshold is DEAD, do not implement:** absolute cosine scores do not separate relevant from irrelevant across queries (junk retrieval scored 0.604-0.648; perfect retrieval scored 0.539-0.624; good specific retrieval bottomed at 0.459). A global or top-relative floor fails on real data. Precision requires a reranker, not a floor.
- **Selection internals (scout map):** packing loop `axon/src/axon/store/vector_common.py:40-55` (`_rank_and_limit`) is pure top-k + fill-to-budget; per-candidate scores exist (`score = 1 - cosine`, staleness-adjusted); http endpoint effectively always uses strategy `balanced` (cap 2000); no session anchor server-side; RecallRecord has NO per-chunk data.

## Global constraints

- Wave 2 protocol continues: TDD, codex executors with per-task briefs, orchestrator commits, per-task reviews, plain "-" only.
- Branches: axon work stacks on `feat/session-savings-wave2` (PR #50); gnomon work stacks on `feat/session-savings-harness` (PR #3).
- Every rung's run artifact is saved to `results/wave3/rungN-<name>.json` and compared in the rung's commit message.
- Acceptance per rung: (1) cumulative savings mean improves vs previous rung; (2) quality gate passes; (3) axon final-turn faithfulness mean does not fall below the previous rung's CI low. Fail any -> revert the rung.
- The zero-history arm design is unchanged as a measurement reference. Recall gating and delta-recall are ONLY meaningful with conversation carryover; the owner's ratified product goal (2026-07-03) is "stop re-sending this much context every turn", which makes the transcript-anchored delta-recall rung the centerpiece of the wave, not an optional extra.

## Ladder

### Rung 1 (in flight): budget 1000 - config-only, no code
Run the existing harness with `recall_max_tokens=1000` (strategy cap already permits: min(1000, 2000) = 1000). Artifact: `results/wave3/rung1-budget-1000.json`. Decision: if faithfulness holds at parity with half the recall spend, 1000 becomes the chat default recommendation and the new reference for rung 2. If faithfulness collapses, budget stays 2000 and rung 2 attacks precision at full budget.

### Rung 2 (the centerpiece): transcript-anchored delta-recall (axon) + hybrid arm (gnomon)
The product goal: recall must stop being a fixed per-turn tax and become a cache-miss handler - spend on topic shifts, not on every turn. Mechanism: **the forwarded transcript is the dedup anchor** - no session-id, no server-side state.

- Task 2a - per-chunk telemetry (prereq, ships regardless): log per-request chunk-level data (chunk id/hash, raw score, staleness-adjusted score, strategy name, packed token estimate, dedup verdict once 2c lands) as a sidecar JSONL next to RecallRecord (`data_root/recall/chunks.jsonl`). No behavior change.
- Task 2b - hybrid arm in gnomon: new arm variant forwarding a recent window of K turns (K=2) with `include_context=true` and the surviving budget from rung 1. SessionTarget arm variant + runner support. This is the realistic deployment mode and the reference the delta-recall is measured on.
- Task 2c - delta-recall in `_retrieve_context` (axon, env-gated `AXON_DELTA_RECALL=1`): when the request carries forwarded history, dedup each retrieved candidate against the transcript content (normalized shingle/hash overlap above a structural cutoff = already known, drop it) BEFORE packing the budget. A follow-up turn whose retrieval is fully covered by the conversation injects nothing (recall cost ~0). Retrieval semantics unchanged when no history is forwarded (zero-history arm and Wave 1/2 callers untouched).

Measured run: hybrid arm with delta-recall on vs rung-1 reference AND vs the pure arms. Success shape: per-session recall spend concentrated on topic-shift turns (telemetry 2a shows the dedup verdicts), cumulative savings positive or near-positive, faithfulness gate holds. Artifact: `rung2-delta-recall.json`.

**VERDICT (2026-07-03): REVERTED as a config.** Measured: cumulative -1.329 [-1.805, -0.809], WORSE than rung 1 (-0.674); faithfulness held (axon 0.671). Telemetry: 0 of 401 chunks dropped across 90 dedup-active requests - lexical shingle dedup never fires because assistant answers PARAPHRASE vault content, they do not reproduce it (semantic coverage, lexical mismatch). The window alone only added cost. Deeper finding from the same telemetry: within-session chunk-hash reuse is median 0% / mean 11.8% - each turn retrieves genuinely different vault regions, so NO dedup mechanism (lexical, hash or semantic) has anything to deduplicate. The "AXON keeps re-sending the same context" premise is false; the per-turn cost is new content every turn. Code stays (env-gated off by default: telemetry dedup field + window_turns are useful infrastructure); the eval reference config remains rung 1 (budget 1000, window 0, delta off). Remaining honest levers: retrieval precision (rung 3 reranker, may enable budget 500) and need-based gating of referential turns in hybrid mode.

### Rung 3: reranker precision (axon)
Rerank stage in `_retrieve_context`: fetch wide (top_k=24), rerank (query, chunk) pairs with a cross-encoder served from the desktop box, keep top candidates by reranker score until the budget. Reranker scores, unlike bi-encoder cosine, DO separate relevance and admit a meaningful cutoff (naive cosine floors are dead by evidence). Model choice (bge-reranker-v2-m3 via TEI, or an Ollama-served alternative) decided at implementation time; latency budget <= 500ms per turn; env-gated (`AXON_RERANK=1`). Fixes the junk-retrieval problem (wrong answers on broad questions) and composes with delta-recall: fewer, better chunks in; known chunks deduped out. Artifact: `rung3-rerank.json`.

### Rung 4 (publication): final state runs the full runbook protocol
2x full run + stability replicate + validity checklist; propagation (README/METRICS swap) remains owner-gated. The published claim reports the curve, the crossover, and the ablation table (what each rung bought).

## Out of scope (deliberate)

- Naive score thresholds (killed by evidence, see above).
- Recall gating / delta-recall outside carryover (in the zero-history arm they starve the model).
- Session-id plumbing in the axon endpoint - the forwarded transcript is the anchor; server-side session state only if a future client cannot forward history.
- Any change to the Wave 2 measurement contract (arms, headline metric, gate) - fixes change AXON, not the ruler.
