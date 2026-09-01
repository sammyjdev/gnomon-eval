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
