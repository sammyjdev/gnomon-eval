"""Ollama-backed judge (RF-04, ADR-002).

Scores faithfulness and context_precision in ONE call to a local Ollama model,
which returns a JSON object keyed by metric name (RNF-06 cost: one model call
per score(), not one per metric). options.seed = seed + run gives a
deterministic sequence per declared seed for a fixed model/host (ADR-007 —
reproducibility within measured variance, not bit-exact). Scores route through
JudgeCache so a repeat of the same (case, response, model, seed, run) does not
re-call the model. A model answer that is not the agreed JSON shape — or that
omits a v1 metric — raises a named error instead of fabricating a score.
For empty-context responses, context_precision is deterministically 0.0 without asking
the model to score it, while faithfulness is still judged normally in that same call.
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
    """Model answer was not the agreed JSON object keyed by metric name."""


def parse_v1_judge_response(content: str, *, metrics: tuple[str, ...] = V1_METRICS) -> MetricScores:
    """Parse a v1 judge response: a JSON object keyed by V1_METRICS, each value
    clamped to [0, 1]. Raises JudgeProtocolError on any shape violation (not
    JSON, missing a v1 metric key, non-numeric value) -- the stable public
    parse contract downstream (glyph ADR-G8) pins against.
    """
    try:
        parsed = json.loads(content)
        return MetricScores(
            scores={metric: max(0.0, min(1.0, float(parsed[metric]))) for metric in metrics}
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise JudgeProtocolError(f"judge output not parseable: {exc}") from exc


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

        result = self._score_all(case, response, seed=seed, run=run)

        if self._cache is not None:
            self._cache.put(case, response, self.model_name, seed=seed, run=run, scores=result)
        return result

    def _score_all(
        self, case: EvalCase, response: RagResponse, *, seed: int, run: int
    ) -> MetricScores:
        metrics = ("faithfulness",) if not response.contexts else V1_METRICS
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "user", "content": build_prompt(case, response, metrics=metrics)}
            ],
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
        except (KeyError, TypeError) as exc:
            raise JudgeProtocolError(f"judge output not parseable: {exc}") from exc
        result = parse_v1_judge_response(content, metrics=metrics)
        if not response.contexts:
            return MetricScores(scores={**result.scores, "context_precision": 0.0})
        return result
