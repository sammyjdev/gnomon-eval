# RAGAS Completion Roadmap

**Date:** 2026-07-13
**Status:** Approved direction — pending distillation into roadmap/issues
**Provenance:** Gap analysis of the rag-agent-101 course material against
GNOMON (2026-07-13), part of the four-repo sweep (axon, forge, gnomon, glyph)
whose axon/forge half was cross-validated by two independent deep-research
reports (Perplexity, Gemini, 2026-07-12). Sibling specs:
`axon/docs/superpowers/specs/2026-07-13-retrieval-eval-precision-roadmap.md`
and `~/.claude/agents/forge/docs/loop-quality-roadmap.md`.

## Goal

Complete the RAGAS metric set GNOMON already half-implements, and turn gate
failures into actionable verdicts. The portfolio-level finding: AXON measures
recall without precision; GNOMON measures precision without recall. Each side
is flying on half the retrieval-quality pair — this spec closes GNOMON's half.

## Item RC-1: Context recall — complete the retrieval pair

**Problem.** `EvalCase.expected_contexts` exists and is collected in every
case, but the v1 judge ignores it. `context_precision` alone measures noise,
not completeness. Half the retrieval signal is thrown away for free.

**Direction.** Wire `expected_contexts` into the judge: a `context_recall`
metric (of the expected contexts, how many did retrieval surface?). Judge
prompt + `metrics/names.py` + runner pass-through; `domain/models.py` already
has the field. Aligns with Roadmap A2. Effort: S.

## Item RC-2: Diagnostic branching as a first-class report field

**Problem.** The gate reports which metric's `ci_low` missed threshold; the
human still derives "which lever to pull" by hand. GNOMON's own
`ai-engineering-gap-review.md` flagged this failure-taxonomy gap
independently — two readings converge on the same hole.

**Direction.** Given precision + recall + faithfulness, emit an explicit
verdict in `reporting/report.py`: low recall → retrieval problem; high recall
+ low faithfulness → generation problem; high recall + high faithfulness +
low precision → retrieval noise. Pure reporting logic over already-computed
metrics, no new judge calls. Depends on RC-1 for the three-way branch; a
two-way interim (precision vs faithfulness) is possible earlier. Effort: S.

## Item RC-3: Answer relevancy — the fourth RAGAS metric

**Problem.** A fully faithful but off-topic answer currently passes the RAG
harness. Lower urgency for the ChatEval/lina harness (per-case GEval criteria
already cover on-topic-ness implicitly).

**Direction.** With-reference variant (against `expected_answer`, already
ground truth elsewhere) is the cheaper, more consistent option. Same shape as
RC-1: judge prompt/rubric + `metrics/names.py` + runner wiring. Effort: S/M.

## Item RC-4: Golden-set drift marker

**Problem.** The "no case whose answer changed recently" rule exists only as
prose in `datasets/second_brain/README.md`, enforced by eyeballing. A stale
case silently degrades threshold recalibration and any published A/B number.

**Direction.** Optional `source_updated_at`/`reviewed_at` field on `EvalCase`
(backward compatible) + a small `scripts/check_dataset_drift.py` that flags
cases whose backing source changed since authoring. Effort: S.

## Item RC-5: Judge calibration spot-check (process, not code)

**Problem.** The manual audit that caught a real GEval bug (a correct
WhatsApp reply scored 0.0 because auto-generated steps hallucinated a JSON
requirement) lives as tribal knowledge in a `rubrics.py` docstring.

**Direction.** A short checklist in `docs/DEVELOPMENT_LOOP.md`: before
promoting a recalibrated gate threshold, hand-check ~10 judge scores against
reasons/transcripts. Explicitly NOT an automated judge-agreement pipeline
(see rejections). Effort: S.

## Deferred

**Per-query-class slicing.** Real, but `second_brain` has 15-20 cases —
slicing destroys the bootstrap CI's n. The 206-case lina suite already gets a
coarse version via its three separately-gated metrics + severity re-labeling.
Trigger: a dataset large enough that CI width stops dominating the signal.

## Rejections (do not revisit without new evidence)

- **Adopting the `ragas` package** — GNOMON's case-level bootstrap is
  stricter than ragas defaults, and the dependency would violate
  RNF-02/ADR-001 dependency direction. Add the two missing metrics by hand.
- **Automated judge-agreement / Cohen's-kappa pipeline** — solo maintainer,
  low cadence; the one real judge bug was caught by reading one transcript.
  RC-5's checklist first; revisit only if judge-caused false gate failures
  recur.
- **Temporal dashboard / history persistence / multi-target comparison** —
  already correctly deferred by GNOMON's own roadmap (A3/A4/A5); the course
  changes nothing.
- **Retrieval techniques (HyDE, multi-query, semantic chunking, vector DB)**
  — AXON-side concerns; the external evaluator does not implement retrieval.

## Ruler-collision rule (publication discipline, no code)

AXON's PREC-1 (`retrieval_eval` precision: deterministic golden fixture, code
retrieval, in-repo, no judge) and GNOMON's `context_precision` (LLM-judged,
end-to-end, bootstrap CI) are incomparable rulers that share a name. Never
report them side by side as interchangeable; name the ruler in every
publication ("AXON retrieval_eval precision" vs "GNOMON end-to-end
context_precision"). RC-1/RC-2 use GNOMON's own vocabulary
(`context_recall`), not AXON's (`recall_first`/`recall_after`).

## Ordering

RC-1 → RC-2 is the value chain. RC-3, RC-4, RC-5 are independent. Nothing
here blocks the existing Roadmap A-items.
