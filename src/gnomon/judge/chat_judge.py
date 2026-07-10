"""DeepEval-backed judge for ChatEval: tool-calling accuracy and criteria-based
scoring, with GNOMON supplying the harness (dataset, aggregation, gate) and
DeepEval supplying the scoring primitives (ToolCorrectnessMetric, GEval) so
this repo does not reimplement tool-call diffing or LLM-as-judge prompting
from scratch. Two named failures, mirroring gnomon.judge.ollama's taxonomy:
ChatJudgeRuntimeError when the underlying provider call fails outright.
"""

from collections.abc import Callable

from gnomon.domain.chat import ChatCase, ChatResult


class ChatJudgeError(Exception):
    """Base for chat judge failures."""


class ChatJudgeRuntimeError(ChatJudgeError):
    """The underlying DeepEval metric call failed (provider unreachable,
    timed out, or returned an unusable response)."""


_SUPPRESSION_EVENT_TYPES = frozenset(
    {
        "malformed_reply_suppressed",
        "unverified_action_claim_suppressed",
        "persona_leak_suppressed",
    }
)


class ChatJudge:
    """`tool_metric_factory` and `geval_factory` are injected so tests can
    stub DeepEval's real metric classes; production wiring (Task 7) passes
    factories that build real deepeval.metrics.ToolCorrectnessMetric and
    deepeval.metrics.GEval instances configured for NIM-then-Ollama fallback.
    """

    def __init__(
        self,
        *,
        tool_metric_factory: Callable[[], object],
        geval_factory: Callable[[str], object],
    ) -> None:
        self._tool_metric_factory = tool_metric_factory
        self._geval_factory = geval_factory
        self.last_reasons: dict[str, str | None] = {}
        self.last_generation_status: str | None = None

    def score(self, case: ChatCase, result: ChatResult) -> dict[str, float]:
        self.last_generation_status = None  # reset at START, mirrors CR-04
        scores: dict[str, float] = {}
        reasons: dict[str, str | None] = {}
        try:
            tool_score, tool_reason = self._score_tool_selection(case, result)
            scores["tool_selection_accuracy"] = tool_score
            reasons["tool_selection_accuracy"] = tool_reason
            if case.criteria:
                criteria_score, criteria_reason, gen_status = self._score_criteria(case, result)
                scores[case.criteria_metric] = criteria_score
                reasons[case.criteria_metric] = criteria_reason
                self.last_generation_status = gen_status
        except Exception as exc:  # noqa: BLE001 - deliberately broad: any
            # provider failure (NIM down, Ollama fallback also down, DeepEval
            # raising its own exception types) must fail closed as one named
            # error, not leak a random third-party exception to the runner.
            raise ChatJudgeRuntimeError(f"chat judge scoring failed: {exc}") from exc
        self.last_reasons = reasons
        return scores

    def _score_tool_selection(self, case: ChatCase, result: ChatResult) -> tuple[float, str | None]:
        from deepeval.test_case import LLMTestCase, ToolCall

        metric = self._tool_metric_factory()
        actual_tools = [ToolCall(name=result.tool_called)] if result.tool_called else []
        expected_tools = [ToolCall(name=name) for name in case.expected_tools]
        test_case = LLMTestCase(
            input=_render_conversation(case.conversation),
            actual_output=result.reply_text,
            tools_called=actual_tools,
            expected_tools=expected_tools,
        )
        metric.measure(test_case)
        return float(metric.score), getattr(metric, "reason", None)

    def _score_criteria(
        self, case: ChatCase, result: ChatResult
    ) -> tuple[float, str | None, str | None]:
        import json

        from deepeval.test_case import LLMTestCase

        # A generation_events entry already tells us the reply is a known
        # fallback (malformed/unverified-action/persona-leak suppression) --
        # scoring that with GEval would risk misjudging a generation-level
        # failure as a content/hallucination verdict, and burns an LLM call
        # whose answer is already known. Use .get(), never [...]: a
        # malformed entry missing "event_type" must not raise here (score()
        # wraps any exception as ChatJudgeRuntimeError, which would be wrong
        # for a merely-malformed telemetry entry).
        for event in result.generation_events:
            event_type = event.get("event_type")
            if event_type in _SUPPRESSION_EVENT_TYPES:
                return 0.0, f"generation suppressed ({event_type}); GEval skipped", event_type

        # geval_factory now builds GEval from a shared, hand-written rubric
        # keyed by criteria_metric (see gnomon.judge.rubrics) -- the
        # case-specific requirement reaches the judge via expected_output,
        # and the tenant's real configured data via context, so the judge
        # can actually verify a claim like "must state the configured
        # price" instead of guessing.
        metric = self._geval_factory(case.criteria_metric)
        test_case = LLMTestCase(
            input=_render_conversation(case.conversation),
            actual_output=result.reply_text,
            expected_output=case.criteria,
            context=[json.dumps(case.tenant, ensure_ascii=False)],
        )
        metric.measure(test_case)
        return float(metric.score), getattr(metric, "reason", None), None


def _render_conversation(conversation: list[dict]) -> str:
    return "\n".join(f"{turn['role']}: {turn['content']}" for turn in conversation)
