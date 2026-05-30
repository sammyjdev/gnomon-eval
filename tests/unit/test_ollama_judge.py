import json

import pytest

from gnomon.domain.models import EvalCase, RagResponse
from gnomon.judge.cache import JudgeCache
from gnomon.judge.ollama import JudgeProtocolError, OllamaJudge
from gnomon.metrics.names import V1_METRICS

CASE = EvalCase(id="c1", question="q", expected_answer="a", expected_contexts=["c"])
RESPONSE = RagResponse(answer="a", contexts=["c"], total_tokens=5, latency_ms=1.0)


class ScriptedTransport:
    """Returns one Ollama-shaped body scoring all metrics, recording seed per call."""

    def __init__(self, scores=None, body_override=None):
        self.scores = scores if scores is not None else {m: 0.8 for m in V1_METRICS}
        self.body_override = body_override
        self.seeds = []

    def post_json(self, url, payload, *, headers, timeout_s):
        self.seeds.append(payload["options"]["seed"])
        if self.body_override is not None:
            return 200, self.body_override
        return 200, {"message": {"content": json.dumps(self.scores)}}


def _judge(transport, cache=None):
    return OllamaJudge(
        model="llama3", base_url="http://localhost:11434", transport=transport, cache=cache
    )


def test_scores_all_metrics_in_unit_range():
    judge = _judge(ScriptedTransport())
    scores = judge.score(CASE, RESPONSE, seed=42, run=0).scores
    assert set(scores) == set(V1_METRICS)
    assert all(0.0 <= v <= 1.0 for v in scores.values())


def test_single_call_scores_all_metrics():
    # RNF-06 cost: one model call per score(), not one per metric.
    transport = ScriptedTransport()
    _judge(transport).score(CASE, RESPONSE, seed=42, run=0)
    assert len(transport.seeds) == 1


def test_seed_is_offset_by_run():
    transport = ScriptedTransport()
    _judge(transport).score(CASE, RESPONSE, seed=100, run=3)
    assert transport.seeds == [103]


def test_cache_hit_skips_transport():
    transport = ScriptedTransport()
    cache = JudgeCache()
    judge = _judge(transport, cache=cache)
    judge.score(CASE, RESPONSE, seed=42, run=0)
    calls_after_first = len(transport.seeds)
    judge.score(CASE, RESPONSE, seed=42, run=0)
    assert len(transport.seeds) == calls_after_first


def test_unparseable_model_output_is_protocol_error():
    transport = ScriptedTransport(body_override={"message": {"content": "I think 0.8"}})
    with pytest.raises(JudgeProtocolError):
        _judge(transport).score(CASE, RESPONSE, seed=42, run=0)


def test_missing_metric_key_is_protocol_error():
    # A response that omits one of the v1 metrics is a protocol error, not a
    # silently-dropped metric.
    partial = {V1_METRICS[0]: 0.8}
    transport = ScriptedTransport(body_override={"message": {"content": json.dumps(partial)}})
    with pytest.raises(JudgeProtocolError):
        _judge(transport).score(CASE, RESPONSE, seed=42, run=0)
