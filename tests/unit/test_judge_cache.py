from gnomon.domain.models import EvalCase, MetricScores, RagResponse
from gnomon.judge.cache import JudgeCache

CASE = EvalCase(
    id="case-1",
    question="q",
    expected_answer="a",
    expected_contexts=["c"],
)
RESPONSE = RagResponse(answer="a", contexts=["c"], total_tokens=10, latency_ms=1.0)
SCORES = MetricScores(scores={"faithfulness": 0.8, "context_precision": 0.7})


def test_hit_returns_stored_scores():
    cache = JudgeCache()
    cache.put(CASE, RESPONSE, "judge-x", seed=42, run=0, scores=SCORES)
    assert cache.get(CASE, RESPONSE, "judge-x", seed=42, run=0) == SCORES


def test_different_run_is_a_miss():
    cache = JudgeCache()
    cache.put(CASE, RESPONSE, "judge-x", seed=42, run=0, scores=SCORES)
    assert cache.get(CASE, RESPONSE, "judge-x", seed=42, run=1) is None


def test_different_seed_is_a_miss():
    cache = JudgeCache()
    cache.put(CASE, RESPONSE, "judge-x", seed=42, run=0, scores=SCORES)
    assert cache.get(CASE, RESPONSE, "judge-x", seed=43, run=0) is None


def test_different_model_is_a_miss():
    cache = JudgeCache()
    cache.put(CASE, RESPONSE, "judge-x", seed=42, run=0, scores=SCORES)
    assert cache.get(CASE, RESPONSE, "judge-y", seed=42, run=0) is None


def test_different_contexts_is_a_miss():
    # The identity includes the retrieved contexts: same answer, different
    # contexts must NOT collide (context_precision depends on contexts).
    other = RagResponse(answer="a", contexts=["DIFFERENT"], total_tokens=10, latency_ms=1.0)
    cache = JudgeCache()
    cache.put(CASE, RESPONSE, "judge-x", seed=42, run=0, scores=SCORES)
    assert cache.get(CASE, other, "judge-x", seed=42, run=0) is None
