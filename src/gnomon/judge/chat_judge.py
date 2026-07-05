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

    def score(self, case: ChatCase, result: ChatResult) -> dict[str, float]:
        scores: dict[str, float] = {}
        try:
            scores["tool_selection_accuracy"] = self._score_tool_selection(case, result)
            if case.criteria:
                scores[self._criteria_metric_name(case)] = self._score_criteria(case, result)
        except Exception as exc:  # noqa: BLE001 - deliberately broad: any
            # provider failure (NIM down, Ollama fallback also down, DeepEval
            # raising its own exception types) must fail closed as one named
            # error, not leak a random third-party exception to the runner.
            raise ChatJudgeRuntimeError(f"chat judge scoring failed: {exc}") from exc
        return scores

    def _score_tool_selection(self, case: ChatCase, result: ChatResult) -> float:
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
        return float(metric.score)

    def _score_criteria(self, case: ChatCase, result: ChatResult) -> float:
        from deepeval.test_case import LLMTestCase

        metric = self._geval_factory(case.criteria)
        test_case = LLMTestCase(
            input=_render_conversation(case.conversation),
            actual_output=result.reply_text,
        )
        metric.measure(test_case)
        return float(metric.score)

    def _criteria_metric_name(self, case: ChatCase) -> str:
        # The 17-case dataset only ever needs one of these two per case
        # (see the design doc's dataset section); "hallucination" is chosen
        # for the two cases whose criteria mention tool-output consistency.
        if "tool" in case.criteria.lower() and ("hallucin" in case.id or "false" in case.id):
            return "hallucination"
        return "tone_brand"


def _render_conversation(conversation: list[dict]) -> str:
    return "\n".join(f"{turn['role']}: {turn['content']}" for turn in conversation)
