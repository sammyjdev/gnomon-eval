"""Canonical metric names for the v1 evaluation (RF-05).

One source of truth so the judge, the gate thresholds and the tests cannot
drift into spelling the same metric two ways.
"""

# Order is the report/display order.
V1_METRICS: tuple[str, ...] = ("faithfulness", "context_precision")

# TCM story quality metric (Phase C2). Separate from V1_METRICS: uses a
# binary adequate/inadequate prompt, not the shared V1 judge prompt.
STORY_COVERAGE = "story_coverage"

# Deterministic context-coverage metrics (anchor scorer). Separate from
# V1_METRICS on purpose: they are computed from EvalCase.expected_contexts, not
# asked of a judge, and they must never enter the shared V1 judge prompt.
# Order is the report/display order. Never average the two - they move in
# opposite directions by design.
ANCHOR_METRICS: tuple[str, ...] = ("anchor_recall", "anchor_precision")

#: The context cost that ships beside ANCHOR_METRICS. Deliberately NOT part of
#: that tuple: it is a cost, not a quality, and must never be averaged with a
#: score. It exists so a recall number cannot be read without what it cost
#: (gnomon-eval#69).
ANCHOR_COST = "context_tokens"
