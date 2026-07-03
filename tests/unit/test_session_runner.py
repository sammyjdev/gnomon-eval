import pytest

from gnomon.domain.session import Session
from gnomon.runner.session_runner import run_sessions
from gnomon.targets.session_target import TurnResult


class FakeTarget:
    def __init__(self, *, empty_contexts_for=()):
        self.calls = []
        self._empty_contexts_for = set(empty_contexts_for)

    def run_turn(self, history, question, *, arm):
        self.calls.append(
            {
                "history": [message.copy() for message in history],
                "question": question,
                "arm": arm,
            }
        )
        empty = arm == "axon" and question in self._empty_contexts_for
        return TurnResult(
            answer=f"{arm} answer to {question}",
            contexts=[] if empty else [f"{arm} context for {question}"],
            prompt_tokens=11,
            completion_tokens=7,
            total_tokens=18,
            latency_ms=42.5,
            usage_source="provider",
        )


class FakeJudge:
    def __init__(self):
        self.calls = []

    def score_faithfulness(self, question, answer, contexts, *, seed, run):
        self.calls.append(
            {
                "question": question,
                "answer": answer,
                "contexts": list(contexts),
                "seed": seed,
                "run": run,
            }
        )
        return 0.8 if answer.startswith("axon ") else 0.6


def _sessions():
    return [
        Session(id="s1", topic="Topic 1", turns=["q1", "q2"]),
        Session(id="s2", topic="Topic 2", turns=["q3", "q4"]),
    ]


def _run(judge_runs=3):
    target = FakeTarget()
    judge = FakeJudge()
    report = run_sessions(
        _sessions(),
        target,
        judge,
        judge_runs=judge_runs,
        seed=123,
        confidence_level=0.95,
    )
    return report, target, judge


def test_turn_costs_cover_every_session_turn_and_arm():
    report, _target, _judge = _run()

    assert len(report.turn_costs) == 2 * 2 * 2
    assert [(cost.session_id, cost.turn, cost.arm) for cost in report.turn_costs] == [
        ("s1", 0, "axon"),
        ("s1", 1, "axon"),
        ("s1", 0, "baseline"),
        ("s1", 1, "baseline"),
        ("s2", 0, "axon"),
        ("s2", 1, "axon"),
        ("s2", 0, "baseline"),
        ("s2", 1, "baseline"),
    ]
    assert all(cost.prompt_tokens == 11 for cost in report.turn_costs)
    assert all(cost.completion_tokens == 7 for cost in report.turn_costs)
    assert all(cost.total_tokens == 18 for cost in report.turn_costs)
    assert all(cost.latency_ms == 42.5 for cost in report.turn_costs)
    assert all(cost.usage_source == "provider" for cost in report.turn_costs)


def test_baseline_history_grows_by_two_messages_per_turn():
    _report, target, _judge = _run()

    baseline_calls = [call for call in target.calls if call["arm"] == "baseline"]

    assert [len(call["history"]) for call in baseline_calls] == [0, 2, 0, 2]


def test_axon_history_is_accumulated_and_passed_to_target():
    _report, target, _judge = _run()

    axon_calls = [call for call in target.calls if call["arm"] == "axon"]

    assert [len(call["history"]) for call in axon_calls] == [0, 2, 0, 2]


def test_arm_histories_use_their_own_answers():
    _report, target, _judge = _run()

    axon_second = next(
        call for call in target.calls if call["arm"] == "axon" and call["question"] == "q2"
    )
    baseline_second = next(
        call for call in target.calls if call["arm"] == "baseline" and call["question"] == "q2"
    )

    assert axon_second["history"][1]["content"] == "axon answer to q1"
    assert baseline_second["history"][1]["content"] == "baseline answer to q1"


def test_judge_is_called_once_per_session_arm_and_run():
    _report, _target, judge = _run(judge_runs=4)

    assert len(judge.calls) == 2 * 2 * 4
    assert [call["run"] for call in judge.calls[:4]] == [0, 1, 2, 3]


def test_final_faithfulness_is_aggregated_over_sessions():
    report, _target, _judge = _run()

    assert set(report.final_faithfulness) == {"axon", "baseline"}
    assert report.final_faithfulness["axon"].metric == "final_faithfulness_axon"
    assert report.final_faithfulness["baseline"].metric == "final_faithfulness_baseline"
    assert report.final_faithfulness["axon"].n == 2
    assert report.final_faithfulness["baseline"].n == 2


def test_empty_final_contexts_score_zero_without_judge_and_keep_costs():
    # Final-turn retrieval miss on the axon arm: zero admissible evidence is
    # scored 0.0 by metric definition - no judge call, session stays in the
    # CI, and no collected TurnCost is lost.
    target = FakeTarget(empty_contexts_for={"q2"})
    judge = FakeJudge()

    report = run_sessions(_sessions(), target, judge, judge_runs=3, seed=123, confidence_level=0.95)

    assert len(report.turn_costs) == 2 * 2 * 2
    # s1's axon arm skipped the judge; the 3 remaining (session, arm) pairs
    # were judged judge_runs times each.
    assert len(judge.calls) == 3 * 3
    assert not any(call["answer"] == "axon answer to q2" for call in judge.calls)
    assert report.final_faithfulness["axon"].n == 2


def test_judge_runs_below_one_is_rejected():
    with pytest.raises(ValueError):
        run_sessions(_sessions(), FakeTarget(), FakeJudge(), judge_runs=0, seed=123)


def test_judge_contexts_match_what_each_arm_saw():
    _report, _target, judge = _run()

    axon_q2 = next(call for call in judge.calls if call["answer"] == "axon answer to q2")
    baseline_q2 = next(call for call in judge.calls if call["answer"] == "baseline answer to q2")

    assert axon_q2["contexts"] == ["axon context for q2"]
    assert "assistant: baseline answer to q1" in baseline_q2["contexts"]
    assert baseline_q2["contexts"][-1] == "user: q2"
