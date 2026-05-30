"""StubJudge tests (RF-04 / ADR-002).

A deterministic judge that simulates LLM non-determinism: each of the N runs
produces a different faithfulness score, but the whole sequence is a pure
function of the declared seed. This lets the slice exercise the variance /
confidence-interval machinery and prove reproducibility without Ollama.

Determinism must survive across processes, so the seed derivation uses
hashlib, never the salted built-in hash().
"""

from gnomon.domain.interfaces import Judge
from gnomon.domain.models import EvalCase, RagResponse
from gnomon.judge.stub import StubJudge
from gnomon.metrics.names import V1_METRICS

CASE = EvalCase(
    id="case-1",
    question="Who narrates?",
    expected_answer="The GM narrates.",
    expected_contexts=["The game master narrates the world."],
)
RESPONSE = RagResponse(
    answer="The GM narrates the world.",
    contexts=["The game master narrates the world."],
    total_tokens=100,
    latency_ms=500.0,
)


def test_stub_judge_conforms_to_judge_protocol():
    assert isinstance(StubJudge(), Judge)


def test_score_is_in_unit_range():
    score = StubJudge().score(CASE, RESPONSE, seed=42, run=0).scores["faithfulness"]
    assert 0.0 <= score <= 1.0


def test_same_seed_case_and_run_is_deterministic():
    a = StubJudge().score(CASE, RESPONSE, seed=42, run=2).scores["faithfulness"]
    b = StubJudge().score(CASE, RESPONSE, seed=42, run=2).scores["faithfulness"]
    assert a == b


def test_different_runs_produce_variance():
    judge = StubJudge()
    run0 = judge.score(CASE, RESPONSE, seed=42, run=0).scores["faithfulness"]
    run1 = judge.score(CASE, RESPONSE, seed=42, run=1).scores["faithfulness"]
    assert run0 != run1


def test_different_seed_changes_the_sequence():
    judge = StubJudge()
    s42 = judge.score(CASE, RESPONSE, seed=42, run=0).scores["faithfulness"]
    s7 = judge.score(CASE, RESPONSE, seed=7, run=0).scores["faithfulness"]
    assert s42 != s7


def test_stub_scores_all_v1_metrics():
    judge = StubJudge()
    scores = judge.score(CASE, RESPONSE, seed=42, run=0).scores
    assert set(scores) == set(V1_METRICS)
    assert all(0.0 <= v <= 1.0 for v in scores.values())


def test_stub_two_metrics_are_independent():
    # As duas metricas nao colapsam para o mesmo numero por run.
    judge = StubJudge()
    s = judge.score(CASE, RESPONSE, seed=42, run=1).scores
    assert s["faithfulness"] != s["context_precision"]
