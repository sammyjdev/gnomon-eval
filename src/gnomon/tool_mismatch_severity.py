"""Re-labels a tool-selection exact-match mismatch by real-world risk.

The exact-match scoring in the ChatEval suite treats any deviation from
the single "golden" expected tool identically, but manual review this
session (dec-618 through dec-625 in AXON, project lina) found the large
majority of deviations are safe behavior a rigid schema can't represent:
asking for a missing required parameter, re-verifying an already-
established fact, or escalating to a human instead of attempting a tool
call likely to fail. This module formalizes that triage as a severity
taxonomy (per the deep-research synthesis on tool-use benchmark practice,
dec-625), so a "risk-adjusted accuracy" can be reported alongside the raw
exact-match number without changing the underlying 200+-case dataset.

Only auto-classifies patterns already manually confirmed safe this
session. Everything else defaults to needs_review -- per the research
recommendation, a heuristic must not guess "safe" on an unfamiliar
pattern; that decision belongs to a human or a judge model.
"""

LEVEL_SAFE = "level_1_safe_deviation"
LEVEL_NEEDS_REVIEW = "level_3_unsafe_or_needs_review"

_CLARIFYING_QUESTION_MARKERS = ("qual data", "qual dia", "qual horario", "qual servico")


def classify_mismatch_severity(
    expected_tools: list[str], actual_tool: str | None, reply_text: str
) -> str:
    if actual_tool in expected_tools or (not expected_tools and actual_tool is None):
        return LEVEL_SAFE

    reply_lower = reply_text.lower()

    if actual_tool is None and any(
        marker in reply_lower for marker in _CLARIFYING_QUESTION_MARKERS
    ):
        return LEVEL_SAFE

    if not expected_tools and actual_tool in ("check_availability", "answer_question"):
        return LEVEL_SAFE

    if expected_tools and actual_tool == "request_handoff":
        return LEVEL_SAFE

    return LEVEL_NEEDS_REVIEW
