import contextlib
import json

from gnomon.domain.chat import ChatCase, ChatResult
from gnomon.runner.chat_runner import run_chat_eval


class FakeTarget:
    def __init__(self, results: dict[str, ChatResult]):
        self._results = results

    def run(self, case: ChatCase) -> ChatResult:
        return self._results[case.id]


class _OrderRecordingTarget:
    def __init__(self, results: dict[str, ChatResult], call_log: list[str]):
        self._results = results
        self._call_log = call_log

    def run(self, case: ChatCase) -> ChatResult:
        self._call_log.append(f"generate:{case.id}")
        return self._results[case.id]


class _OrderRecordingJudge:
    def __init__(self, scores: dict[str, dict[str, float]], call_log: list[str]):
        self._scores = scores
        self._call_log = call_log

    def score(self, case: ChatCase, result: ChatResult) -> dict[str, float]:
        self._call_log.append(f"judge:{case.id}")
        return self._scores[case.id]


class FakeJudge:
    def __init__(self, scores: dict[str, dict[str, float]]):
        self._scores = scores

    def score(self, case: ChatCase, result: ChatResult) -> dict[str, float]:
        return self._scores[case.id]


class _FailingOnCaseJudge:
    """Raises for one specific case id, scores normally otherwise -- used to
    reproduce the 2026-07-09 incident (a single unscoreable case, judge chain
    fully exhausted, killed a ~52min/206-case run with zero output)."""

    def __init__(self, scores: dict[str, dict[str, float]], *, fails_on: str):
        self._scores = scores
        self._fails_on = fails_on

    def score(self, case: ChatCase, result: ChatResult) -> dict[str, float]:
        if case.id == self._fails_on:
            raise RuntimeError(f"judge chain exhausted for {case.id}")
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


def test_run_chat_eval_calls_on_case_scored_once_per_case_with_scores():
    # Bug 2: no per-case visibility into judge scores. on_case_scored is an
    # optional hook called right after judge.score(case, result), so a caller
    # (the --pilot CLI path) can observe per-case results without the runner
    # needing to know anything about printing/reporting.
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
            tool_called="answer_question", reply_text="ok a", total_tokens=10, latency_ms=100.0
        ),
        "b": ChatResult(
            tool_called="answer_question", reply_text="ok b", total_tokens=20, latency_ms=200.0
        ),
    }
    scores = {
        "a": {"tool_selection_accuracy": 1.0},
        "b": {"tool_selection_accuracy": 0.0},
    }

    calls = []

    def on_case_scored(case, result, case_scores):
        calls.append((case, result, case_scores))

    run_chat_eval(
        cases,
        FakeTarget(results),
        FakeJudge(scores),
        seed=42,
        on_case_scored=on_case_scored,
    )

    assert len(calls) == 2
    assert calls[0] == (cases[0], results["a"], scores["a"])
    assert calls[1] == (cases[1], results["b"], scores["b"])


def test_run_chat_eval_still_works_without_on_case_scored():
    # Default (None) must remain a no-op so every pre-existing caller is
    # unaffected.
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
            tool_called="answer_question", reply_text="ok a", total_tokens=10, latency_ms=100.0
        ),
        "b": ChatResult(
            tool_called="answer_question", reply_text="ok b", total_tokens=20, latency_ms=200.0
        ),
    }
    scores = {
        "a": {"tool_selection_accuracy": 1.0},
        "b": {"tool_selection_accuracy": 0.0},
    }

    report = run_chat_eval(cases, FakeTarget(results), FakeJudge(scores), seed=42)
    assert report.metric("tool_selection_accuracy").n == 2


def test_run_chat_eval_skips_case_when_judge_scoring_fails_instead_of_crashing(caplog):
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
        ChatCase(
            id="c",
            conversation=[{"role": "user", "content": "Oi 3"}],
            tenant={"name": "T", "tone": "amigavel"},
            expected_tools=["answer_question"],
        ),
    ]
    results = {
        "a": ChatResult(
            tool_called="answer_question", reply_text="ok a", total_tokens=10, latency_ms=100.0
        ),
        "b": ChatResult(
            tool_called="answer_question", reply_text="ok b", total_tokens=20, latency_ms=200.0
        ),
        "c": ChatResult(
            tool_called="answer_question", reply_text="ok c", total_tokens=30, latency_ms=300.0
        ),
    }
    scores = {
        "a": {"tool_selection_accuracy": 1.0},
        "c": {"tool_selection_accuracy": 0.0},
    }

    with caplog.at_level("WARNING"):
        report = run_chat_eval(
            cases, FakeTarget(results), _FailingOnCaseJudge(scores, fails_on="b"), seed=42
        )

    # case "b" is excluded from the metric, but "a" and "c" still aggregate.
    assert report.metric("tool_selection_accuracy").n == 2
    # generation cost for "b" was real (target.run succeeded) and must still
    # be counted -- only the judge step failed.
    assert report.total_tokens == 60
    assert any("b" in r.message for r in caplog.records if r.levelname == "WARNING")


def test_run_chat_eval_does_not_call_on_case_scored_for_a_skipped_case():
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
        ChatCase(
            id="c",
            conversation=[{"role": "user", "content": "Oi 3"}],
            tenant={"name": "T", "tone": "amigavel"},
            expected_tools=["answer_question"],
        ),
    ]
    results = {
        "a": ChatResult(
            tool_called="answer_question", reply_text="ok a", total_tokens=10, latency_ms=100.0
        ),
        "b": ChatResult(
            tool_called="answer_question", reply_text="ok b", total_tokens=20, latency_ms=200.0
        ),
        "c": ChatResult(
            tool_called="answer_question", reply_text="ok c", total_tokens=30, latency_ms=300.0
        ),
    }
    scores = {"a": {"tool_selection_accuracy": 1.0}, "c": {"tool_selection_accuracy": 0.0}}
    calls = []

    run_chat_eval(
        cases,
        FakeTarget(results),
        _FailingOnCaseJudge(scores, fails_on="b"),
        seed=42,
        on_case_scored=lambda case, result, case_scores: calls.append(case.id),
    )

    assert calls == ["a", "c"]


def _two_cases_with_results_and_scores():
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
            tool_called="answer_question", reply_text="ok a", total_tokens=10, latency_ms=100.0
        ),
        "b": ChatResult(
            tool_called="answer_question", reply_text="ok b", total_tokens=20, latency_ms=200.0
        ),
    }
    scores = {
        "a": {"tool_selection_accuracy": 1.0},
        "b": {"tool_selection_accuracy": 0.0},
    }
    return cases, results, scores


def test_run_chat_eval_generates_every_case_before_judging_any():
    # The whole point: a crash/interrupt during judging must not be able to
    # lose generation work that already happened -- which only holds if
    # every target.run() call completes before the first judge.score() call
    # starts, not interleaved case-by-case.
    cases, results, scores = _two_cases_with_results_and_scores()
    call_log: list[str] = []

    run_chat_eval(
        cases,
        _OrderRecordingTarget(results, call_log),
        _OrderRecordingJudge(scores, call_log),
        seed=42,
    )

    assert call_log == [
        "generate:a",
        "generate:b",
        "judge:a",
        "judge:b",
    ]


def test_run_chat_eval_persists_generations_before_judging(tmp_path):
    cases, results, scores = _two_cases_with_results_and_scores()
    path = tmp_path / "generations.jsonl"

    run_chat_eval(
        cases,
        FakeTarget(results),
        FakeJudge(scores),
        seed=42,
        generations_path=str(path),
    )

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    row_a = json.loads(lines[0])
    assert row_a["case_id"] == "a"
    assert row_a["result"]["reply_text"] == "ok a"
    assert row_a["result"]["total_tokens"] == 10
    row_b = json.loads(lines[1])
    assert row_b["case_id"] == "b"
    assert row_b["result"]["reply_text"] == "ok b"


def test_run_chat_eval_persists_generations_even_when_judging_crashes(tmp_path):
    # The actual point of persisting: if judging blows up entirely (not just
    # one case -- e.g. a bug outside the per-case try/except), the
    # already-completed generation work is still recoverable from disk.
    cases, results, _ = _two_cases_with_results_and_scores()
    path = tmp_path / "generations.jsonl"

    class ExplodingJudge:
        def score(self, case, result):
            raise ZeroDivisionError("judge stage is broken, not just one case")

    with contextlib.suppress(Exception):
        # Deliberately broad -- this test only cares that the file survives
        # an unhandled judge-stage exception.
        run_chat_eval(
            cases,
            FakeTarget(results),
            ExplodingJudge(),
            seed=42,
            generations_path=str(path),
        )

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_run_chat_eval_skips_target_for_pregenerated_cases():
    # The whole point: re-judging (new judge config, new criteria, whatever)
    # must not re-spend real Anthropic money re-generating cases we already
    # have a saved result for.
    cases, results, scores = _two_cases_with_results_and_scores()
    call_log: list[str] = []

    report = run_chat_eval(
        cases,
        _OrderRecordingTarget(results, call_log),
        _OrderRecordingJudge(scores, call_log),
        seed=42,
        pregenerated={"a": results["a"], "b": results["b"]},
    )

    assert call_log == ["judge:a", "judge:b"]  # no "generate:*" entries at all
    assert report.metric("tool_selection_accuracy").n == 2


def test_run_chat_eval_generates_only_cases_missing_from_pregenerated():
    # Partial-resume case: a generations file left by a crash mid-run only
    # covers a prefix of `cases` -- the rest must still be freshly generated,
    # not silently dropped.
    cases, results, scores = _two_cases_with_results_and_scores()
    call_log: list[str] = []

    run_chat_eval(
        cases,
        _OrderRecordingTarget(results, call_log),
        _OrderRecordingJudge(scores, call_log),
        seed=42,
        pregenerated={"a": results["a"]},
    )

    assert call_log == ["generate:b", "judge:a", "judge:b"]


def test_load_generations_reads_jsonl_written_by_run_chat_eval(tmp_path):
    from gnomon.runner.chat_runner import load_generations

    cases, results, scores = _two_cases_with_results_and_scores()
    path = tmp_path / "generations.jsonl"

    run_chat_eval(
        cases, FakeTarget(results), FakeJudge(scores), seed=42, generations_path=str(path)
    )

    loaded = load_generations(str(path))

    assert loaded == results


def test_run_chat_eval_round_trips_through_a_saved_generations_file(tmp_path):
    # End-to-end: save once (real generation), reload, re-judge with zero
    # target.run() calls -- the actual feature being asked for.
    from gnomon.runner.chat_runner import load_generations

    cases, results, scores = _two_cases_with_results_and_scores()
    path = tmp_path / "generations.jsonl"

    run_chat_eval(
        cases, FakeTarget(results), FakeJudge(scores), seed=42, generations_path=str(path)
    )

    class ExplodingTarget:
        def run(self, case):
            raise AssertionError(f"target.run() must not be called for {case.id}")

    report = run_chat_eval(
        cases,
        ExplodingTarget(),
        FakeJudge(scores),
        seed=42,
        pregenerated=load_generations(str(path)),
    )

    assert report.metric("tool_selection_accuracy").n == 2
