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


def test_recall_rejects_an_empty_answer_key() -> None:
    """Vacuous recall is not zero: an empty key is a caller bug, not a total miss.

    Unreachable from AnchorScorer - EvalCase.expected_contexts has min_length=1.
    """
    with pytest.raises(ValueError, match="at least one anchor"):
        anchor_recall([], ["def a(): ..."])
