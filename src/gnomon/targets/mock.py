"""In-memory target returning a fixed response.

Validates the flow, not a real RAG. No network. Implements the domain's
RagTarget contract so the runner cannot tell it from a real adapter.
"""

from gnomon.domain.models import RagResponse


class MockTarget:
    """Returns a canned RagResponse for any question."""

    def __init__(
        self, *, answer: str, contexts: list[str], total_tokens: int, latency_ms: float
    ) -> None:
        self._response = RagResponse(
            answer=answer,
            contexts=contexts,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
        )

    def query(self, question: str) -> RagResponse:  # noqa: ARG002 - fixed response
        return self._response
