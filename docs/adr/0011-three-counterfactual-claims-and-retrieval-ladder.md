# ADR-011: Three counterfactual claims and retrieval ladder

**Date:** 2026-07-04
**Status:** Accepted

> **Amendment (2026-07-27 audit):** the *framework* (three named counterfactuals, never mixed) still stands and is followed in the runbooks. But the frozen measurement snapshot in this ADR (17 cases, 2026-07-04) is **superseded** — the dataset grew to N=34 and the live panel run in `docs/panel/initial-run.md` (2026-07-22) shows different results (faithfulness now fails the majority gate). Do NOT cite the old numbers; treat the runbook as the live source of truth for measured verdicts.

## Context

ADR-009 established that any "AXON saves tokens" claim needs a real
multi-turn counterfactual. ADR-010 then fixed the session-harness method for
that specific cost claim. What remained underspecified was the broader
language around "AXON saves/earns X": different published claims were mixing
different counterfactuals, and the retrieval stack itself still had unresolved
quality regressions from index composition, markdown skeleton chunks, and
dense-only search.

This ADR separates the claims by counterfactual, records which ruler belongs
to each one, and records the measured retrieval-ladder verdicts that define
the current best retrieval configuration. It also records negative results
explicitly so the team does not re-run dead ends that were already measured.

## Decision

ADR-011 defines a three-counterfactual framework for any published "AXON
saves/earns X" statement. Every claim must name its counterfactual and use the
matching ruler:

- Session curve. Counterfactual: re-sending the conversation transcript. This
  uses the Wave 2 session harness from ADR-010. Measured 2026-07-03:
  cumulative savings -0.674 [-1.259, -0.139] at recall budget 1000. In 10-turn
  sessions the arm costs more than transcript forwarding, per-turn parity is
  reached at turn ~9, and faithfulness reached parity. This number is tied to
  the session harness only and must be re-measured after the retrieval ladder
  at publication time.
- Real Claude Code usage. Counterfactual: reading each source file in full in
  a read/grep workflow. This uses chunk telemetry plus
  `axon scripts/recall_savings_report.py`. Every published number from this
  ruler must include the method note, because the claim is about actual tool
  usage relative to full-file reads, not about the session harness.
- Recall quality uplift. Counterfactual: no memory at all. This uses the Wave
  1 single-turn harness with A/B `include_context`. This is the cross-session
  capability claim and must be published as quality numbers, never as a token
  percentage.

ADR-011 also records the retrieval ladder verdicts measured on 2026-07-04 in
the Wave 1 harness over 17 cases with seed 42 and judge llama3.1:8b x8:

- Baseline, old index: faithfulness 0.711 [0.665, 0.752], context_precision
  0.752 [0.669, 0.831]. Root causes measured: the index was 97% dev-repo
  chunks versus 1.8% vault, the index was stale and a fresh rebuild found 2.9x
  more vault content, there were 2303 dev-plan artifact chunks, metadata
  skeleton chunks were present, and search was dense-only.
- Rung 3a, index hygiene via exclusions plus fresh rebuild: faithfulness 0.770
  [0.727, 0.814] - PROMOTED. This rung also found and fixed eval-artifact
  answer leakage into the index, and eval datasets are now excluded from
  indexing.
- Rung 3b, skeleton suppression via prose-ratio merge in the markdown
  chunker: context_precision 0.822 [0.752, 0.883], with faithfulness held -
  PROMOTED.
- Rung 3c, hybrid lexical via `tsvector 'simple'` plus GIN plus RRF behind
  env `AXON_HYBRID_SEARCH=1`: faithfulness 0.775 [0.735, 0.814] - PROMOTED.
  This is the best configuration.
- Rung 3d, cross-encoder reranker via in-process fastembed
  jina-reranker-v2-base-multilingual behind env `AXON_RERANK`: faithfulness
  0.748 [0.703], precision 0.760 [0.697] - REVERTED. It worsened both metrics,
  so the code remains env-gated off.

The retrieval gate status remains red under ADR-006. Faithfulness `ci_low` is
0.735 versus the threshold 0.75, a miss by 0.015. The residual gap is partly
retrieval quality and partly case variance at `n=17`. The recorded options are
to expand the case set, publish the documented near-miss, or run one bounded
rerank iteration.

ADR-011 records these negative results as dead ends:

- Absolute or relative cosine score thresholds are dead. They were measured
  twice, and scores in the 0.60-0.65 range do not separate junk from gold
  across queries.
- Delta-recall or dedup of any kind is dead. Assistant answers paraphrase
  vault content, lexical dedup dropped 0/401 cases, and within-session chunk
  reuse is median 0%, so the per-turn cost is genuinely new content.
- Cross-encoder reranking as currently wired is dead on this corpus, per rung
  3d.

## Consequences

**Upsides:**
- Published claims now have one named counterfactual each, which prevents the
  session-harness savings curve, real workflow telemetry, and quality uplift
  from being collapsed into one misleading number.
- The best current retrieval configuration is explicit: index hygiene,
  skeleton suppression, and hybrid lexical search are promoted, while the
  reranker stays off by default.
- Negative results are now part of the decision record, which reduces repeat
  work on cosine thresholds, dedup ideas, and the current reranker wiring.

**Downsides / trade-offs:**
- The headline becomes less convenient. There is no single universal "AXON
  saves X" number anymore because each claim needs its own counterfactual and
  method note.
- The current best retrieval stack still misses the ADR-006 gate on
  `faithfulness ci_low` by 0.015, so publication still carries a near-miss
  decision instead of a clean pass.
- Real Claude Code usage numbers require the mandatory method note every time,
  which adds publication discipline and removes room for shorthand summaries.

**Neutral / to watch:**
- The Wave 2 session number recorded here is a measured pre-ladder snapshot and
  must be re-measured at publication time after the promoted retrieval ladder
  is in place.
- The remaining gap may shrink more from a larger case set than from another
  retrieval tweak, because `n=17` leaves visible case variance in the CI.

## Alternatives considered

| Alternative | Why it was rejected |
|---|---|
| Keep publishing one generic "AXON saves X" number | It mixes incompatible counterfactuals and obscures what was actually measured. ADR-009 and ADR-010 already require the session claim to be grounded in a specific harness. |
| Keep the old dense-only retrieval stack and publish around the regressions | The measured root causes were concrete and fixable: stale index contents, dev-plan artifact chunks, metadata skeleton chunks, vault underrepresentation, and dense-only retrieval. |
| Use cosine score thresholds as the quality filter | Measured twice and rejected because 0.60-0.65 scores do not distinguish good from bad retrieval across queries on this corpus. |
| Add delta-recall or dedup logic to cut retrieval cost | Measured and rejected because lexical dedup dropped 0/401 and within-session chunk reuse is median 0%, so there is no material duplicate mass to remove. |
| Promote the cross-encoder reranker | The measured rung 3d result worsened both faithfulness and precision on this corpus, so promotion would be evidence-free. |
| Keep using the retired 52.3% projection as the top-line framing | That framing collapses multiple claim types into one savings number and relies on a retired projection rather than the measured rulers defined here. |

## Relations

- ADR-011 requires ADR-009.
- ADR-011 requires ADR-010.
- ADR-011 relates to ADR-004.
- ADR-011 relates to ADR-006.
- ADR-011 relates to ADR-008.
- ADR-011 requires AXON `AXON_HYBRID_SEARCH` and the index hygiene exclusions.
- ADR-011 supersedes the single-number savings framing of the retired 52.3%
  projection.
