"""Domain interface (Protocol) tests.

The domain defines the contracts that targets and judges implement
(ADR-001 / RNF-02). These are runtime-checkable Protocols so the
dependency direction is verifiable: implementations conform to the
domain, the domain depends on no implementation.
"""

from gnomon.domain.interfaces import Judge, RagTarget
from gnomon.domain.models import EvalCase, MetricScores, RagResponse


class _ConformingTarget:
    def query(self, question: str) -> RagResponse:
        return RagResponse(answer="a", contexts=["c"], total_tokens=1, latency_ms=1.0)


class _ConformingJudge:
    def score(self, case: EvalCase, response: RagResponse, *, seed: int, run: int) -> MetricScores:
        return MetricScores(scores={"faithfulness": 0.9})


class _NotATarget:
    pass


def test_conforming_target_satisfies_protocol():
    assert isinstance(_ConformingTarget(), RagTarget)


def test_conforming_judge_satisfies_protocol():
    assert isinstance(_ConformingJudge(), Judge)


def test_non_conforming_object_does_not_satisfy_target_protocol():
    assert not isinstance(_NotATarget(), RagTarget)
