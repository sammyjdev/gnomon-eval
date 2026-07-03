import pytest

from gnomon.targets.openai_compat import IncompleteResponseError, TargetRuntimeError
from gnomon.targets.session_target import SessionTarget


class FakeTransport:
    def __init__(self, *, status=200, body=None, raises=None):
        self.status, self.body, self.raises = status, body or {}, raises
        self.calls = []

    def post_json(self, url, payload, *, headers, timeout_s):
        self.calls.append((url, payload, headers, timeout_s))
        if self.raises:
            raise self.raises
        return self.status, self.body


def _ok_body():
    return {
        "choices": [{"message": {"content": "A remembered answer."}}],
        "contexts": ["Relevant session context."],
        "usage": {
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
            "source": "provider",
        },
    }


def _target(transport, *, recall_max_tokens=1234):
    return SessionTarget(
        base_url="http://localhost:8000/v1",
        model="session-model",
        transport=transport,
        recall_max_tokens=recall_max_tokens,
    )


def test_axon_arm_sends_question_only_with_context_recall_budget():
    transport = FakeTransport(body=_ok_body())
    target = _target(transport, recall_max_tokens=321)

    target.run_turn(
        [{"role": "assistant", "content": "old answer"}],
        "What happened?",
        arm="axon",
    )

    _url, payload, _headers, _timeout_s = transport.calls[0]
    assert payload == {
        "model": "session-model",
        "messages": [{"role": "user", "content": "What happened?"}],
        "include_context": True,
        "forward_history": False,
        "recall_max_tokens": 321,
    }


def test_baseline_arm_sends_history_and_omits_recall_budget():
    transport = FakeTransport(body=_ok_body())
    target = _target(transport)
    history = [
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier answer"},
    ]

    target.run_turn(history, "Current question?", arm="baseline")

    _url, payload, _headers, _timeout_s = transport.calls[0]
    assert payload == {
        "model": "session-model",
        "messages": [*history, {"role": "user", "content": "Current question?"}],
        "include_context": False,
        "forward_history": True,
    }
    assert "recall_max_tokens" not in payload


def test_usage_block_maps_to_turn_result_fields():
    target = _target(FakeTransport(body=_ok_body()))

    result = target.run_turn([], "q", arm="axon")

    assert result.answer == "A remembered answer."
    assert result.contexts == ["Relevant session context."]
    assert result.prompt_tokens == 11
    assert result.completion_tokens == 7
    assert result.total_tokens == 18
    assert result.latency_ms >= 0.0
    assert result.usage_source == "provider"


def test_missing_usage_prompt_tokens_is_incomplete_response():
    body = _ok_body()
    del body["usage"]["prompt_tokens"]
    target = _target(FakeTransport(body=body))

    with pytest.raises(IncompleteResponseError):
        target.run_turn([], "q", arm="axon")


def test_missing_usage_source_is_incomplete_response():
    body = _ok_body()
    del body["usage"]["source"]
    target = _target(FakeTransport(body=body))

    with pytest.raises(IncompleteResponseError):
        target.run_turn([], "q", arm="axon")


def test_zero_usage_value_is_not_treated_as_missing():
    body = _ok_body()
    body["usage"]["prompt_tokens"] = 0
    target = _target(FakeTransport(body=body))

    result = target.run_turn([], "q", arm="axon")

    assert result.prompt_tokens == 0


def test_non_200_is_runtime_error():
    target = _target(FakeTransport(status=500, body={"error": "boom"}))

    with pytest.raises(TargetRuntimeError):
        target.run_turn([], "q", arm="axon")
