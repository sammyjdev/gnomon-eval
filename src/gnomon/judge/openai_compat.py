"""OpenAI-compatible REST judge (v1 metrics), for hosted judge models such as
DeepInfra's Llama endpoint.

Wire format is the only thing that differs from gnomon.judge.ollama.OllamaJudge
-- POST base_url + "/chat/completions" with Bearer auth, response body at
choices[0].message.content -- so parsing/caching reuse parse_v1_judge_response
and JudgeCache verbatim: both judges are provably scored by the identical v1
contract (ADR-002), only the transport differs.
"""

from gnomon.domain.models import EvalCase, MetricScores, RagResponse
from gnomon.http import HttpTransport, TransportError, UrllibTransport
from gnomon.judge.cache import JudgeCache
from gnomon.judge.ollama import JudgeProtocolError, JudgeRuntimeError, parse_v1_judge_response
from gnomon.judge.prompts import build_prompt

_JSON_RESPONSE_FORMAT = {"type": "json_object"}


class OpenAICompatJudge:
    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str | None = None,
        transport: HttpTransport | None = None,
        cache: JudgeCache | None = None,
        timeout_s: float = 60.0,
        temperature: float = 0.0,
    ) -> None:
        self.model_name = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._transport = transport or UrllibTransport()
        self._cache = cache
        self._timeout_s = timeout_s
        self._temperature = temperature
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def score(self, case: EvalCase, response: RagResponse, *, seed: int, run: int) -> MetricScores:
        if self._cache is not None:
            cached = self._cache.get(case, response, self.model_name, seed=seed, run=run)
            if cached is not None:
                return cached

        result = self._score_all(case, response)

        if self._cache is not None:
            self._cache.put(case, response, self.model_name, seed=seed, run=run, scores=result)
        return result

    def _score_all(self, case: EvalCase, response: RagResponse) -> MetricScores:
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": build_prompt(case, response)}],
            "temperature": self._temperature,
            "response_format": _JSON_RESPONSE_FORMAT,
        }
        try:
            status, body = self._transport.post_json(
                self._url, payload, headers=self._headers, timeout_s=self._timeout_s
            )
        except TransportError as exc:
            raise JudgeRuntimeError(f"openai_compat judge unreachable: {exc}") from exc
        if status != 200:
            raise JudgeRuntimeError(f"openai_compat judge returned HTTP {status}: {body}")

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise JudgeProtocolError(f"judge output not parseable: {exc}") from exc
        return parse_v1_judge_response(content)
