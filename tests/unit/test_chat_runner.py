from gnomon.domain.chat import ChatCase, ChatResult
from gnomon.runner.chat_runner import run_chat_eval


class FakeTarget:
    def __init__(self, results: dict[str, ChatResult]):
        self._results = results

    def run(self, case: ChatCase) -> ChatResult:
        return self._results[case.id]


class FakeJudge:
    def __init__(self, scores: dict[str, dict[str, float]]):
        self._scores = scores

    def score(self, case: ChatCase, result: ChatResult) -> dict[str, float]:
        return self._scores[case.id]


def test_run_chat_eval_aggregates_per_metric_with_confidence_intervals():
    cases = [
        ChatCase(
            id="a",
            conversation=[{"role": "user", "content": "Oi"}],
            tenant={"name": "T", "tone": "amigavel"},
            expected_tools=["answer_question"],
        ),
        ChatCase(
            id="b",
            conversation=[{"role": "user", "content": "Oi 2"}],
            tenant={"name": "T", "tone": "amigavel"},
            expected_tools=["answer_question"],
        ),
    ]
    results = {
        "a": ChatResult(
            tool_called="answer_question", reply_text="ok", total_tokens=10, latency_ms=100.0
        ),
        "b": ChatResult(
            tool_called="answer_question", reply_text="ok", total_tokens=20, latency_ms=200.0
        ),
    }
    scores = {
        "a": {"tool_selection_accuracy": 1.0},
        "b": {"tool_selection_accuracy": 0.0},
    }

    report = run_chat_eval(cases, FakeTarget(results), FakeJudge(scores), seed=42)

    metric = report.metric("tool_selection_accuracy")
    assert metric.n == 2
    assert metric.mean == 0.5
    assert report.total_tokens == 30
    assert report.mean_latency_ms == 150.0
