import json

import pytest

from gnomon.judge.cache import JudgeCache
from gnomon.judge.ollama import JudgeError, JudgeProtocolError
from gnomon.judge.session_judge import SessionOllamaJudge


class SessionTransport:
    def __init__(self, *, content=None):
        self.content = content if content is not None else json.dumps({"faithfulness": 0.8})
        self.payloads = []

    def post_json(self, url, payload, *, headers, timeout_s):
        self.payloads.append(payload)
        return 200, {"message": {"content": self.content}}


def _judge(transport, cache=None):
    return SessionOllamaJudge(
        model="llama3",
        base_url="http://localhost:11434",
        transport=transport,
        cache=cache,
    )


def test_happy_path_returns_faithfulness_score():
    score = _judge(SessionTransport()).score_faithfulness("q", "a", ["context"], seed=42, run=0)
    assert score == 0.8


@pytest.mark.parametrize("value", [1.5, -0.1])
def test_out_of_range_faithfulness_raises_named_judge_error(value):
    transport = SessionTransport(content=json.dumps({"faithfulness": value}))
    with pytest.raises(JudgeError):
        _judge(transport).score_faithfulness("q", "a", ["context"], seed=42, run=0)


def test_non_json_answer_content_raises_protocol_error():
    transport = SessionTransport(content="I think 0.8")
    with pytest.raises(JudgeProtocolError):
        _judge(transport).score_faithfulness("q", "a", ["context"], seed=42, run=0)


def test_cache_hit_avoids_second_transport_call():
    transport = SessionTransport()
    judge = _judge(transport, cache=JudgeCache())

    judge.score_faithfulness("q", "a", ["context"], seed=42, run=0)
    judge.score_faithfulness("q", "a", ["context"], seed=42, run=0)

    assert len(transport.payloads) == 1


@pytest.mark.parametrize(
    ("question", "answer", "contexts"),
    [("", "a", ["context"]), ("q", "", ["context"]), ("q", "a", [])],
)
def test_empty_inputs_raise_named_judge_error(question, answer, contexts):
    transport = SessionTransport()
    with pytest.raises(JudgeError):
        _judge(transport).score_faithfulness(question, answer, contexts, seed=42, run=0)
    assert transport.payloads == []


def test_seed_is_offset_by_run_in_request_payload():
    transport = SessionTransport()
    _judge(transport).score_faithfulness("q", "a", ["context"], seed=100, run=3)
    assert transport.payloads[0]["options"]["seed"] == 103
