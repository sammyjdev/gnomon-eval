"""MockTarget tests.

A fixed in-memory target that returns a canned RagResponse. No network: it
exists to validate the end-to-end flow, not real RAG behaviour. It must
satisfy the RagTarget contract and carry tokens + latency (ADR-004).
"""

from gnomon.domain.interfaces import RagTarget
from gnomon.targets.mock import MockTarget


def test_mock_target_conforms_to_rag_target_protocol():
    target = MockTarget(answer="a", contexts=["c"], total_tokens=10, latency_ms=5.0)
    assert isinstance(target, RagTarget)


def test_mock_target_returns_the_configured_response_with_cost_and_latency():
    target = MockTarget(
        answer="The GM narrates the world.",
        contexts=["The game master narrates."],
        total_tokens=128,
        latency_ms=640.0,
    )
    resp = target.query("Who narrates?")
    assert resp.answer == "The GM narrates the world."
    assert resp.contexts == ["The game master narrates."]
    assert resp.total_tokens == 128
    assert resp.latency_ms == 640.0
