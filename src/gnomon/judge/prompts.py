"""Judge prompts for the v1 metrics (RF-05).

Each prompt asks the model for a single float in [0, 1] inside a JSON object,
so the judge can parse a score deterministically instead of scraping prose.
"""

from gnomon.domain.models import EvalCase, RagResponse

_INSTRUCTION = (
    'Return ONLY a JSON object of the form {{"score": <float 0..1>}}. No prose, no explanation.'
)

_TEMPLATES = {
    "faithfulness": (
        "Rate how well the ANSWER is grounded in the CONTEXTS (1.0 = every claim "
        "is supported, 0.0 = unsupported).\n\n"
        "QUESTION: {question}\nANSWER: {answer}\nCONTEXTS: {contexts}\n\n" + _INSTRUCTION
    ),
    "context_precision": (
        "Rate how relevant the retrieved CONTEXTS are to the QUESTION (1.0 = all "
        "relevant, 0.0 = none relevant).\n\n"
        "QUESTION: {question}\nCONTEXTS: {contexts}\n\n" + _INSTRUCTION
    ),
}


def build_prompt(metric: str, case: EvalCase, response: RagResponse) -> str:
    return _TEMPLATES[metric].format(
        question=case.question,
        answer=response.answer,
        contexts="\n- " + "\n- ".join(response.contexts),
    )
