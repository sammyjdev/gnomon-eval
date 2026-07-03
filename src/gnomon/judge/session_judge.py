"""Ollama-backed faithfulness judge for scripted sessions.

Sessions have no ground truth: OllamaJudge.build_prompt requires
EvalCase.expected_answer/expected_contexts, which scripted sessions do not
have (ADR-0010). This judge scores faithfulness only, against the contexts
the arm actually saw (retrieved contexts for the axon arm, the forwarded
transcript for the baseline arm). It reuses the same HTTP/JSON/seed/cache
machinery as OllamaJudge: options.seed = seed + run (ADR-008 denoising),
strict-JSON answer, JudgeCache keyed by content hash, named JudgeError
subclasses on any off-protocol response.
"""

import hashlib
import json

from gnomon.domain.models import EvalCase, MetricScores, RagResponse
from gnomon.http import HttpTransport, TransportError, UrllibTransport
from gnomon.judge.cache import JudgeCache
from gnomon.judge.ollama import JudgeProtocolError, JudgeRuntimeError
from gnomon.judge.session_prompts import build_session_prompt


class SessionOllamaJudge:
    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        cache: JudgeCache | None,
        transport: HttpTransport | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        self.model_name = model
        self._url = base_url.rstrip("/") + "/api/chat"
        self._cache = cache
        self._transport = transport or UrllibTransport()
        self._timeout_s = timeout_s

    def score_faithfulness(
        self, question: str, answer: str, contexts: list[str], *, seed: int, run: int
    ) -> float:
        # Fail closed inside the JudgeError taxonomy: empty inputs would
        # otherwise surface as a raw pydantic ValidationError from the
        # cache-key models (EvalCase requires a non-empty question).
        if not question or not answer or not contexts:
            raise JudgeRuntimeError(
                "session judge requires non-empty question, answer and contexts"
            )
        case, response = _cache_inputs(question, answer, contexts)
        if self._cache is not None:
            cached = self._cache.get(case, response, self.model_name, seed=seed, run=run)
            if cached is not None:
                return cached.scores["faithfulness"]

        score = self._score_faithfulness(question, answer, contexts, seed=seed, run=run)

        if self._cache is not None:
            self._cache.put(
                case,
                response,
                self.model_name,
                seed=seed,
                run=run,
                scores=MetricScores(scores={"faithfulness": score}),
            )
        return score

    def _score_faithfulness(
        self, question: str, answer: str, contexts: list[str], *, seed: int, run: int
    ) -> float:
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "user", "content": build_session_prompt(question, answer, contexts)}
            ],
            "format": "json",
            "stream": False,
            "options": {"seed": seed + run, "temperature": 0.0},
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
            parsed = json.loads(content)
            score = float(parsed["faithfulness"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise JudgeProtocolError(f"judge output not parseable: {exc}") from exc
        if not 0.0 <= score <= 1.0:
            # Deliberate divergence from OllamaJudge, which clamps: this score
            # feeds the run's quality gate, so an off-protocol value must fail
            # loudly instead of being silently normalized.
            raise JudgeProtocolError(f"faithfulness out of range: {score}")
        return score


def _cache_inputs(question: str, answer: str, contexts: list[str]) -> tuple[EvalCase, RagResponse]:
    content = json.dumps(
        {"question": question, "answer": answer, "contexts": contexts},
        sort_keys=True,
        separators=(",", ":"),
    )
    case = EvalCase(
        id=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        question=question,
        expected_answer="session",
        expected_contexts=["session"],
    )
    response = RagResponse(answer=answer, contexts=contexts, total_tokens=0, latency_ms=0.0)
    return case, response
