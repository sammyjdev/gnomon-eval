# Design: score context coverage against the answer key, not against an opinion

- Date: 2026-08-31
- Relates to: gnomon-eval#68, `metron/judge-calibration/REPORT.md`, METRON
  `code-retrieval-roundtable` SPEC
- Destination of the numbers: **public claim**, so the instrument must pass its
  own gate before it measures anything.

## Problem

`context_precision` is judged by an LLM panel, and the panel does not agree with
itself in a way that survives changing the arm.

Measured 2026-08-31 across two arms, six candidate judges plus the three shipped
ones (`metron/judge-calibration/REPORT.md`):

- **Mean swing in correlation-to-consensus between two arms: 0.286** — the same
  order as the differences that would justify replacing a judge.
- `phi-4` returns 1.0 on all 30 cases of one arm (spread 0.000, no
  discrimination) and is the single best judge on the other (+0.708).
- `llama31-8b` moves from -0.117 to +0.647.

The mechanism is saturation. Where retrieved contexts are good, mean scores sit
between 0.76 and 1.00, variance collapses, and correlation destabilises. Where
they are poor (0.17-0.54) every judge correlates decently. **Inter-judge
agreement measures arm difficulty, not judge capability** — so no choice of
judge fixes it.

Meanwhile every `EvalCase` carries `expected_contexts`: textual anchors such as
`"class BaseTransport:"` or
`"public final class JsonArray extends JsonElement implements Iterable<JsonElement> {"`.
All 30 cases of both corpora have them populated. **`build_prompt` never passes
them.** The judge is asked for an opinion on relevance while the answer key sits
unused in the case file.

Scored without any model:

| metric | llamaindex-vector | aider-repomap | Cohen's d |
|---|---|---|---|
| `anchor_recall` | 0.703 | 0.170 | **+1.84** |
| 3-judge panel `context_precision` | 0.913 | 0.424 | +1.77 |

The deterministic metric separates the arms at least as sharply as three LLM
judges, at zero cost, with no latency (the panel averages 27s/case, outliers at
140s), and its correlation with the panel is +0.513 / +0.534 across the two arms.

Those two correlations are NOT comparable to the judges' 0.286: that is a swing
in correlation-to-consensus, a different quantity on a different pair of things.
An earlier draft set "a 0.02 difference" against it; the comparison was retracted
from `metron/judge-calibration/RESCORE.md` and is struck here too.

## Decision

**1. Anchor coverage becomes the primary metric for answer-key coverage,
computed with no model. It does not replace the judged `context_precision` as a
measure of relevance.** That qualifier is not decoration: the gate found
`anchor_recall` reproduces 4 of the 5 CI-separated panel verdicts in scope and
reverses none, which licenses it as a coverage metric — and says nothing about
the cases the panel could not separate, which is where relevance judgements
actually live. Two numbers, reported separately and never averaged:

- `anchor_recall` — fraction of a case's expected anchors present anywhere in the
  retrieved contexts.
- `anchor_precision` — fraction of retrieved contexts containing at least one
  anchor.

They move in opposite directions by design, and averaging them would hide
exactly the trade-off the benchmark exists to expose.

The worked example has to be stated carefully, because the obvious version of it
is wrong. `aider-repomap` scores 0.400 precision against 0.170 recall. It does
NOT do so by returning many short contexts of which a large share carry an
anchor: it returns **exactly one context per case, mean 12,591 characters** (30
cases, measured). Its 0.400 is therefore "12 of 30 cases had an anchor somewhere
in the single blob", and its 0.170 is "17% of all anchors were reached".

**`anchor_precision` is not comparable across arms that return different numbers
of contexts.** Its denominator is the arm's own retrieval depth k, so the metric
answers a different question at each k, and at k=1 it degenerates entirely:

    anchor_precision == 1.0 if recall > 0 else 0.0

which is `P(recall > 0)` once averaged over cases — a case-level hit rate
*coupled to* recall, not a precision trading off against it. Measured contexts
per case on the six rescorable arms: `aider-repomap` 1.0, `vector-sym-v1` 4.7,
`vector-sym-v2` 6.7, `llamaindex-vector` / `llamaindex-java` 8.0,
`graphify-java` 11.7. Read `anchor_precision` within an arm across corpora or
across revisions of the same retriever; do not rank arms by it.

**2. The judge keeps `faithfulness`.** It grades the answer against the contexts
and has no answer key, so subjectivity there is legitimate. This spec does not
change how `faithfulness` is asked.

**3. The panel is not changed.** No candidate judge is consistently better, and
the three shipped ones are the most stable across arms (swing 0.077 / 0.082 /
0.763). The cheapest costs $0.007 per run; a more expensive one buys noise.

**4. The judged `context_precision` stays, demoted to secondary.** It is what the
12 historical arms were scored with, and deleting it would erase the only bridge
to them.

## Architecture

`AnchorScorer` implements the existing judge contract and needs nothing else:

```python
class AnchorScorer:
    model_name = "anchor-scorer"

    def score(
        self, case: EvalCase, response: RagResponse, *, seed: int, run: int
    ) -> MetricScores: ...
```

Everything it reads is already on the objects the contract hands it —
`case.expected_contexts` and `response.contexts`. It makes no network call, so
`seed` and `run` are accepted and ignored: the function is deterministic by
construction, which is strictly stronger than the `deterministic_judge=True`
that the LLM judges only approximate.

Consequences of reusing the contract rather than adding a parallel path:

- It enters a panel as an ordinary `PanelMember`, so it inherits per-case scores,
  bootstrap CIs and aggregation with no change to `run_panel_eval`.
- `judge_runs=1` is sufficient and `judge_runs>1` is wasted work, not noise
  reduction.
- `StubJudge` is the precedent: a non-LLM implementation of the same contract
  already exists and the runner does not distinguish it.

Metric names live in `gnomon/metrics/names.py` alongside `V1_METRICS`, as
`ANCHOR_METRICS`, following the `STORY_COVERAGE` precedent of a metric set that
is deliberately outside the shared V1 judge prompt.

### Matching rule

An anchor matches when its whitespace-normalised form appears as a substring of
the whitespace-normalised context. Normalisation collapses runs of whitespace so
that reindentation does not break a match; nothing else is transformed.

### Empty inputs

A case with no `expected_contexts` cannot occur: `EvalCase` declares
`expected_contexts: list[str] = Field(min_length=1)`, so pydantic rejects it at
construction. The scorer needs no branch for it.

**A response with no contexts scores 0.0 on both metrics**, matching the
convention `OpenAICompatJudge` already enforces — it forces
`context_precision = 0.0` when `response.contexts` is empty, protected by three
tests (`test_empty_contexts_short_circuit_context_precision_to_zero` and
siblings).

An earlier draft of this spec excluded empty retrievals from `anchor_precision`
on the grounds that a zero denominator is undefined and that scoring 0.0 punishes
one failure twice. That reasoning was wrong in a way worth recording: excluding a
case from the aggregate *removes it from the mean*, which **benefits** the
retriever that returned nothing. Returning nothing must never score better than
returning something imperfect.

## The gate this must pass before any claim uses it

The judges failed on stability across arms, so that is the test this metric must
pass — and it is not assumed, it is measured on the six rescorable arms
(`code-retrieval-roundtable` ×2 over httpx/Python, `java-replication` ×4 over
gson/Java):

1. **Ordering stability.** Does anchor coverage rank the arms consistently within
   each corpus, and does it agree with the panel's verdicts where the panel
   separated arms by non-overlapping CIs?
2. **Cross-corpus stability.** The judges' failure mode was a 0.286 swing between
   two arms. The equivalent number for this metric must be computed and reported,
   not assumed to be small.
3. **Literalness bias, quantified.** Substring matching favours retrievers that
   return verbatim code and penalises those that summarise. The rescore of the
   six arms shows whether it changes any ordering; if it does, the metric is not
   fit for a public claim without a paraphrase-tolerant variant.

   An earlier draft offered "aider-repomap at 0.400 precision against llamaindex
   at 0.237, with 4× lower recall" as evidence of that bias. It is not: those two
   arms retrieve at k=1 and k=8, so per the caveat under decision 1 their
   `anchor_precision` values are not comparable, and at k=1 the 0.400 is a
   restatement of recall rather than an independent quantity. Only
   `anchor_recall` can carry this gate.

If the gate fails, the fallback is gnomon-eval#68 item 3: keep the judged metric
and fix how it is asked (pass `expected_contexts`, allow a short justification
before the score, use the hand-written rubrics in `judge/rubrics.py`). That is a
different spec.

## Out of scope

- **The six `graphify-vs-glyph` arms.** They generated contexts on the fly and
  never persisted them, so they cannot be rescored with any new metric without
  re-running the retrievers. This is the same defect AXON's compression
  telemetry had: the result was recorded and the input was not, so no case could
  be reconstructed. Worth fixing in METRON — every benchmark should persist
  `contexts/` — but not here.
- **The AXON adapter.** It is the reason this work exists, and it waits for the
  gate above to pass. Writing it against an instrument that has not been
  validated would reproduce the mistake this spec is correcting.
- **How `faithfulness` is prompted.** Real (the prompt forbids reasoning), and a
  separate change.

## What this does not establish

Agreement is not accuracy. Anchor coverage correlating with the panel at ~0.52
is consistent with both measuring the same wrong thing. What the deterministic
metric removes is judge variance, not measurement error — and a metric that is
stably wrong is more dangerous for a public claim than one that is visibly
noisy, because it looks trustworthy. The literalness-bias check in the gate is
the specific defence against that, and it is the one item most likely to fail.
