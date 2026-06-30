"""Canonical metric names for the v1 evaluation (RF-05).

One source of truth so the judge, the gate thresholds and the tests cannot
drift into spelling the same metric two ways.
"""

# Order is the report/display order.
V1_METRICS: tuple[str, ...] = ("faithfulness", "context_precision")

# TCM story quality metric (Phase C2). Separate from V1_METRICS: uses a
# binary adequate/inadequate prompt, not the shared V1 judge prompt.
STORY_COVERAGE = "story_coverage"
