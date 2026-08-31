# Wave 3 Extended - Retrieval Quality + Real-Usage Accounting

**Goal:** Fix the measured retrieval friction points (inverted index, skeleton chunks, no score separation, no lexical arm), quantify what AXON actually saves in real Claude Code usage, and publish three defensible numbers - each with its explicit counterfactual - replacing the retired 52.3%.

**Execution model:** Claude orchestrates, Codex CLI executes (see the `codex-executor` skill). Every retrieval change is validated against the Wave 1 single-turn harness (17 cases, recall/faithfulness) and the live probes before promotion; session-curve re-measured at the end.

## Evidence base (2026-07-03/04, all measured)

- Index inversion: 12,189 chunks total; 97% from `~/dev` repos, **1.8% from the vault** (223 chunks); ctx `career` has 3 chunks; 2,303 chunks are dev-plan artifacts. Broad queries drown in dev-doc noise (4/9 junk in the density-gate probe, right answer at rank 5, dec-040 absent).
- Skeleton chunks: exported vault notes carry metadata sections (status/repo/files) that become budget-wasting chunks (dec-039 probe).
- Score band 0.60-0.65 does not separate junk from gold (bi-encoder ceiling); cosine thresholds are dead (measured twice).
- No lexical arm: index is dense-only; exact-term queries ("density gate") have no BM25/tsvector path.
- Session curve (Wave 2/3 harness): budget 1000 accepted (-0.674 cumulative, faithfulness up); delta-recall dead (0/401 drops, within-session chunk reuse median 0%).
- Claude Code real usage (14d, 70 sessions): AXON MCP in 27% of sessions, ~21.6k tokens one-shot, search_code ~1k tok/call - no emergency, but no savings NUMBER either.
- Path inconsistency: http endpoint forces CODE_ANALYSIS -> strategy `balanced`; the MCP path classified the same query DEEP_REASONING -> `deep` (different budgets for the same question).
- Embedder chain first hop is LOCAL M1 Ollama (`AXON_OLLAMA_LOCAL_HOST` default 127.0.0.1) for bge-m3 - unvalidated latency/coupling.

## The three claims this wave produces

1. **Session curve** (counterfactual: re-sent conversation) - Wave 2 harness, re-measured after rungs.
2. **Real-usage savings** (counterfactual: Read/grep of whole files) - Axis B accounting.
3. **Recall quality uplift** (counterfactual: no memory at all) - Wave 1 harness numbers, positioned as the cross-session capability claim (not a token percentage).

## Task ladder (each rung: implement -> measure -> keep/revert)

Branches: axon work stacks on `feat/session-savings-wave2` (PR #50); gnomon on `feat/session-savings-harness` (PR #3). Orchestrator commits; Codex never touches git.

| # | Task | Repo | Executor | Model | Effort | Rationale |
|---|------|------|----------|-------|--------|-----------|
| T1 | Index hygiene policy + A/B build: exclusion rules for dev-plan artifacts (`**/docs/superpowers/plans/**`, implementation docs), full-vault indexing into side table `embeddings_ablation` (scout confirmed `PgVectorStore(table=...)` + env knobs make this direct) | axon | codex | gpt-5.5 | medium | Config+script work with existing patterns, but scope decisions are load-bearing |
| T2 | Rung 3a measurement: Wave 1 harness + density-gate/GLYPH probes against old vs new table; promotion decision | - | orchestrator | - | - | Measurement is never delegated |
| T3 | Skeleton-chunk suppression in `md_chunker`: prose-ratio heuristic (metadata/list-only sections skipped or merged), TDD on dec-039-style fixtures | axon | codex | gpt-5.5 | medium | Localized chunker change, clear fixtures |
| T4 | Reranker stage: wide fetch (top_k=24) + cross-encoder rerank served from the desktop box, env-gated `AXON_RERANK=1`, latency budget <= 500ms/turn; model choice validated live (bge-reranker-v2-m3 via Ollama/TEI - verify per model-facts before asserting) | axon | codex | gpt-5.5 | **high** | Integration + latency + fallback semantics; the only fix for the 0.60-0.65 band |
| T5 | Rung 3c measurement + budget-500 trial (precision may enable halving the budget again) | - | orchestrator | - | - | - |
| T6 | Lexical arm: tsvector column + GIN index + RRF merge with dense results (Postgres-native hybrid) | axon | codex | gpt-5.5 | **high** | Schema+query change; exact-term recall ("density gate") |
| T7 | Strategy unification: same query must resolve the same retrieval strategy on http and MCP paths (parametrize, document) | axon | codex | gpt-5.4 | medium | Mechanical once the decision is written in the brief |
| T8 | Telemetry file_path + Axis B accounting: add `file_path` to ChunkRecord (local telemetry, owner-approved); script computing per-call counterfactual (returned tokens vs full-file Read tokens) over chunks.jsonl + transcript cross-check | axon + analysis | codex (code) / orchestrator (analysis) | gpt-5.4 | medium | Additive telemetry + a deterministic script |
| T9 | Embedder chain validation: measure bge-m3 embed latency local M1 vs desktop Ollama; point `AXON_OLLAMA_LOCAL_HOST` at the faster/stabler host; document | - | orchestrator | - | - | Probe + env change, no code |
| T10 | Referential-turn query enrichment (query = last turn + short thread recall) - ONLY if T2/T5 show referential turns still failing | axon | codex | gpt-5.5 | high | Deferred twice; enters only with evidence |
| T11 | ADR: three-counterfactual claim framework + cross-session positioning + rung verdicts (incl. negative results: cosine thresholds, delta-recall) | gnomon | codex | gpt-5.4 | medium | Content fully enumerated by then |
| T12 | Final session-curve re-measurement + runbook protocol (2x + stability) + propagation checklist | - | orchestrator + owner | - | - | Owner-gated publication |

## Acceptance gates

- Retrieval rungs (T1/T3/T4/T6): Wave 1 harness recall/faithfulness must improve or hold vs previous rung AND the two probe queries must rank a relevant chunk top-3; regression -> revert.
- Session rungs (T5/T12): cumulative improves, quality gate passes, axon faithfulness not below previous CI low.
- Axis B (T8): report states counterfactual explicitly; no number without method note.
- xhigh escalation: any codex task failing review on a LOGIC error resumes via `codex exec resume` with `model_reasoning_effort=xhigh`.

## Ladder verdicts (2026-07-04, measured)

- T1/T2 rung 3a PROMOTED: fresh clean index; faith 0.711 [0.665] -> 0.770 [0.727]; found and purged eval-artifact answer leakage (datasets/ now excluded from indexing).
- T3 rung 3b PROMOTED: precision 0.783 -> 0.822 [0.752]; dec-039 rationale surfaces instead of its metadata skeleton.
- T6 rung 3c PROMOTED as best config (AXON_HYBRID_SEARCH=1): faith 0.775 [0.735]; precision 0.792 [0.716]. Exact-term golden set: hit@3 2/10 -> 3/10.
- T4 rung 3d REVERTED: in-process jina-reranker-v2 worsened both metrics (faith 0.748 [0.703], precision 0.760 [0.697]); AXON_RERANK stays off; code kept env-gated. Reordered ahead of nothing - measured after T6 per the zero-infra-first decision.
- T7 shipped: strategy selection deterministic and identical on http/MCP/CLI paths, zero LLM cost.
- T9 done: bge-m3 on local M1 kept (29ms/chunk, no desktop coupling).
- Gate status: faith ci_low 0.735 vs threshold 0.75 - red by 0.015. The residual gap is n=17 case-variance as much as retrieval quality; options recorded: expand case set, publish documented near-miss, or one bounded rerank iteration (strip breadcrumbs pre-scoring).

## Validation map (friction point -> instrument -> pass criteria)

| Friction point | Instrument | Metric | Pass criteria |
|---|---|---|---|
| Index inversion (97% dev / 1.8% vault) | (a) SQL recount on the A/B table; (b) Wave 1 harness old-vs-new table; (c) the 2 live probes | vault share, ctx coverage; recall/faithfulness CI; probe ranks | vault fully indexed (career >> 3 chunks); harness recall improves or holds; relevant chunk in top-3 on both probes |
| Skeleton/metadata chunks | (a) chunker unit tests on dec-039-style fixtures (prose-ratio); (b) probes: the RATIONALE chunk of dec-039/040 must surface | prose ratio; probe content | metadata-only sections never emitted as standalone chunks; rationale chunk retrieved where the skeleton chunk used to be |
| Score band 0.60-0.65 has no separation | before/after reranker on the probes + Wave 1 harness; latency probe | junk-vs-gold score gap; recall CI; rerank p95 latency | gold outranks junk on both probes; recall improves; p95 <= 500ms/turn measured on smoke |
| No lexical arm (exact-term queries) | NEW mini golden set: ~10 exact-term queries ("density gate", "dec-040", "AXON_MAX_PRE_SEND_TOKENS"...) run dense-only vs hybrid | hit@3 per query | hybrid strictly >= dense on every query, > on the term queries; no regression on the semantic 17 |
| http vs MCP strategy mismatch | contract test: same query resolves the same strategy on both paths; chunk telemetry `strategy` field cross-checked | strategy name + effective budget | test green; telemetry shows one strategy per query across paths |
| Embedder chain on local M1 | latency probe: embed batch of 100 chunks M1 vs desktop Ollama | p95 per batch, failure rate | pick the faster/stabler host; full-vault index time acceptable (T1 depends on it) |
| Real-usage savings unknown (Axis B) | method validation first: hand-compute the Read counterfactual for 5 real search_code calls, compare with the script; then 14d aggregate | tokens returned vs full-file Read tokens per call | script matches hand computation within 5%; published number carries the method note |
| Referential turns (deferred T10) | per-turn breakdown of the session curve + faithfulness, referential turn indices marked in the dataset README; chunk telemetry scores on those turns | per-turn faithfulness delta; retrieved-chunk relevance on referential turns | T10 enters ONLY if post-3a-3d referential turns still show junk retrieval or depressed faithfulness; otherwise stays out |
| Cross-session value (no savings counterfactual) | Wave 1 harness IS the instrument (A/B include_context on/off = with/without memory) | recall + faithfulness uplift | published as capability/quality claim in T11's ADR, never as a token percentage |
| Index drift (regression after the wave) | permanent check: vault-share + ctx-coverage assertions added to `pb doctor` (or runbook checklist) | chunk counts per source/ctx | doctor/runbook flags inversion before it reaches 97% again |
| Desktop GPU contention (measurement hygiene) | pre-run probe (2-token generation <= 8s) before every measured run; monitor-based relaunch | probe latency | no measured run starts against a contended box; timeouts never retried blind |

## Out of scope (deliberate, evidence-backed)

- Cosine score thresholds (dead: measured twice).
- Dedup/delta-recall of any kind (dead: 0/401 drops, median 0% chunk reuse).
- Embedder swap (T-last only if everything above fails to move recall; bge-m3 dense is not the bottleneck the evidence points at).
- Session-id server state (transcript remains the only anchor if ever needed).
