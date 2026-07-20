"""Judge prompt for the v1 metrics (RF-05).

A single prompt asks the model to score every v1 metric at once and return one
JSON object keyed by metric name, so one model call scores the whole case
(RNF-06 cost: len(cases) * judge_runs model calls, not multiplied by the
number of metrics). The parser validates the object against V1_METRICS.
"""

from gnomon.domain.models import EvalCase, RagResponse
from gnomon.judge.untrusted import UNTRUSTED_INPUT_WARNING, wrap_untrusted
from gnomon.metrics.names import V1_METRICS

# Per-metric descriptions. Keys must stay in sync with V1_METRICS — adding a
# metric there means adding its description here.
_METRIC_DESCRIPTIONS = {
    "faithfulness": (
        "how well the ANSWER is grounded in the CONTEXTS "
        "(1.0 = every claim supported, 0.0 = unsupported)"
    ),
    "context_precision": (
        "how relevant the CONTEXTS are to the QUESTION (1.0 = all relevant, 0.0 = none relevant)"
    ),
}

_METRIC_LINES = "\n".join(f"- {m}: {_METRIC_DESCRIPTIONS[m]}" for m in V1_METRICS)
_JSON_SHAPE = ", ".join(f'"{m}": <float 0..1>' for m in V1_METRICS)

V1_PROMPT_INSTRUCTIONS = (
    "You are grading a RAG answer on these metrics, each a float in [0, 1]:\n"
    f"{_METRIC_LINES}\n\n"
    f"{UNTRUSTED_INPUT_WARNING}"
)
V1_PROMPT_JSON_SHAPE = f"{{{_JSON_SHAPE}}}"


def build_prompt(case: EvalCase, response: RagResponse) -> str:
    contexts_block = "- " + "\n- ".join(response.contexts)
    return (
        f"{V1_PROMPT_INSTRUCTIONS}\n\n"
        f"QUESTION: {case.question}\n"
        f"ANSWER:\n{wrap_untrusted(response.answer)}\n"
        f"CONTEXTS:\n{wrap_untrusted(contexts_block)}\n\n"
        f"Return ONLY a JSON object: {V1_PROMPT_JSON_SHAPE}. No prose, no explanation."
    )
