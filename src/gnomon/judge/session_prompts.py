"""Faithfulness-only judge prompt for scripted sessions."""


def build_session_prompt(question: str, answer: str, contexts: list[str]) -> str:
    return (
        "You are grading a RAG answer for faithfulness only.\n"
        "Score how fully the ANSWER is grounded in the CONTEXTS below. "
        "The contexts are the ONLY admissible evidence. "
        "Use a float from 0 to 1, where 1 means every claim is supported and "
        "0 means the answer is unsupported.\n\n"
        f"QUESTION: {question}\n"
        f"ANSWER: {answer}\n"
        "CONTEXTS:\n- "
        + "\n- ".join(contexts)
        + '\n\nReturn ONLY a JSON object: {"faithfulness": <float 0..1>}. '
        "No prose, no explanation."
    )
