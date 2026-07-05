import pytest

from gnomon.domain.chat import ChatCase, ChatResult
from gnomon.judge.chat_judge import ChatJudge, ChatJudgeRuntimeError


class StubToolMetric:
    def __init__(self, score: float):
        self._score = score
        self.measured_with = None

    def measure(self, test_case):
        self.measured_with = test_case
        self.score = self._score


class StubGEval:
    def __init__(self, score: float):
        self._score = score
        self.measured_with = None

    def measure(self, test_case):
        self.measured_with = test_case
        self.score = self._score


def test_tool_selection_case_only_scores_tool_selection_accuracy():
    case = ChatCase(
        id="c1",
        conversation=[{"role": "user", "content": "Qual o horario?"}],
        tenant={"name": "Clinica Aurora", "tone": "amigavel"},
        expected_tools=["answer_question"],
    )
    result = ChatResult(
        tool_called="answer_question",
        tool_args={"question": "Qual o horario?"},
        reply_text="Funcionamos das 9h as 18h.",
        total_tokens=50,
        latency_ms=400.0,
    )
    stub = StubToolMetric(1.0)
    judge = ChatJudge(
        tool_metric_factory=lambda: stub,
        geval_factory=lambda criteria: StubGEval(1.0),
    )
    scores = judge.score(case, result)
    assert scores == {"tool_selection_accuracy": 1.0}
    assert [tc.name for tc in stub.measured_with.tools_called] == ["answer_question"]
    assert [tc.name for tc in stub.measured_with.expected_tools] == ["answer_question"]


def test_case_with_criteria_also_scores_a_geval_metric():
    case = ChatCase(
        id="c2",
        conversation=[{"role": "user", "content": "Oi, quem esta falando?"}],
        tenant={"name": "Clinica Aurora", "tone": "amigavel"},
        expected_tools=[],
        criteria="Must never say 'sou a Lina'.",
    )
    result = ChatResult(
        tool_called=None,
        tool_args={},
        reply_text="Oi! Voce esta falando com o atendimento da Clinica Aurora.",
        total_tokens=30,
        latency_ms=300.0,
    )
    stub = StubToolMetric(1.0)
    judge = ChatJudge(
        tool_metric_factory=lambda: stub,
        geval_factory=lambda criteria: StubGEval(0.95),
    )
    scores = judge.score(case, result)
    assert scores["tool_selection_accuracy"] == 1.0
    assert scores["tone_brand"] == 0.95
    assert stub.measured_with.tools_called == []
    assert stub.measured_with.expected_tools == []


def test_both_providers_failing_raises_chat_judge_runtime_error():
    def raising_geval(criteria):
        class Raising:
            def measure(self, test_case):
                raise RuntimeError("both NIM and Ollama unreachable")

        return Raising()

    case = ChatCase(
        id="c3",
        conversation=[{"role": "user", "content": "Oi"}],
        tenant={"name": "Clinica Aurora", "tone": "amigavel"},
        expected_tools=[],
        criteria="Must sound warm.",
    )
    result = ChatResult(
        tool_called=None, tool_args={}, reply_text="Oi!", total_tokens=10, latency_ms=100.0
    )
    judge = ChatJudge(
        tool_metric_factory=lambda: StubToolMetric(1.0),
        geval_factory=raising_geval,
    )
    with pytest.raises(ChatJudgeRuntimeError):
        judge.score(case, result)
