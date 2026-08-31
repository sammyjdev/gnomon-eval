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
