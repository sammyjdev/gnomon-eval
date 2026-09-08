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
    """Fraction of expected anchors the contexts reached.

    An empty answer key raises rather than scoring 0.0: recall over no anchors
    is vacuous, not zero, and returning 0.0 would report a perfect-by-vacuity
    retrieval as a total miss. EvalCase already makes this unreachable from the
    scorer (`expected_contexts: Field(min_length=1)`); the guard is for direct
    callers of this function.
    """
    if not anchors:
        raise ValueError("anchor_recall needs at least one anchor: recall over none is undefined")
    return len(anchor_hits(anchors, contexts)) / len(anchors)


def context_cost(contexts: list[str], *, budget_tokens: int) -> float:
    """Fraction of the shared token budget this retrieval spent.

    anchor_recall has no defence against being inflated with volume: a retriever
    returning the whole repository scores near 1.0. The metric that would
    normally control for that - anchor_precision - is not comparable across arms
    with different retrieval depth, because its denominator IS that depth and at
    k=1 it degenerates to P(recall > 0).

    Measured on the METRON roundtable: naive windows scored 0.421 / 0.517 / 0.603
    at 20 / 40 / 60 lines while recall per 1k tokens fell 0.325 -> 0.202 -> 0.167.
    Reading recall without its cost recommends the worst arm.

    A fraction rather than a raw count, for two reasons: it is what makes two
    arms comparable, and MetricScores validates every value into [0, 1], which is
    a guarantee worth more than the convenience of a count. Overspend clamps to
    1.0 and reads as saturation.
    """
    if budget_tokens <= 0:
        raise ValueError("budget_tokens must be positive to express a cost as a fraction")
    estimated = sum(len(c) for c in contexts) / 4
    return min(1.0, estimated / budget_tokens)


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
