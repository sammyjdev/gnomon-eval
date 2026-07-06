import pytest

from gnomon.domain.chat import ChatCase, ChatResult
from gnomon.judge.chat_judge import ChatJudge, ChatJudgeRuntimeError


class StubToolMetric:
    def __init__(self, score: float, reason: str | None = None):
        self._score = score
        self.reason = reason
        self.measured_with = None

    def measure(self, test_case):
        self.measured_with = test_case
        self.score = self._score


class StubGEval:
    def __init__(self, score: float, reason: str | None = None):
        self._score = score
        self.reason = reason
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


def test_case_with_hallucination_criteria_metric_scores_hallucination_not_tone_brand():
    case = ChatCase(
        id="c4",
        conversation=[{"role": "user", "content": "Tem certeza que esta livre?"}],
        tenant={"name": "Clinica Aurora", "tone": "amigavel"},
        expected_tools=[],
        criteria="Must not reverse a prior no-availability answer.",
        criteria_metric="hallucination",
    )
    result = ChatResult(
        tool_called=None,
        tool_args={},
        reply_text="Continua sem horario disponivel.",
        total_tokens=20,
        latency_ms=200.0,
    )
    judge = ChatJudge(
        tool_metric_factory=lambda: StubToolMetric(1.0),
        geval_factory=lambda criteria: StubGEval(0.9),
    )
    scores = judge.score(case, result)
    assert scores["hallucination"] == 0.9
    assert "tone_brand" not in scores


def test_score_captures_each_metrics_reason_for_debugging():
    # A raw score alone doesn't explain why a reply got that score -- this
    # matters most exactly when a score looks wrong (e.g. an apparently
    # correct reply scoring 0.0), which is impossible to diagnose without
    # the underlying GEval/ToolCorrectnessMetric .reason text.
    case = ChatCase(
        id="c5",
        conversation=[{"role": "user", "content": "Qual o endereco?"}],
        tenant={"name": "Clinica Aurora", "tone": "amigavel"},
        expected_tools=["answer_question"],
        criteria="Must not invent a street address.",
    )
    result = ChatResult(
        tool_called="answer_question",
        tool_args={},
        reply_text="Nao tenho essa informacao.",
        total_tokens=10,
        latency_ms=100.0,
    )
    judge = ChatJudge(
        tool_metric_factory=lambda: StubToolMetric(1.0, reason="tool matched expected"),
        geval_factory=lambda criteria: StubGEval(0.0, reason="reply hedges instead of answering"),
    )
    judge.score(case, result)
    assert judge.last_reasons["tool_selection_accuracy"] == "tool matched expected"
    assert judge.last_reasons["tone_brand"] == "reply hedges instead of answering"


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
