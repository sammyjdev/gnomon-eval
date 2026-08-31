# Anchor Scorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score context coverage against each case's `expected_contexts` with no model, then validate it on six already-scored arms before any claim uses it.

**Architecture:** `AnchorScorer` implements the existing judge contract (`score(case, response, *, seed, run) -> MetricScores`), so it joins a panel as an ordinary `PanelMember` and inherits per-case scores, CIs and aggregation with no change to `run_panel_eval`. `StubJudge` is the precedent for a non-LLM implementation of that contract. Validation lives in METRON and rescores the six arms whose contexts were persisted.

**Tech Stack:** Python 3.11+, pydantic v2, pytest. Repos: `~/dev/tools/gnomon-eval` (Tasks 1-3), `~/dev/tools/metron` (Task 4).

**Spec:** `docs/superpowers/specs/2026-08-31-anchor-scorer-design.md`

## Global Constraints

- Tests run from the repo root: `python3 -m pytest tests/ -q -p no:rerunfailures` (the rerunfailures plugin binds a socket, which the sandbox denies).
- `EvalCase.expected_contexts` is `Field(min_length=1)` — an empty answer key cannot occur and needs no branch.
- An empty `response.contexts` scores **0.0 on both anchor metrics**, matching `OpenAICompatJudge`, which forces `context_precision = 0.0` in that case.
- `anchor_recall` and `anchor_precision` are reported separately and **never averaged** — they move in opposite directions by design.
- The scorer makes no network call. `seed` and `run` are accepted and ignored.
- Do not change the shipped panel, and do not change how `faithfulness` is prompted. Both are out of scope per the spec.
- Metric name strings live only in `gnomon/metrics/names.py`; no literal `"anchor_recall"` anywhere else in `src/`.

---

### Task 1: Anchor matching, as a pure function

**Files:**
- Create: `src/gnomon/metrics/anchors.py`
- Create: `tests/unit/test_anchors.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `normalise(text: str) -> str`, `anchor_hits(anchors: list[str], contexts: list[str]) -> list[str]`, `anchor_recall(anchors: list[str], contexts: list[str]) -> float`, `anchor_precision(anchors: list[str], contexts: list[str]) -> float`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_anchors.py
import pytest

from gnomon.metrics.anchors import anchor_hits, anchor_precision, anchor_recall, normalise


def test_normalise_collapses_whitespace_runs() -> None:
    assert normalise("class  Foo:\n    pass") == "class Foo: pass"


def test_anchor_matches_across_reindentation() -> None:
    """Reindented code must still match - that is the only transformation."""
    assert anchor_hits(["class Foo:"], ["        class    Foo:"]) == ["class Foo:"]


def test_anchor_does_not_match_a_paraphrase() -> None:
    """Documented limitation: substring matching is literal (spec, gate item 3)."""
    assert anchor_hits(["class Foo:"], ["Foo is defined as a class"]) == []


def test_recall_is_the_fraction_of_anchors_present() -> None:
    anchors = ["a()", "b()", "c()"]
    contexts = ["def a(): ...", "def c(): ..."]
    assert anchor_recall(anchors, contexts) == pytest.approx(2 / 3)


def test_recall_counts_an_anchor_once_however_often_it_appears() -> None:
    assert anchor_recall(["a()"], ["def a(): ...", "def a(): ...", "def a(): ..."]) == 1.0


def test_precision_is_the_fraction_of_contexts_carrying_an_anchor() -> None:
    contexts = ["def a(): ...", "unrelated prose", "def b(): ...", "more prose"]
    assert anchor_precision(["a()", "b()"], contexts) == pytest.approx(0.5)


def test_an_anchor_spanning_two_contexts_is_not_a_hit() -> None:
    """Anchors are matched per context; a split anchor was never retrieved whole."""
    assert anchor_hits(["class Foo(Bar):"], ["class Foo(", "Bar):"]) == []


def test_empty_contexts_score_zero_on_both() -> None:
    """Matches OpenAICompatJudge: an empty retrieval is 0.0, never excluded."""
    assert anchor_recall(["a()"], []) == 0.0
    assert anchor_precision(["a()"], []) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_anchors.py -q -p no:rerunfailures`
Expected: FAIL — `ModuleNotFoundError: No module named 'gnomon.metrics.anchors'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/gnomon/metrics/anchors.py
"""Context coverage measured against a case's expected_contexts.

The judged context_precision could not rank arms stably: mean swing in
correlation-to-consensus across two arms was 0.286, because where contexts are
good every case scores near the ceiling and correlation destabilises. These two
functions measure the same thing against the answer key that was always in the
case file, deterministically and at no cost.

Matching is literal, by design and with a known cost: a context that paraphrases
an anchor scores nothing, which favours retrievers returning verbatim code. See
the spec's gate item 3.
"""

from __future__ import annotations


def normalise(text: str) -> str:
    """Collapse whitespace runs so reindentation does not break a match."""
    return " ".join(text.split())


def anchor_hits(anchors: list[str], contexts: list[str]) -> list[str]:
    """Anchors found whole inside at least one context, in the anchors' order."""
    normalised_contexts = [normalise(context) for context in contexts]
    return [
        anchor
        for anchor in anchors
        if any(normalise(anchor) in context for context in normalised_contexts)
    ]


def anchor_recall(anchors: list[str], contexts: list[str]) -> float:
    """Fraction of expected anchors the contexts reached."""
    if not anchors:
        return 0.0
    return len(anchor_hits(anchors, contexts)) / len(anchors)


def anchor_precision(anchors: list[str], contexts: list[str]) -> float:
    """Fraction of retrieved contexts carrying at least one anchor.

    Zero contexts scores 0.0 rather than being excluded: excluding a case
    removes it from the mean, which would reward returning nothing.
    """
    if not contexts:
        return 0.0
    normalised_anchors = [normalise(anchor) for anchor in anchors]
    useful = sum(
        1
        for context in contexts
        if any(anchor in normalise(context) for anchor in normalised_anchors)
    )
    return useful / len(contexts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_anchors.py -q -p no:rerunfailures`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gnomon/metrics/anchors.py tests/unit/test_anchors.py
git commit -m "feat(metrics): measure context coverage against the case's answer key"
```

---

### Task 2: Metric names

**Files:**
- Modify: `src/gnomon/metrics/names.py`
- Create: `tests/unit/test_anchor_metric_names.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `ANCHOR_METRICS: tuple[str, ...] = ("anchor_recall", "anchor_precision")`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_anchor_metric_names.py
def test_anchor_metrics_are_named_once_and_ordered() -> None:
    from gnomon.metrics.names import ANCHOR_METRICS

    assert ANCHOR_METRICS == ("anchor_recall", "anchor_precision")


def test_anchor_metrics_are_not_part_of_the_judged_v1_set() -> None:
    """They are computed, not prompted - the V1 judge must never be asked for them."""
    from gnomon.metrics.names import ANCHOR_METRICS, V1_METRICS

    assert not set(ANCHOR_METRICS) & set(V1_METRICS)


def test_no_source_file_hardcodes_an_anchor_metric_string() -> None:
    """names.py is the single source of truth (RF-05), as it is for V1_METRICS.

    Matches the quoted string, not the bare identifier: `anchor_recall` is also
    a function name in metrics/anchors.py and appears in every import of it.
    """
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "src" / "gnomon"
    offenders = [
        str(path.relative_to(src))
        for path in src.rglob("*.py")
        if path.name != "names.py"
        and ('"anchor_recall"' in path.read_text(encoding="utf-8")
             or "'anchor_recall'" in path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_anchor_metric_names.py -q -p no:rerunfailures`
Expected: FAIL — `ImportError: cannot import name 'ANCHOR_METRICS'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/gnomon/metrics/names.py`:

```python
# Deterministic context-coverage metrics (anchor scorer). Separate from
# V1_METRICS on purpose: they are computed from EvalCase.expected_contexts, not
# asked of a judge, and they must never enter the shared V1 judge prompt.
# Order is the report/display order. Never average the two - they move in
# opposite directions by design.
ANCHOR_METRICS: tuple[str, ...] = ("anchor_recall", "anchor_precision")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_anchor_metric_names.py -q -p no:rerunfailures`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gnomon/metrics/names.py tests/unit/test_anchor_metric_names.py
git commit -m "feat(metrics): name the anchor metrics in the one place names live"
```

---

### Task 3: AnchorScorer on the judge contract

**Files:**
- Create: `src/gnomon/judge/anchor_scorer.py`
- Create: `tests/unit/test_anchor_scorer.py`

**Interfaces:**
- Consumes: `anchor_recall`, `anchor_precision` from Task 1; `ANCHOR_METRICS` from Task 2.
- Produces: `AnchorScorer` with `model_name = "anchor-scorer"` and `score(case: EvalCase, response: RagResponse, *, seed: int, run: int) -> MetricScores`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_anchor_scorer.py
from gnomon.domain.models import EvalCase, MetricScores, RagResponse
from gnomon.judge.anchor_scorer import AnchorScorer
from gnomon.metrics.names import ANCHOR_METRICS

CASE = EvalCase(
    id="c1",
    question="where is Foo defined?",
    expected_answer="in foo.py",
    expected_contexts=["class Foo:", "class Bar:"],
)


def _response(contexts: list[str]) -> RagResponse:
    return RagResponse(answer="a", contexts=contexts, total_tokens=0, latency_ms=0.0)


def test_scores_exactly_the_anchor_metrics() -> None:
    scores = AnchorScorer().score(CASE, _response(["class Foo:"]), seed=42, run=0).scores
    assert set(scores) == set(ANCHOR_METRICS)


def test_returns_metric_scores_so_it_fits_the_panel() -> None:
    result = AnchorScorer().score(CASE, _response(["class Foo:"]), seed=42, run=0)
    assert isinstance(result, MetricScores)


def test_half_the_anchors_found_is_half_recall() -> None:
    scores = AnchorScorer().score(CASE, _response(["class Foo:"]), seed=42, run=0).scores
    assert scores["anchor_recall"] == 0.5
    assert scores["anchor_precision"] == 1.0


def test_empty_contexts_score_zero_on_both() -> None:
    scores = AnchorScorer().score(CASE, _response([]), seed=42, run=0).scores
    assert scores == {"anchor_recall": 0.0, "anchor_precision": 0.0}


def test_seed_and_run_do_not_change_the_score() -> None:
    """Deterministic by construction, which is stronger than deterministic_judge."""
    scorer = AnchorScorer()
    response = _response(["class Foo:", "noise"])
    first = scorer.score(CASE, response, seed=1, run=0).scores
    second = scorer.score(CASE, response, seed=999, run=7).scores
    assert first == second


def test_model_name_is_stable_for_reporting() -> None:
    assert AnchorScorer().model_name == "anchor-scorer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_anchor_scorer.py -q -p no:rerunfailures`
Expected: FAIL — `ModuleNotFoundError: No module named 'gnomon.judge.anchor_scorer'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/gnomon/judge/anchor_scorer.py
"""A scorer on the judge contract that never calls a model.

The judged context_precision could not rank arms stably (mean swing 0.286 across
two arms), while these numbers, computed from the answer key already in every
case, separated the same two arms at cohen_d +1.84 against the panel's +1.77.

It implements the judge contract rather than adding a parallel path, so it joins
a panel as an ordinary PanelMember and inherits per-case scores, bootstrap CIs
and aggregation unchanged. StubJudge is the precedent for a non-LLM member.
"""

from __future__ import annotations

from gnomon.domain.models import EvalCase, MetricScores, RagResponse
from gnomon.metrics.anchors import anchor_precision, anchor_recall
from gnomon.metrics.names import ANCHOR_METRICS


class AnchorScorer:
    """Scores ANCHOR_METRICS from EvalCase.expected_contexts."""

    model_name = "anchor-scorer"

    def score(
        self, case: EvalCase, response: RagResponse, *, seed: int, run: int
    ) -> MetricScores:
        # seed/run are part of the contract and irrelevant here: the result is a
        # pure function of the case and the response, so judge_runs > 1 buys
        # nothing.
        _ = (seed, run)
        anchors = list(case.expected_contexts)
        return MetricScores(
            scores={
                ANCHOR_METRICS[0]: anchor_recall(anchors, response.contexts),
                ANCHOR_METRICS[1]: anchor_precision(anchors, response.contexts),
            }
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_anchor_scorer.py -q -p no:rerunfailures`
Expected: PASS (6 passed)

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest tests/ -q -p no:rerunfailures`
Expected: PASS. Compare the count against a run on `HEAD~3` before treating any failure as caused by this work.

- [ ] **Step 6: Commit**

```bash
git add src/gnomon/judge/anchor_scorer.py tests/unit/test_anchor_scorer.py
git commit -m "feat(judge): a scorer on the judge contract that never calls a model"
```

---

### Task 4: Validate on the six rescorable arms (METRON)

**Files:**
- Create: `~/dev/tools/metron/judge-calibration/rescore.py`
- Create: `~/dev/tools/metron/judge-calibration/RESCORE.md`
- Modify: `~/dev/tools/metron/judge-calibration/REPORT.md` (link the rescore result)

**Interfaces:**
- Consumes: `AnchorScorer` from Task 3, via `sys.path.insert(0, "/Users/samdev/dev/tools/gnomon-eval/src")` — the same import style `code-retrieval-roundtable/runner.py` already uses.
- Produces: `results/rescore.json` and the three gate answers.

This task is the spec's gate. It must not be skipped, and its outcome decides whether the metric is fit for a public claim.

- [ ] **Step 1: Write the rescore script**

```python
# ~/dev/tools/metron/judge-calibration/rescore.py
"""Gate for the anchor scorer: does it rank arms stably where the judges did not?

Rescores the six arms whose contexts were persisted - code-retrieval-roundtable
(httpx/Python, 2 arms) and java-replication (gson/Java, 4 arms) - and answers
the three gate questions from the spec:

  1. ordering stability within each corpus, and agreement with the panel's
     verdicts where the panel separated arms
  2. cross-corpus stability, as the number comparable to the judges' 0.286 swing
  3. literalness bias: does substring matching change any ordering?

Usage: python3 rescore.py
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, "/Users/samdev/dev/tools/gnomon-eval/src")

from gnomon.domain.models import EvalCase, RagResponse  # noqa: E402
from gnomon.judge.anchor_scorer import AnchorScorer  # noqa: E402
from gnomon.metrics.names import ANCHOR_METRICS  # noqa: E402

METRON = Path(__file__).resolve().parent.parent
CORPORA = {
    "httpx": {
        "bench": METRON / "code-retrieval-roundtable",
        "cases": METRON / "graphify-vs-glyph" / "cases" / "cases.json",
        "arms": ["llamaindex-vector", "aider-repomap"],
    },
    "gson": {
        "bench": METRON / "java-replication",
        "cases": METRON / "java-replication" / "cases" / "cases.json",
        "arms": ["graphify-java", "llamaindex-java", "vector-sym-v1", "vector-sym-v2"],
    },
}


def score_arm(bench: Path, cases_path: Path, arm: str) -> dict[str, dict[str, float]]:
    cases = {c["id"]: c for c in json.loads(cases_path.read_text())}
    contexts_by_id = json.loads((bench / "contexts" / f"{arm}.json").read_text())
    scorer = AnchorScorer()
    out: dict[str, dict[str, float]] = {}
    for case_id, contexts in contexts_by_id.items():
        raw = cases.get(case_id)
        if raw is None:
            continue
        case = EvalCase(
            id=raw["id"],
            question=raw["question"],
            expected_answer=raw["expected_answer"],
            expected_contexts=raw["expected_contexts"],
        )
        response = RagResponse(answer="", contexts=contexts, total_tokens=0, latency_ms=0.0)
        out[case_id] = scorer.score(case, response, seed=42, run=0).scores
    return out


def judged_mean(bench: Path, arm: str) -> float | None:
    """Panel mean for context_precision on this arm, or None if not scored."""
    path = bench / "results" / f"{arm}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    per_judge = payload.get("case_scores", {})
    values = [
        score
        for judge in per_judge.values()
        for score in judge.get("context_precision", {}).values()
    ]
    return statistics.mean(values) if values else None


def main() -> None:
    report: dict[str, dict] = {}
    for corpus, cfg in CORPORA.items():
        print(f"\n=== {corpus}")
        header = f"{'arm':22}" + "".join(f"{m:>17}" for m in ANCHOR_METRICS) + f"{'judged':>10}"
        print(header)
        report[corpus] = {}
        for arm in cfg["arms"]:
            scores = score_arm(cfg["bench"], cfg["cases"], arm)
            if not scores:
                print(f"{arm:22} (no cases matched)")
                continue
            means = {
                m: statistics.mean([s[m] for s in scores.values()]) for m in ANCHOR_METRICS
            }
            judged = judged_mean(cfg["bench"], arm)
            report[corpus][arm] = {
                "n": len(scores),
                **means,
                "judged_context_precision": judged,
            }
            judged_cell = f"{judged:>10.3f}" if judged is not None else f"{'-':>10}"
            print(
                f"{arm:22}"
                + "".join(f"{means[m]:>17.3f}" for m in ANCHOR_METRICS)
                + judged_cell
            )

    print("\n--- gate 1: ordering within each corpus")
    for corpus, arms in report.items():
        for metric in (*ANCHOR_METRICS, "judged_context_precision"):
            ranked = [
                a
                for a, v in sorted(
                    arms.items(), key=lambda kv: -(kv[1][metric] or 0.0)
                )
            ]
            print(f"  {corpus:6} by {metric:26} {' > '.join(ranked)}")

    print("\n--- gate 2: cross-corpus spread of each metric (judges' swing was 0.286)")
    for metric in (*ANCHOR_METRICS, "judged_context_precision"):
        per_corpus = [
            statistics.mean([v[metric] for v in arms.values() if v[metric] is not None])
            for arms in report.values()
            if any(v[metric] is not None for v in arms.values())
        ]
        if len(per_corpus) == 2:
            print(f"  {metric:26} |delta| = {abs(per_corpus[0] - per_corpus[1]):.3f}")

    print("\n--- gate 3: does anchor ordering disagree with the judged ordering?")
    for corpus, arms in report.items():
        by_recall = [a for a, v in sorted(arms.items(), key=lambda kv: -kv[1][ANCHOR_METRICS[0]])]
        judged_ok = [a for a, v in arms.items() if v["judged_context_precision"] is not None]
        by_judged = [
            a
            for a, v in sorted(
                ((a, arms[a]) for a in judged_ok),
                key=lambda kv: -kv[1]["judged_context_precision"],
            )
        ]
        verdict = "SAME" if by_recall[: len(by_judged)] == by_judged else "DIFFERENT"
        print(f"  {corpus:6} anchor_recall vs judged: {verdict}")
        print(f"         anchor: {' > '.join(by_recall)}")
        print(f"         judged: {' > '.join(by_judged)}")

    out = Path(__file__).resolve().parent / "results" / "rescore.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run:
```bash
cd ~/dev/tools/metron/judge-calibration && python3 rescore.py
```
Expected: a table per corpus, then the three gate sections. No API key needed and no network call — if it takes more than a few seconds, something is calling a model that should not be.

Verified while writing this plan, so the script can rely on it: `java-replication/runner.py`
sets `SIBLING = BENCH`, so its cases live at `java-replication/cases/cases.json`
(not in graphify-vs-glyph), and its `results/*.json` carry the same
`case_scores[judge]["context_precision"]` shape as the roundtable.

- [ ] **Step 3: Verify the java arm names against what exists**

Run:
```bash
ls ~/dev/tools/metron/java-replication/contexts/ ~/dev/tools/metron/java-replication/results/
```
Expected: the four arms named in `CORPORA["gson"]["arms"]`. If a name differs, fix the list — do not silently skip an arm, since "(no cases matched)" printed for an arm is a coverage hole, not a result.

- [ ] **Step 4: Write RESCORE.md with the three gate answers**

Record, with the numbers the run produced:

- **Gate 1** — the per-corpus orderings, and whether `anchor_recall` agrees with the judged ordering. State the answer, not a hedge.
- **Gate 2** — the cross-corpus `|delta|` for each metric, next to the judges' 0.286. If the anchor metrics swing as much as the judges did, say so plainly: the metric failed its own gate and the fallback is gnomon-eval#68 item 3.
- **Gate 3** — whether the ordering differs from the judged one, and for which arms. A disagreement is not automatically a defect (the judged metric is the noisy one), but it must be attributed: check whether the disagreeing arm returns signatures rather than code blocks, which is the literalness bias the spec predicted.

Include the limitation verbatim from the spec: agreement is not accuracy, and a stably wrong metric is more dangerous for a public claim than a visibly noisy one.

- [ ] **Step 5: Commit**

```bash
cd ~/dev/tools/metron
git add judge-calibration/rescore.py judge-calibration/RESCORE.md judge-calibration/results/rescore.json judge-calibration/REPORT.md
git commit -m "bench(judge-calibration): rescore six arms without a judge, and answer the gate"
```

---

## Verification

- [ ] `python3 -m pytest tests/ -q -p no:rerunfailures` green in gnomon-eval, count compared against pre-change HEAD
- [ ] `ruff check src/gnomon/metrics/anchors.py src/gnomon/judge/anchor_scorer.py` clean
- [ ] `rescore.py` runs with no `DEEPINFRA_API_KEY` set — proof it calls no model
- [ ] All six arms appear in `results/rescore.json` with `n == 30`; no arm printed "(no cases matched)"
- [ ] `RESCORE.md` answers all three gate questions with numbers, including a stated verdict on whether the metric is fit for a public claim

## Explicitly not in this plan

- The AXON adapter for the roundtable (METRON), which waits on the gate above
- Any change to the shipped judge panel
- Any change to how `faithfulness` is prompted (gnomon-eval#68 item 3)
- Persisting `contexts/` in `graphify-vs-glyph` so its six arms become rescorable
