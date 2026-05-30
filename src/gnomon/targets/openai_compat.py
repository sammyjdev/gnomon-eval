"""OpenAI-compatible REST adapter (RF-02, RF-03).

Translates the domain's RagTarget contract to an OpenAI chat/completions
endpoint. The error taxonomy keeps VAL-02 honest: a config-class failure
(bad URL, missing model) is a different exception from a runtime-class
failure (unreachable, timeout, non-2xx, off-protocol body). An incomplete
response (no contexts or no token count) is rejected explicitly (VAL-03),
never coerced to a silent zero that would contaminate cost or a metric.

Contexts source: OpenAI chat/completions has no standard field for retrieved
contexts, so the target returns them in a configurable top-level extension
field (default "contexts"). See ADR-005.
"""

import time

from gnomon.domain.models import RagResponse
from gnomon.http import HttpTransport, TransportError, UrllibTransport


class OpenAICompatError(Exception):
    """Base for target adapter failures."""


class TargetConfigError(OpenAICompatError):
    """Misconfiguration detected before or independent of the call (VAL-02)."""


class TargetRuntimeError(OpenAICompatError):
    """Target unreachable, timed out, errored or answered off-protocol (VAL-02)."""


class IncompleteResponseError(OpenAICompatError):
    """Response missing contexts or token count (VAL-03)."""


class OpenAICompatTarget:
    """RagTarget speaking OpenAI chat/completions over REST."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        transport: HttpTransport | None = None,
        api_key: str | None = None,
        timeout_s: float = 30.0,
        contexts_field: str = "contexts",
    ) -> None:
        if not base_url:
            raise TargetConfigError("openai_compat target requires a base_url")
        if not model:
            raise TargetConfigError("openai_compat target requires a model")
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._transport = transport or UrllibTransport()
        self._timeout_s = timeout_s
        self._contexts_field = contexts_field
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def query(self, question: str) -> RagResponse:
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": question}],
        }
        start = time.perf_counter()
        try:
            status, body = self._transport.post_json(
                self._url, payload, headers=self._headers, timeout_s=self._timeout_s
            )
        except TransportError as exc:
            raise TargetRuntimeError(f"target unreachable: {exc}") from exc
        latency_ms = (time.perf_counter() - start) * 1000.0

        if status != 200:
            raise TargetRuntimeError(f"target returned HTTP {status}")

        try:
            answer = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise TargetRuntimeError("target answered off-protocol (no choices/message)") from exc

        contexts = body.get(self._contexts_field)
        total_tokens = (body.get("usage") or {}).get("total_tokens")
        if contexts is None or total_tokens is None:
            raise IncompleteResponseError(
                "response missing "
                f"{'contexts' if contexts is None else 'usage.total_tokens'} (VAL-03)"
            )

        return RagResponse(
            answer=answer,
            contexts=list(contexts),
            total_tokens=int(total_tokens),
            latency_ms=latency_ms,
        )
