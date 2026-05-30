"""Ollama-backed judge (RF-04, ADR-002).

Scores faithfulness and context_precision by asking a local Ollama model for
a JSON score per metric. options.seed = seed + run gives a deterministic
sequence per declared seed for a fixed model/host (ADR-007 — reproducibility
within measured variance, not bit-exact). Scores route through JudgeCache so
a repeat of the same (case, response, model, seed, run) does not re-call the
model. A model answer that is not the agreed JSON shape raises a named error
instead of fabricating a score.
"""

import json

from gnomon.domain.models import EvalCase, MetricScores, RagResponse
from gnomon.http import HttpTransport, TransportError, UrllibTransport
from gnomon.judge.cache import JudgeCache
from gnomon.judge.prompts import build_prompt
from gnomon.metrics.names import V1_METRICS


class JudgeError(Exception):
    """Base for judge failures."""


class JudgeRuntimeError(JudgeError):
    """Ollama unreachable, timed out or returned non-2xx."""


class JudgeProtocolError(JudgeError):
    """Model answer was not the agreed {"score": float} JSON shape."""


class OllamaJudge:
    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        transport: HttpTransport | None = None,
        cache: JudgeCache | None = None,
        timeout_s: float = 60.0,
        temperature: float = 0.0,
    ) -> None:
        self.model_name = model
        self._url = base_url.rstrip("/") + "/api/chat"
        self._transport = transport or UrllibTransport()
        self._cache = cache
        self._timeout_s = timeout_s
        self._temperature = temperature

    def score(self, case: EvalCase, response: RagResponse, *, seed: int, run: int) -> MetricScores:
        if self._cache is not None:
            cached = self._cache.get(case, response, self.model_name, seed=seed, run=run)
            if cached is not None:
                return cached

        scores = {
            metric: self._score_one(metric, case, response, seed=seed, run=run)
            for metric in V1_METRICS
        }
        result = MetricScores(scores=scores)

        if self._cache is not None:
            self._cache.put(case, response, self.model_name, seed=seed, run=run, scores=result)
        return result

    def _score_one(
        self, metric: str, case: EvalCase, response: RagResponse, *, seed: int, run: int
    ) -> float:
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": build_prompt(metric, case, response)}],
            "format": "json",
            "stream": False,
            "options": {"seed": seed + run, "temperature": self._temperature},
        }
        try:
            status, body = self._transport.post_json(
                self._url, payload, headers={}, timeout_s=self._timeout_s
            )
        except TransportError as exc:
            raise JudgeRuntimeError(f"ollama unreachable: {exc}") from exc
        if status != 200:
            raise JudgeRuntimeError(f"ollama returned HTTP {status}")

        try:
            content = body["message"]["content"]
            value = float(json.loads(content)["score"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise JudgeProtocolError(f"judge output not parseable for {metric!r}: {exc}") from exc
        return max(0.0, min(1.0, value))
