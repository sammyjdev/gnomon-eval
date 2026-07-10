"""Hand-written GEval evaluation_steps, replacing per-call auto-generation.

DeepEval's GEval forces 3-4 evaluation_steps whenever it auto-generates them
from a `criteria` string, regardless of how many real requirements that
string has -- confirmed against deepeval 4.0.7's own
`generate_evaluation_steps.txt` template. A 2-requirement criteria gets
padded with 1-2 invented ones, and the scoring prompt only ever sees the
generated steps, never the original criteria (so a hallucinated step fully
replaces the real requirement, with no fallback). Auto-generation also reruns
on every GEval instance -- the judge's own scoring instructions varied
between otherwise-identical reruns of the same case, adding judge-side noise
on top of the model-under-test's own variance (found via a 2026-07-09
ChatEval audit: a correct reply -- gave the configured price, correctly
declined an unconfigured fact -- scored 0.0, reason: "does not provide a
clear JSON output", on a WhatsApp bot that never speaks JSON).

Only two `criteria_metric` values ever reach GEval (tool_selection_accuracy
is scored by ToolCorrectnessMetric instead), so two small, shared rubrics
replace ~190 per-case auto-generations. Each case's specific requirement
still reaches the judge -- via LLMTestCase.expected_output (case.criteria)
and LLMTestCase.context (case.tenant), not via GEval's criteria= param.
"""

EVALUATION_STEPS: dict[str, list[str]] = {
    "hallucination": [
        "Check 'context' (the tenant's configured data) for the specific fact "
        "the customer asked about (price, hours, address, policy, etc). If it "
        "is present in 'context', 'actual_output' must state that value "
        "correctly.",
        "If a fact is absent from 'context', it is unknown, not false. A "
        "reply that says it does not have that information is CORRECT for an "
        "absent fact -- do not penalize an honest 'I don't know' as a "
        "failure.",
        "'expected_output' describes what this specific reply must and must "
        "not do. Check 'actual_output' against it literally, part by part if "
        "it covers more than one topic.",
        "Do not evaluate formatting, output structure, JSON, tone, or "
        "length -- only whether the stated facts match 'context' and "
        "whether anything was invented that isn't in 'context'.",
    ],
    "tone_brand": [
        "'expected_output' describes the specific tone/brand rule for this "
        "reply. Check 'actual_output' against it literally.",
        "The tenant's configured tone in 'context' is the target register -- "
        "judge whether 'actual_output' matches that register, not a generic "
        "notion of 'professional' or 'friendly'.",
        "A short, direct reply is not a violation by itself -- only "
        "penalize if it actually breaks the rule stated in "
        "'expected_output'.",
        "Do not evaluate formatting, output structure, or JSON -- only tone "
        "and brand-voice compliance.",
    ],
}
