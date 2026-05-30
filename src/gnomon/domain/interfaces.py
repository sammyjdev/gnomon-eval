"""Contracts the rest of the system implements.

These Protocols are the seam in the dependency graph (ADR-001): the runner
and metrics depend on these abstractions, concrete targets and judges
implement them. The domain itself depends on nothing below it.
"""

from typing import Protocol, runtime_checkable

from gnomon.domain.models import EvalCase, MetricScores, RagResponse


@runtime_checkable
class RagTarget(Protocol):
    """A RAG system under evaluation. One adapter per concrete RAG (RF-02)."""

    def query(self, question: str) -> RagResponse:
        """Send a question, return answer + contexts + tokens + latency."""
        ...


@runtime_checkable
class Judge(Protocol):
    """Scores a (case, response) pair under a declared seed (RF-04 / ADR-002).

    `run` identifies which of the N variance runs this is, so a seeded judge
    produces a fixed, reproducible sequence of scores for a given seed.
    """

    def score(
        self, case: EvalCase, response: RagResponse, *, seed: int, run: int
    ) -> MetricScores: ...
