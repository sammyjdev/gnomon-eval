# ADR-0012: Three-Judge Panel (Distinct Families, Report All, Majority Gates)

**Date:** 2026-07-21
**Status:** Accepted (2026-07-21)

## Context

Issue #4 originally proposed a second judge to measure how much a verdict
depends on the judging model. The owner expanded the decision (2026-07-21,
recorded on #4): a two-judge disagreement is only ambiguity - with three
judges, disagreement becomes structured signal (a 2-1 split identifies the
dissenter and the per-family bias pattern). Convergent evidence from the
harness-bench work: the same seeded defect (`backward_clock`) produced 9 of
14 classified failures across 4 different models - family-level blind spots
are real, and decorrelation by construction is the only defense measured to
work. External literature agrees: Han et al. 2026 audits judge position bias
by reporting judgments separately, never blended.

## Decision

1. **Panel composition: three models from distinct vendor families of the
   same generation.** No two panel members may share a vendor family. Same
   generation avoids capability imbalance masquerading as disagreement.
2. **Measurement reports all three verdicts.** Metric results are reported
   per judge, side by side, plus disagreement statistics (per-case deltas,
   pairwise correlation). A cross-judge mean is never the published number -
   averaging destroys exactly what the panel exists to measure (RNF-03).
3. **Gates use an explicit 2-of-3 majority.** Where a single pass/fail
   verdict is required (quality gates), the rule is majority, stated
   separately from reporting. Votes are public; the ruling is the majority.
4. **Impartiality mechanics:** all three judges consume the same canonical
   prompt/parse artifacts (ADR section H, issue #47), temperature 0, and
   `judge_runs=1` per deterministic judge (#49). Prompt divergence between
   panel members is a bug, not a knob.
5. **Membership is earned by screening, not opinion.** Candidates pass the
   capacity bar (roadmap B4: valid JSON, no hallucinated keys, schema
   compliance over N probe cases) before joining the panel. A judge that
   fails the bar is excluded regardless of family (precedent: phi3:mini's
   `faithlessness` key failed an entire run, fail-closed).
6. **Offline-first trade-off, declared:** the full panel requires network
   for hosted families. The single local judge remains the documented
   offline fallback; the panel is the publication-grade mode. Single-judge
   results must be labeled as such.

## Consequences

- **Positive:** disagreement becomes measurable signal; family bias is
  visible instead of absorbed; published numbers carry an honesty upgrade
  (three independent verdicts beat one opaque blend); gating keeps a crisp
  deterministic rule.
- **Cost:** 3x judge calls per case per run - with deterministic judges and
  `judge_runs=1`, a 17-case run is ~51 calls on free rails; trivial. Judge
  cache granularity already keys on judge_model, so panel members cache
  independently.
- **Surface changes:** EvalReport/reporting gain per-judge results and
  disagreement stats; config gains a panel declaration; contract doc gains
  the panel semantics. Existing single-judge configs remain valid (panel is
  additive, not a breaking change).
- **Selection benchmark required** before wiring: screen free-rail
  candidates (distinct families, same generation - e.g. Google/DeepSeek/
  OpenAI-OSS class, exact models verified live at screening time) through
  the B4 bar, then pin the initial panel in config with the screening
  evidence linked.

## Execution plan (post-acceptance)

Issue #4 is rescoped/split into: (a) panel infra (config + runner + report
schema + disagreement stats), (b) capacity-screening harness (B4), (c)
initial panel selection run + pinning. TDD throughout; contract doc updated;
existing 17-case dataset is the screening corpus.

## Revisit triggers

1. Free rails stop carrying three viable same-generation families → drop to
   the best two + declared limitation, or fund one paid seat.
2. Disagreement statistics stay ~zero across many runs → the panel is
   redundant for this corpus; consider reverting to single judge + periodic
   panel audits instead of always-on.
