import pytest

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


def test_scores_the_anchor_metrics_and_nothing_beyond_them_but_the_cost() -> None:
    """The cost joined the output in gnomon-eval#69; nothing else may."""
    from gnomon.metrics.names import ANCHOR_COST

    scores = AnchorScorer().score(CASE, _response(["class Foo:"]), seed=42, run=0).scores
    assert set(scores) == set(ANCHOR_METRICS) | {ANCHOR_COST}


def test_returns_metric_scores_so_it_fits_the_panel() -> None:
    result = AnchorScorer().score(CASE, _response(["class Foo:"]), seed=42, run=0)
    assert isinstance(result, MetricScores)


def test_half_the_anchors_found_is_half_recall() -> None:
    scores = AnchorScorer().score(CASE, _response(["class Foo:"]), seed=42, run=0).scores
    assert scores["anchor_recall"] == 0.5
    assert scores["anchor_precision"] == 1.0


def test_empty_contexts_score_zero_on_both() -> None:
    scores = AnchorScorer().score(CASE, _response([]), seed=42, run=0).scores
    assert scores == {
        "anchor_recall": 0.0,
        "anchor_precision": 0.0,
        "context_tokens": 0.0,
    }


def test_seed_and_run_do_not_change_the_score() -> None:
    """Deterministic by construction, which is stronger than deterministic_judge."""
    scorer = AnchorScorer()
    response = _response(["class Foo:", "noise"])
    first = scorer.score(CASE, response, seed=1, run=0).scores
    second = scorer.score(CASE, response, seed=999, run=7).scores
    assert first == second


def test_model_name_is_stable_for_reporting() -> None:
    assert AnchorScorer().model_name == "anchor-scorer"


# ── gnomon-eval#69: recall must not travel without its cost ─────────────────


def test_scorer_emits_the_context_cost_alongside_recall() -> None:
    """anchor_recall has no defence against being inflated with volume.

    A retriever returning the whole repository scores near 1.0, and the metric
    that would normally control for that - anchor_precision - is not comparable
    across arms with different retrieval depth (its denominator IS that depth,
    and at k=1 it degenerates to P(recall > 0)). Measured on the METRON
    roundtable: naive windows scored 0.421 / 0.517 / 0.603 at 20 / 40 / 60 lines
    while efficiency fell 0.325 -> 0.202 -> 0.167. Reading recall without its
    cost recommends the worst arm.

    So the cost ships with the score. A caller cannot obtain one without the
    other.
    """
    scores = AnchorScorer().score(CASE, _response(["class Foo:", "noise"]), seed=1, run=0).scores
    assert "context_tokens" in scores


def test_context_cost_is_the_fraction_of_the_shared_budget_spent() -> None:
    """Reported as a fraction of the bench's shared token cap, not a raw count.

    MetricScores validates every value into [0, 1] - a guarantee worth more than
    the convenience of a raw number - and a fraction of the shared budget is what
    makes two arms comparable anyway.
    """
    from gnomon.metrics.anchors import context_cost

    contexts = ["a" * 400, "b" * 800]  # ~300 estimated tokens
    assert context_cost(contexts, budget_tokens=1000) == pytest.approx(0.3)

    scores = AnchorScorer(budget_tokens=1000).score(CASE, _response(contexts), seed=1, run=0).scores
    assert scores["context_tokens"] == pytest.approx(0.3)


def test_an_empty_retrieval_costs_nothing() -> None:
    from gnomon.metrics.anchors import context_cost

    assert context_cost([], budget_tokens=1000) == 0.0


def test_spending_over_the_budget_clamps_rather_than_escaping_the_range() -> None:
    """An arm that overshoots the cap is at 1.0, not at 1.4: the value stays a
    valid score, and overspend is visible as saturation."""
    from gnomon.metrics.anchors import context_cost

    assert context_cost(["x" * 8000], budget_tokens=1000) == 1.0


def test_cost_is_reported_but_never_averaged_into_the_score() -> None:
    """It is a cost, not a quality. Averaging it with recall would be meaningless
    and MetricScores would reject it anyway - it is not in [0, 1]."""
    from gnomon.metrics.names import ANCHOR_COST, ANCHOR_METRICS

    assert ANCHOR_COST not in ANCHOR_METRICS
