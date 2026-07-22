# Initial panel evaluation run (ADR-0012 c, issue #55)

**Date:** 2026-07-22. **Dataset:** `datasets/second_brain/cases.json` (N=34,
owner-validated). **Target:** AXON `serve-http` on `localhost:8765`
(`openai_compat` target, same endpoint as the decisive single-judge A/B),
arms ON (`include_context=true`) and OFF. **Eval:** `judge_runs=1`,
`deterministic_judge=true`, seed 42, 95% CI. **Panel:** the three pinned
`config/panel.toml` members. **Raw evidence:**
`runs/2026-07-22-initial-run-{on,off}.json`.

Responses are freshly generated per arm (the target is a live RAG stack, not
a replay), so judge verdicts here are over the *same* responses within the
run, but not the same responses as the decisive single-judge A/B of
2026-07-21.

## Results (mean [95% CI], N=34)

| Judge (family) | faith ON | faith OFF | ctx_prec ON | ctx_prec OFF |
|---|---|---|---|---|
| Llama-3.1-8B (meta) | 0.749 [0.668, 0.806] | 0.535 [0.441, 0.621] | 0.854 [0.771, 0.913] | 0.000 |
| GLM-4.6 (zhipu) | 0.382 [0.235, 0.559] | 0.353 [0.206, 0.529] | 0.825 [0.777, 0.867] | 0.000 |
| Mistral-Nemo-12B (mistral) | 0.684 [0.553, 0.812] | 0.044 [0.000, 0.103] | 0.665 [0.535, 0.791] | 0.000 |

OFF-arm `context_precision` is deterministically 0.0 for every judge
(empty contexts, metrics-scoped prompting from #62 working as designed).

## Majority gate (thresholds: faithfulness ci_low >= 0.75, ctx_prec ci_low >= 0.70)

- **context_precision: PASS** (2/3 - Llama 0.771, GLM 0.777; Mistral 0.535 fails).
- **faithfulness: FAIL** (0/3 - Llama 0.668, GLM 0.235, Mistral 0.553).

## Disagreement

Pairwise Pearson (per-case scores, ON arm): faithfulness 0.30/0.48/0.48;
context_precision 0.06/0.44/0.30. Per-case deltas hit 0.8-1.0 on roughly a
third of the cases for faithfulness. Full per-case detail in the run JSONs.

## Reading (per ADR-0012: all verdicts reported, never averaged)

- **The retrieval-relevance effect is panel-robust.** All three families score
  ON context_precision far above the OFF floor of 0.0, and the majority
  clears the pre-registered gate. This is the strongest triangulated claim.
- **The faithfulness effect direction is unanimous, its magnitude is
  judge-dependent.** Llama (+0.21) and Mistral (+0.64) show CI-separated
  lifts; GLM-4.6 is harsh on both arms (0.35 -> 0.38, overlapping CIs) - it
  does not credit the generated answers as grounded regardless of retrieval.
  Under the majority rule no judge clears the 0.75 bar on this run's
  responses (the decisive single-judge run had cleared it at 0.757 with
  Llama on a different response draw).
- **Consequence for published claims:** context_precision numbers may cite
  the panel gate; faithfulness numbers must be scoped to the judge that
  produced them (single-judge, named) or presented as an effect-size claim,
  not a panel-gated one.

Follow-ups (not blocking #55): per-case review of GLM-4.6's harsh
faithfulness verdicts to decide rubric vs judge error; stability repeat of
the panel run before promoting any panel-gated faithfulness claim.
