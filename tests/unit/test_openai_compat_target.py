import pytest

from gnomon.http import TransportError
from gnomon.targets.openai_compat import (
    IncompleteResponseError,
    OpenAICompatTarget,
    TargetConfigError,
    TargetRuntimeError,
)


class FakeTransport:
    def __init__(self, *, status=200, body=None, raises=None):
        self.status, self.body, self.raises = status, body or {}, raises
        self.calls = []

    def post_json(self, url, payload, *, headers, timeout_s):
        self.calls.append((url, payload))
        if self.raises:
            raise self.raises
        return self.status, self.body


def _ok_body():
    return {
        "choices": [{"message": {"content": "The game master narrates the world."}}],
        "contexts": ["The game master narrates the world to the players."],
        "usage": {"total_tokens": 137},
    }


def _target(transport):
    return OpenAICompatTarget(
        base_url="http://localhost:8000/v1",
        model="rpg-master",
        transport=transport,
    )


def test_missing_base_url_is_config_error():
    with pytest.raises(TargetConfigError):
        OpenAICompatTarget(base_url="", model="m", transport=FakeTransport())


def test_happy_path_maps_to_rag_response():
    target = _target(FakeTransport(body=_ok_body()))
    resp = target.query("Who narrates the world?")
    assert resp.answer == "The game master narrates the world."
    assert resp.contexts == ["The game master narrates the world to the players."]
    assert resp.total_tokens == 137
    assert resp.latency_ms >= 0.0


def test_network_failure_is_runtime_error():
    target = _target(FakeTransport(raises=TransportError("connection refused")))
    with pytest.raises(TargetRuntimeError):
        target.query("q")


def test_non_2xx_is_runtime_error():
    target = _target(FakeTransport(status=500, body={"error": "boom"}))
    with pytest.raises(TargetRuntimeError):
        target.query("q")


def test_off_protocol_body_is_runtime_error():
    target = _target(FakeTransport(body={"unexpected": "shape"}))
    with pytest.raises(TargetRuntimeError):
        target.query("q")


def test_missing_contexts_is_incomplete_response():
    body = _ok_body()
    del body["contexts"]
    target = _target(FakeTransport(body=body))
    with pytest.raises(IncompleteResponseError):
        target.query("q")


def test_missing_tokens_is_incomplete_response():
    body = _ok_body()
    del body["usage"]
    target = _target(FakeTransport(body=body))
    with pytest.raises(IncompleteResponseError):
        target.query("q")


def test_include_context_flag_sent_in_payload():
    transport = FakeTransport(body=_ok_body())
    target = OpenAICompatTarget(
        base_url="http://localhost:8000/v1",
        model="axon",
        transport=transport,
        include_context=False,
    )
    target.query("q")
    _url, payload = transport.calls[0]
    assert payload["include_context"] is False


def test_include_context_omitted_by_default():
    transport = FakeTransport(body=_ok_body())
    _target(transport).query("q")
    _url, payload = transport.calls[0]
    assert "include_context" not in payload
