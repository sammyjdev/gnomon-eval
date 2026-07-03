"""Session-turn REST target for Wave 2 savings evaluation."""

import time

from pydantic import BaseModel, ConfigDict

from gnomon.domain.session import Arm
from gnomon.http import HttpTransport, TransportError, UrllibTransport
from gnomon.targets.openai_compat import (
    IncompleteResponseError,
    TargetConfigError,
    TargetRuntimeError,
)


class TurnResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    answer: str
    contexts: list[str]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    usage_source: str


class SessionTarget:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        transport: HttpTransport | None = None,
        api_key: str | None = None,
        timeout_s: float = 60.0,
        recall_max_tokens: int = 2000,
        window_turns: int = 0,
    ) -> None:
        if not base_url:
            raise TargetConfigError("session target requires a base_url")
        if not model:
            raise TargetConfigError("session target requires a model")
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._transport = transport or UrllibTransport()
        self._timeout_s = timeout_s
        self._recall_max_tokens = recall_max_tokens
        self._window_turns = window_turns
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def run_turn(self, history: list[dict], question: str, *, arm: Arm) -> TurnResult:
        if arm == "axon":
            messages = [{"role": "user", "content": question}]
            forward_history = False
            if self._window_turns > 0:
                window = history[-(2 * self._window_turns) :]
                messages = [*window, {"role": "user", "content": question}]
                forward_history = True
            payload = {
                "model": self._model,
                "messages": messages,
                "include_context": True,
                "forward_history": forward_history,
                "recall_max_tokens": self._recall_max_tokens,
            }
        else:
            payload = {
                "model": self._model,
                "messages": [*history, {"role": "user", "content": question}],
                "include_context": False,
                "forward_history": True,
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

        usage = body.get("usage") or {}
        required_usage = (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "source",
        )
        missing = next((key for key in required_usage if key not in usage), None)
        if missing is not None:
            raise IncompleteResponseError(f"response missing usage.{missing}")

        return TurnResult(
            answer=answer,
            contexts=list(body.get("contexts", [])),
            prompt_tokens=int(usage["prompt_tokens"]),
            completion_tokens=int(usage["completion_tokens"]),
            total_tokens=int(usage["total_tokens"]),
            latency_ms=latency_ms,
            usage_source=str(usage["source"]),
        )
