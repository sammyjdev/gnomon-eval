import json

import pytest

from gnomon.domain.models import EvalCase, RagResponse
from gnomon.judge.cache import JudgeCache
from gnomon.judge.ollama import JudgeProtocolError
from gnomon.judge.openai_compat import OpenAICompatJudge
from gnomon.metrics.names import V1_METRICS

CASE = EvalCase(id="c1", question="q", expected_answer="a", expected_contexts=["c"])
RESPONSE = RagResponse(answer="a", contexts=["c"], total_tokens=5, latency_ms=1.0)


class ScriptedTransport:
    """Returns one OpenAI-chat-shaped body scoring all metrics."""

    def __init__(self, scores=None, body_override=None):
        self.scores = scores if scores is not None else {m: 0.8 for m in V1_METRICS}
        self.body_override = body_override
        self.calls = []

    def post_json(self, url, payload, *, headers, timeout_s):
        self.calls.append((url, payload, headers))
        if self.body_override is not None:
            return 200, self.body_override
        return 200, {"choices": [{"message": {"content": json.dumps(self.scores)}}]}


def _judge(transport, cache=None, api_key=None):
    return OpenAICompatJudge(
        model="meta-llama/Meta-Llama-3.1-8B-Instruct",
        base_url="https://api.deepinfra.com/v1/openai",
        api_key=api_key,
        transport=transport,
        cache=cache,
    )


def test_scores_all_metrics_in_unit_range():
    judge = _judge(ScriptedTransport())
    scores = judge.score(CASE, RESPONSE, seed=42, run=0).scores
    assert set(scores) == set(V1_METRICS)
    assert all(0.0 <= v <= 1.0 for v in scores.values())


def test_single_call_scores_all_metrics():
    transport = ScriptedTransport()
    _judge(transport).score(CASE, RESPONSE, seed=42, run=0)
    assert len(transport.calls) == 1


def test_posts_to_chat_completions_with_bearer_auth():
    transport = ScriptedTransport()
    _judge(transport, api_key="secret").score(CASE, RESPONSE, seed=42, run=0)
    url, _, headers = transport.calls[0]
    assert url == "https://api.deepinfra.com/v1/openai/chat/completions"
    assert headers["Authorization"] == "Bearer secret"


def test_cache_hit_skips_transport():
    transport = ScriptedTransport()
    cache = JudgeCache()
    judge = _judge(transport, cache=cache)
    judge.score(CASE, RESPONSE, seed=42, run=0)
    calls_after_first = len(transport.calls)
    judge.score(CASE, RESPONSE, seed=42, run=0)
    assert len(transport.calls) == calls_after_first


def test_unparseable_model_output_is_protocol_error():
    transport = ScriptedTransport(body_override={"choices": [{"message": {"content": "I think 0.8"}}]})
    with pytest.raises(JudgeProtocolError):
        _judge(transport).score(CASE, RESPONSE, seed=42, run=0)


def test_missing_metric_key_is_protocol_error():
    partial = {V1_METRICS[0]: 0.8}
    transport = ScriptedTransport(
        body_override={"choices": [{"message": {"content": json.dumps(partial)}}]}
    )
    with pytest.raises(JudgeProtocolError):
        _judge(transport).score(CASE, RESPONSE, seed=42, run=0)
