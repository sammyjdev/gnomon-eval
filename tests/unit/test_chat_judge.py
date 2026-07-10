import json

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


def test_score_criteria_passes_criteria_metric_not_criteria_text_to_geval_factory():
    # GEval's evaluation_steps are now a small, shared, hand-written rubric
    # keyed by criteria_metric ("hallucination"/"tone_brand") instead of
    # auto-generated per case from the raw criteria string -- the factory
    # only needs to know which rubric family to build, not the case's
    # specific criteria text (that now flows through as expected_output).
    case = ChatCase(
        id="c6",
        conversation=[{"role": "user", "content": "Oi"}],
        tenant={"name": "T", "tone": "amigavel"},
        expected_tools=[],
        criteria="Must not invent a price.",
        criteria_metric="hallucination",
    )
    result = ChatResult(
        tool_called=None, tool_args={}, reply_text="Oi!", total_tokens=1, latency_ms=1.0
    )
    recorded = []

    def geval_factory(criteria_metric):
        recorded.append(criteria_metric)
        return StubGEval(1.0)

    judge = ChatJudge(tool_metric_factory=lambda: StubToolMetric(1.0), geval_factory=geval_factory)
    judge.score(case, result)

    assert recorded == ["hallucination"]


def test_score_criteria_passes_case_criteria_as_expected_output_and_tenant_as_context():
    # Root fix for a judge that can't verify its own scoring criteria: the
    # judge previously only saw the conversation and the reply, never the
    # tenant's actual configured data, so a criteria like "must state the
    # configured price" had no ground truth to check against.
    case = ChatCase(
        id="c7",
        conversation=[{"role": "user", "content": "Qual o preco da fisioterapia?"}],
        tenant={
            "name": "Fisio Movimento",
            "tone": "profissional",
            "services": [{"name": "Sessao", "price_cents": 16000}],
        },
        expected_tools=["answer_question"],
        criteria="Must provide the configured price and not invent medical report availability.",
        criteria_metric="hallucination",
    )
    result = ChatResult(
        tool_called="answer_question",
        tool_args={},
        reply_text="A sessao custa R$ 160.",
        total_tokens=10,
        latency_ms=100.0,
    )
    stub = StubGEval(0.9)
    judge = ChatJudge(
        tool_metric_factory=lambda: StubToolMetric(1.0),
        geval_factory=lambda criteria_metric: stub,
    )
    judge.score(case, result)

    assert stub.measured_with.expected_output == case.criteria
    assert json.loads(stub.measured_with.context[0]) == case.tenant


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


class _SpyGEval:
    """Records whether measure() was ever called -- used to prove the
    suppression short-circuit skips the LLM call entirely, not just that it
    overrides the score afterward."""

    def __init__(self, score: float = 1.0, reason: str | None = None):
        self._score = score
        self.reason = reason
        self.measured_with = None
        self.measure_called = False

    def measure(self, test_case):
        self.measure_called = True
        self.measured_with = test_case
        self.score = self._score


def _criteria_case(criteria_metric: str = "tone_brand") -> ChatCase:
    return ChatCase(
        id="c-suppressed",
        conversation=[{"role": "user", "content": "Oi"}],
        tenant={"name": "Clinica Aurora", "tone": "amigavel"},
        expected_tools=[],
        criteria="Must sound warm.",
        criteria_metric=criteria_metric,
    )


def test_suppression_event_short_circuits_criteria_with_zero_and_skips_geval():
    case = _criteria_case()
    result = ChatResult(
        tool_called=None,
        tool_args={},
        reply_text="Desculpe, nao entendi.",
        total_tokens=5,
        latency_ms=50.0,
        generation_events=[{"event_type": "malformed_reply_suppressed"}],
    )
    spy = _SpyGEval()
    judge = ChatJudge(
        tool_metric_factory=lambda: StubToolMetric(1.0),
        geval_factory=lambda criteria_metric: spy,
    )
    scores = judge.score(case, result)
    assert scores["tone_brand"] == 0.0
    assert spy.measure_called is False


def test_suppression_sets_last_generation_status_to_event_type():
    case = _criteria_case()
    result = ChatResult(
        tool_called=None,
        tool_args={},
        reply_text="Desculpe, nao entendi.",
        total_tokens=5,
        latency_ms=50.0,
        generation_events=[{"event_type": "persona_leak_suppressed"}],
    )
    judge = ChatJudge(
        tool_metric_factory=lambda: StubToolMetric(1.0),
        geval_factory=lambda criteria_metric: _SpyGEval(),
    )
    judge.score(case, result)
    assert judge.last_generation_status == "persona_leak_suppressed"


@pytest.mark.parametrize(
    "event_type",
    [
        "malformed_reply_suppressed",
        "unverified_action_claim_suppressed",
        "persona_leak_suppressed",
    ],
)
def test_each_of_the_three_suppression_types_fires(event_type):
    case = _criteria_case()
    result = ChatResult(
        tool_called=None,
        tool_args={},
        reply_text="Desculpe, nao entendi.",
        total_tokens=5,
        latency_ms=50.0,
        generation_events=[{"event_type": event_type}],
    )
    spy = _SpyGEval()
    judge = ChatJudge(
        tool_metric_factory=lambda: StubToolMetric(1.0),
        geval_factory=lambda criteria_metric: spy,
    )
    scores = judge.score(case, result)
    assert scores["tone_brand"] == 0.0
    assert spy.measure_called is False
    assert judge.last_generation_status == event_type


def test_non_suppression_event_does_not_short_circuit():
    case = _criteria_case()
    result = ChatResult(
        tool_called=None,
        tool_args={},
        reply_text="Oi! Voce esta falando com a Clinica Aurora.",
        total_tokens=5,
        latency_ms=50.0,
        generation_events=[{"event_type": "some_other_event"}],
    )
    spy = _SpyGEval(0.8)
    judge = ChatJudge(
        tool_metric_factory=lambda: StubToolMetric(1.0),
        geval_factory=lambda criteria_metric: spy,
    )
    scores = judge.score(case, result)
    assert scores["tone_brand"] == 0.8
    assert spy.measure_called is True
    assert judge.last_generation_status is None


def test_empty_generation_events_uses_normal_geval_flow():
    case = _criteria_case()
    result = ChatResult(
        tool_called=None,
        tool_args={},
        reply_text="Oi! Voce esta falando com a Clinica Aurora.",
        total_tokens=5,
        latency_ms=50.0,
    )
    spy = _SpyGEval(0.7)
    judge = ChatJudge(
        tool_metric_factory=lambda: StubToolMetric(1.0),
        geval_factory=lambda criteria_metric: spy,
    )
    scores = judge.score(case, result)
    assert scores["tone_brand"] == 0.7
    assert spy.measure_called is True
    assert judge.last_generation_status is None


def test_first_suppression_match_wins_on_multiple_events():
    case = _criteria_case()
    result = ChatResult(
        tool_called=None,
        tool_args={},
        reply_text="Desculpe, nao entendi.",
        total_tokens=5,
        latency_ms=50.0,
        generation_events=[
            {"event_type": "malformed_reply_suppressed"},
            {"event_type": "persona_leak_suppressed"},
        ],
    )
    judge = ChatJudge(
        tool_metric_factory=lambda: StubToolMetric(1.0),
        geval_factory=lambda criteria_metric: _SpyGEval(),
    )
    judge.score(case, result)
    assert judge.last_generation_status == "malformed_reply_suppressed"


def test_last_generation_status_stays_none_when_no_criteria():
    case = ChatCase(
        id="c-no-criteria",
        conversation=[{"role": "user", "content": "Qual o horario?"}],
        tenant={"name": "Clinica Aurora", "tone": "amigavel"},
        expected_tools=["answer_question"],
    )
    result = ChatResult(
        tool_called="answer_question",
        tool_args={},
        reply_text="Funcionamos das 9h as 18h.",
        total_tokens=5,
        latency_ms=50.0,
        generation_events=[{"event_type": "malformed_reply_suppressed"}],
    )
    judge = ChatJudge(
        tool_metric_factory=lambda: StubToolMetric(1.0),
        geval_factory=lambda criteria_metric: _SpyGEval(),
    )
    judge.score(case, result)
    assert judge.last_generation_status is None


def test_last_generation_status_reset_to_none_on_second_scoring():
    suppressed_case = _criteria_case()
    suppressed_result = ChatResult(
        tool_called=None,
        tool_args={},
        reply_text="Desculpe, nao entendi.",
        total_tokens=5,
        latency_ms=50.0,
        generation_events=[{"event_type": "malformed_reply_suppressed"}],
    )
    clean_case = _criteria_case()
    clean_result = ChatResult(
        tool_called=None,
        tool_args={},
        reply_text="Oi! Voce esta falando com a Clinica Aurora.",
        total_tokens=5,
        latency_ms=50.0,
    )
    judge = ChatJudge(
        tool_metric_factory=lambda: StubToolMetric(1.0),
        geval_factory=lambda criteria_metric: _SpyGEval(0.9),
    )
    judge.score(suppressed_case, suppressed_result)
    assert judge.last_generation_status == "malformed_reply_suppressed"

    judge.score(clean_case, clean_result)
    assert judge.last_generation_status is None


def test_last_generation_status_resets_even_when_next_case_has_no_criteria():
    # Unlike the test above, the second case has NO criteria at all, so
    # score()'s `if case.criteria:` block never runs and never sets
    # last_generation_status itself -- only the reset-at-start-of-score()
    # line can clear the stale status left over from the first, suppressed
    # case. Dropping that reset line survives every other test in this file.
    suppressed_case = _criteria_case()
    suppressed_result = ChatResult(
        tool_called=None,
        tool_args={},
        reply_text="Desculpe, nao entendi.",
        total_tokens=5,
        latency_ms=50.0,
        generation_events=[{"event_type": "malformed_reply_suppressed"}],
    )
    no_criteria_case = ChatCase(
        id="c-no-criteria-2",
        conversation=[{"role": "user", "content": "Qual o horario?"}],
        tenant={"name": "Clinica Aurora", "tone": "amigavel"},
        expected_tools=["answer_question"],
    )
    no_criteria_result = ChatResult(
        tool_called="answer_question",
        tool_args={},
        reply_text="Funcionamos das 9h as 18h.",
        total_tokens=5,
        latency_ms=50.0,
    )
    judge = ChatJudge(
        tool_metric_factory=lambda: StubToolMetric(1.0),
        geval_factory=lambda criteria_metric: _SpyGEval(0.9),
    )
    judge.score(suppressed_case, suppressed_result)
    assert judge.last_generation_status == "malformed_reply_suppressed"

    judge.score(no_criteria_case, no_criteria_result)
    assert judge.last_generation_status is None


def test_malformed_generation_event_missing_event_type_does_not_crash():
    # A generation_events entry missing "event_type" altogether (schema
    # drift, or a non-suppression event type this repo doesn't name) must
    # not crash score()'s broad except into a false ChatJudgeRuntimeError --
    # it should just fall through to the normal GEval flow.
    case = _criteria_case()
    result = ChatResult(
        tool_called=None,
        tool_args={},
        reply_text="Oi! Voce esta falando com a Clinica Aurora.",
        total_tokens=5,
        latency_ms=50.0,
        generation_events=[{"payload": {}, "created_at": "2026-07-09T00:00:00Z"}],
    )
    spy = _SpyGEval(0.6)
    judge = ChatJudge(
        tool_metric_factory=lambda: StubToolMetric(1.0),
        geval_factory=lambda criteria_metric: spy,
    )
    scores = judge.score(case, result)
    assert scores[case.criteria_metric] == 0.6
    assert spy.measure_called is True
    assert judge.last_generation_status is None
