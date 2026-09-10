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
from gnomon.metrics.anchors import anchor_precision, anchor_recall, context_cost
from gnomon.metrics.names import ANCHOR_COST, ANCHOR_METRICS

#: The roundtable's shared cap, and the only budget any arm has been scored
#: against so far. A bench with a different cap passes its own.
_DEFAULT_BUDGET_TOKENS = 4000


class AnchorScorer:
    """Scores ANCHOR_METRICS from EvalCase.expected_contexts."""

    model_name = "anchor-scorer"

    def __init__(self, *, budget_tokens: int = _DEFAULT_BUDGET_TOKENS) -> None:
        """budget_tokens is the bench's shared context cap - the denominator the
        reported cost is a fraction of. Arms compared against each other must
        use the same value, which is why it is explicit rather than inferred."""
        self._budget_tokens = budget_tokens

    def score(self, case: EvalCase, response: RagResponse, *, seed: int, run: int) -> MetricScores:
        # seed/run are part of the contract and irrelevant here: the result is a
        # pure function of the case and the response, so judge_runs > 1 buys
        # nothing.
        _ = (seed, run)
        anchors = list(case.expected_contexts)
        return MetricScores(
            scores={
                ANCHOR_METRICS[0]: anchor_recall(anchors, response.contexts),
                ANCHOR_METRICS[1]: anchor_precision(anchors, response.contexts),
                # Ships with the score, not beside it: gnomon-eval#69 exists
                # because a recall number was readable without its cost.
                ANCHOR_COST: context_cost(response.contexts, budget_tokens=self._budget_tokens),
            }
        )
