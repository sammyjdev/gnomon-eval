import json
import sys
import types

import pytest

from gnomon.config.chat_config import (
    ChatGateConfig,
    ChatJudgeConfig,
    ChatRunConfig,
    ChatTargetConfig,
)
from gnomon.domain.models import EvalReport


def _a_chat_case():
    from gnomon.domain.chat import ChatCase

    return ChatCase(
        id="case-1",
        conversation=[{"role": "user", "content": "Oi"}],
        tenant={"name": "T", "tone": "amigavel"},
        expected_tools=["answer_question"],
    )


def _make_cfg() -> ChatRunConfig:
    return ChatRunConfig(
        dataset_path="datasets/lina_chateval/cases.json",
        target=ChatTargetConfig(
            script_path="gateway/scripts/run_chateval_case.py",
            cwd="/Users/samdev/dev/lina",
        ),
        judge=ChatJudgeConfig(
            primary_model="meta/llama-3.3-70b-instruct",
            fallback_model="phi4:14b",
            fallback_base_url="http://localhost:11434",
        ),
        gate=ChatGateConfig(
            thresholds={"tool_selection_accuracy": 0.90, "tone_brand": 0.80, "hallucination": 0.90}
        ),
    )


class _FakeTarget:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeJudge:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _empty_report() -> EvalReport:
    return EvalReport(metrics=[], per_case_cost=[])


def test_chat_help_exits_zero():
    from gnomon.cli import chat_main

    with pytest.raises(SystemExit) as exc:
        chat_main(["--help"])
    assert exc.value.code == 0


def test_chat_pilot_slices_cases_to_five(monkeypatch):
    import gnomon.cli as cli

    sentinel_cases = [f"case-{i}" for i in range(7)]
    monkeypatch.setattr(cli, "load_chat_cases", lambda path: sentinel_cases)
    monkeypatch.setattr(cli, "ChatTarget", _FakeTarget)
    monkeypatch.setattr(cli, "ChatJudge", _FakeJudge)

    recorded = []
    seeds_used = []

    def fake_run_chat_eval(cases, target, judge, *, seed, generations_path=None, pregenerated=None):
        recorded.append(cases)
        seeds_used.append(seed)
        return _empty_report()

    monkeypatch.setattr(cli, "run_chat_eval", fake_run_chat_eval)
    monkeypatch.setattr(
        cli,
        "evaluate_gate",
        lambda report, thresholds: types.SimpleNamespace(passed=True, failures=[]),
    )

    cfg = _make_cfg()
    cli.run_chat_from_config(cfg, pilot=True)
    assert len(recorded[-1]) == 5

    cli.run_chat_from_config(cfg, pilot=False)
    assert len(recorded[-1]) == 7
    assert seeds_used == [cfg.seed, cfg.seed]


def test_run_chat_from_config_uses_configured_seed_not_a_hardcoded_one(monkeypatch):
    import gnomon.cli as cli

    monkeypatch.setattr(cli, "load_chat_cases", lambda path: ["case-1"])
    monkeypatch.setattr(cli, "ChatTarget", _FakeTarget)
    monkeypatch.setattr(cli, "ChatJudge", _FakeJudge)

    seeds_used = []
    monkeypatch.setattr(
        cli,
        "run_chat_eval",
        lambda cases, target, judge, *, seed, generations_path=None, pregenerated=None: (
            seeds_used.append(seed),
            _empty_report(),
        )[1],
    )
    monkeypatch.setattr(
        cli,
        "evaluate_gate",
        lambda report, thresholds: types.SimpleNamespace(passed=True, failures=[]),
    )

    cfg = ChatRunConfig(
        dataset_path="datasets/lina_chateval/cases.json",
        target=ChatTargetConfig(
            script_path="gateway/scripts/run_chateval_case.py",
            cwd="/Users/samdev/dev/lina",
        ),
        judge=ChatJudgeConfig(
            primary_model="meta/llama-3.3-70b-instruct",
            fallback_model="phi4:14b",
            fallback_base_url="http://localhost:11434",
        ),
        gate=ChatGateConfig(thresholds={"tool_selection_accuracy": 0.90}),
        seed=1234,
    )
    cli.run_chat_from_config(cfg, pilot=False)
    assert seeds_used == [1234]


def test_run_chat_from_config_threads_generations_path_into_run_chat_eval(monkeypatch):
    import gnomon.cli as cli

    monkeypatch.setattr(cli, "load_chat_cases", lambda path: ["case-1"])
    monkeypatch.setattr(cli, "ChatTarget", _FakeTarget)
    monkeypatch.setattr(cli, "ChatJudge", _FakeJudge)

    paths_used = []
    monkeypatch.setattr(
        cli,
        "run_chat_eval",
        lambda cases, target, judge, *, seed, generations_path=None, pregenerated=None: (
            paths_used.append(generations_path),
            _empty_report(),
        )[1],
    )
    monkeypatch.setattr(
        cli,
        "evaluate_gate",
        lambda report, thresholds: types.SimpleNamespace(passed=True, failures=[]),
    )

    cli.run_chat_from_config(_make_cfg(), pilot=False, generations_path="out/gens.jsonl")
    assert paths_used == ["out/gens.jsonl"]


def test_chat_main_parses_save_generations_flag(monkeypatch):
    import gnomon.cli as cli

    monkeypatch.setattr(cli.ChatRunConfig, "from_file", classmethod(lambda cls, path: _make_cfg()))

    captured = {}

    def fake_run_chat_from_config(cfg, *, pilot, generations_path=None, load_generations_path=None):
        captured["generations_path"] = generations_path
        return _empty_report(), types.SimpleNamespace(passed=True, failures=[])

    monkeypatch.setattr(cli, "run_chat_from_config", fake_run_chat_from_config)

    cli.chat_main(["-c", "config/chat.toml", "--save-generations", "out/gens.jsonl"])
    assert captured["generations_path"] == "out/gens.jsonl"


def test_chat_main_parses_load_generations_flag(monkeypatch):
    import gnomon.cli as cli

    monkeypatch.setattr(cli.ChatRunConfig, "from_file", classmethod(lambda cls, path: _make_cfg()))

    captured = {}

    def fake_run_chat_from_config(cfg, *, pilot, generations_path=None, load_generations_path=None):
        captured["load_generations_path"] = load_generations_path
        return _empty_report(), types.SimpleNamespace(passed=True, failures=[])

    monkeypatch.setattr(cli, "run_chat_from_config", fake_run_chat_from_config)

    cli.chat_main(["-c", "config/chat.toml", "--load-generations", "out/gens.jsonl"])
    assert captured["load_generations_path"] == "out/gens.jsonl"


def test_run_chat_from_config_loads_pregenerated_results_and_skips_target(monkeypatch, tmp_path):
    import gnomon.cli as cli
    from gnomon.domain.chat import ChatResult
    from gnomon.runner.chat_runner import run_chat_eval as real_run_chat_eval

    monkeypatch.setattr(cli, "load_chat_cases", lambda path: [_a_chat_case()])

    class ExplodingTarget:
        def __init__(self, **kwargs):
            pass

        def run(self, case):
            raise AssertionError("target.run() must not be called when fully pregenerated")

    monkeypatch.setattr(cli, "ChatTarget", ExplodingTarget)
    monkeypatch.setattr(cli, "ChatJudge", _FakeJudge)
    monkeypatch.setattr(cli, "run_chat_eval", real_run_chat_eval)
    monkeypatch.setattr(
        cli,
        "evaluate_gate",
        lambda report, thresholds: types.SimpleNamespace(passed=True, failures=[]),
    )

    path = tmp_path / "gens.jsonl"
    result = ChatResult(
        tool_called="answer_question", reply_text="ok", total_tokens=5, latency_ms=1.0
    )
    path.write_text(
        json.dumps({"case_id": "case-1", "result": result.model_dump()}) + "\n", encoding="utf-8"
    )

    report, _ = cli.run_chat_from_config(_make_cfg(), pilot=False, load_generations_path=str(path))
    assert report.total_tokens == 5


@pytest.mark.parametrize("gate_passed,expected_exit", [(True, 0), (False, 1)])
def test_chat_main_exit_code_follows_gate(monkeypatch, gate_passed, expected_exit):
    import gnomon.cli as cli

    monkeypatch.setattr(cli.ChatRunConfig, "from_file", classmethod(lambda cls, path: _make_cfg()))
    monkeypatch.setattr(cli, "load_chat_cases", lambda path: ["case-1"])
    monkeypatch.setattr(cli, "ChatTarget", _FakeTarget)
    monkeypatch.setattr(cli, "ChatJudge", _FakeJudge)
    monkeypatch.setattr(
        cli,
        "run_chat_eval",
        lambda cases, target, judge, *, seed, generations_path=None, pregenerated=None: (
            _empty_report()
        ),
    )
    monkeypatch.setattr(
        cli,
        "evaluate_gate",
        lambda report, thresholds: types.SimpleNamespace(
            passed=gate_passed, failures=[] if gate_passed else ["x"]
        ),
    )

    exit_code = cli.chat_main(["-c", "config/chat.toml"])
    assert exit_code == expected_exit


def _make_completion(record, deepinfra_ok):
    def completion(**kw):
        record.append(kw)
        if kw["model"].startswith("deepinfra/") and not deepinfra_ok:
            raise RuntimeError("DeepInfra down")
        content = "DEEPINFRA-ANSWER" if kw["model"].startswith("deepinfra/") else "OLLAMA-ANSWER"
        msg = types.SimpleNamespace(content=content)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    return completion


def test_run_chat_from_config_wires_judge_model_into_tool_correctness_metric(monkeypatch):
    import deepeval.metrics as deepeval_metrics

    import gnomon.cli as cli

    monkeypatch.setattr(cli, "load_chat_cases", lambda path: ["case-1"])
    monkeypatch.setattr(cli, "ChatTarget", _FakeTarget)
    monkeypatch.setattr(
        cli,
        "run_chat_eval",
        lambda cases, target, judge, *, seed, generations_path=None, pregenerated=None: (
            _empty_report()
        ),
    )
    monkeypatch.setattr(
        cli,
        "evaluate_gate",
        lambda report, thresholds: types.SimpleNamespace(passed=True, failures=[]),
    )

    captured = {}

    def fake_chat_judge(*, tool_metric_factory, geval_factory):
        captured["tool_metric_factory"] = tool_metric_factory
        return _FakeJudge(tool_metric_factory=tool_metric_factory, geval_factory=geval_factory)

    monkeypatch.setattr(cli, "ChatJudge", fake_chat_judge)

    recorded_kwargs = {}

    class FakeToolCorrectnessMetric:
        def __init__(self, **kwargs):
            recorded_kwargs.update(kwargs)

    monkeypatch.setattr(deepeval_metrics, "ToolCorrectnessMetric", FakeToolCorrectnessMetric)

    cli.run_chat_from_config(_make_cfg(), pilot=True)
    captured["tool_metric_factory"]()

    assert recorded_kwargs.get("model") is not None


def test_judge_model_uses_deepinfra_when_ok(monkeypatch):
    from gnomon.cli import _build_judge_model

    record = []
    fake_litellm = types.SimpleNamespace(completion=_make_completion(record, deepinfra_ok=True))
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    cfg = ChatJudgeConfig(
        primary_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        fallback_model="phi4:14b",
        fallback_base_url="http://localhost:11434",
    )
    model = _build_judge_model(cfg)
    assert model.generate("hi") == "DEEPINFRA-ANSWER"
    assert len(record) == 1
    assert record[0]["model"] == "deepinfra/meta-llama/Llama-3.3-70B-Instruct-Turbo"


def test_judge_model_falls_back_to_ollama_on_deepinfra_failure(monkeypatch, caplog):
    from gnomon.cli import _build_judge_model

    record = []
    fake_litellm = types.SimpleNamespace(completion=_make_completion(record, deepinfra_ok=False))
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    cfg = ChatJudgeConfig(
        primary_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        fallback_model="phi4:14b",
        fallback_base_url="http://localhost:11434",
    )
    model = _build_judge_model(cfg)
    with caplog.at_level("WARNING"):
        assert model.generate("hi") == "OLLAMA-ANSWER"
    assert len(record) == 2
    assert record[1]["model"] == "ollama/phi4:14b"
    assert record[1]["api_base"] == "http://localhost:11434"
    # Ollama is the last-resort tier and typically not running on this
    # machine (2026-07-09 incident: an unreachable Ollama hung the whole
    # judge chain until the underlying connection error surfaced, killing a
    # ~52min run with zero output because run_chat_eval has no per-case
    # recovery). A short explicit timeout makes "Ollama is down/cold" fail
    # fast instead of stalling the run.
    assert record[1]["timeout"] <= 15
    assert any(
        "meta-llama/Llama-3.3-70B-Instruct-Turbo" in r.message and "phi4:14b" in r.message
        for r in caplog.records
        if r.levelname == "WARNING"
    )


def test_judge_model_propagates_when_both_fail(monkeypatch):
    from gnomon.cli import _build_judge_model

    def always_fail(**kw):
        raise RuntimeError(f"down: {kw['model']}")

    fake_litellm = types.SimpleNamespace(completion=always_fail)
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    cfg = ChatJudgeConfig(
        primary_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        fallback_model="phi4:14b",
        fallback_base_url="http://localhost:11434",
    )
    model = _build_judge_model(cfg)
    with pytest.raises(RuntimeError):
        model.generate("hi")


def _make_completion_with_groq(record, *, deepinfra_ok, groq_ok):
    def completion(**kw):
        record.append(kw)
        if kw["model"].startswith("deepinfra/") and not deepinfra_ok:
            raise RuntimeError("DeepInfra down")
        if kw["model"].startswith("groq/") and not groq_ok:
            raise RuntimeError("Groq down")
        if kw["model"].startswith("deepinfra/"):
            content = "DEEPINFRA-ANSWER"
        elif kw["model"].startswith("groq/"):
            content = "GROQ-ANSWER"
        else:
            content = "OLLAMA-ANSWER"
        msg = types.SimpleNamespace(content=content)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    return completion


def test_judge_model_falls_back_to_groq_when_deepinfra_fails_and_secondary_model_configured(
    monkeypatch, caplog
):
    from gnomon.cli import _build_judge_model

    record = []
    fake_litellm = types.SimpleNamespace(
        completion=_make_completion_with_groq(record, deepinfra_ok=False, groq_ok=True)
    )
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    cfg = ChatJudgeConfig(
        primary_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        secondary_model="llama-3.3-70b-versatile",
        fallback_model="phi4:14b",
        fallback_base_url="http://localhost:11434",
    )
    model = _build_judge_model(cfg)
    with caplog.at_level("WARNING"):
        assert model.generate("hi") == "GROQ-ANSWER"
    assert len(record) == 2
    assert record[1]["model"] == "groq/llama-3.3-70b-versatile"


def test_judge_model_falls_back_to_ollama_when_deepinfra_and_groq_both_fail(monkeypatch):
    from gnomon.cli import _build_judge_model

    record = []
    fake_litellm = types.SimpleNamespace(
        completion=_make_completion_with_groq(record, deepinfra_ok=False, groq_ok=False)
    )
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    cfg = ChatJudgeConfig(
        primary_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        secondary_model="llama-3.3-70b-versatile",
        fallback_model="phi4:14b",
        fallback_base_url="http://localhost:11434",
    )
    model = _build_judge_model(cfg)
    assert model.generate("hi") == "OLLAMA-ANSWER"
    assert len(record) == 3
    assert record[2]["model"] == "ollama/phi4:14b"


def test_judge_model_skips_groq_when_secondary_model_not_configured(monkeypatch):
    # Backward compatibility: existing configs with no secondary_model must
    # keep the DeepInfra -> Ollama 2-tier behavior unchanged.
    from gnomon.cli import _build_judge_model

    record = []
    fake_litellm = types.SimpleNamespace(
        completion=_make_completion_with_groq(record, deepinfra_ok=False, groq_ok=True)
    )
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    cfg = ChatJudgeConfig(
        primary_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        fallback_model="phi4:14b",
        fallback_base_url="http://localhost:11434",
    )
    model = _build_judge_model(cfg)
    assert model.generate("hi") == "OLLAMA-ANSWER"
    assert len(record) == 2
    assert record[1]["model"] == "ollama/phi4:14b"


def _make_completion_with_cerebras(record, *, deepinfra_ok, groq_ok, cerebras_ok):
    def completion(**kw):
        record.append(kw)
        if kw["model"].startswith("deepinfra/") and not deepinfra_ok:
            raise RuntimeError("DeepInfra down")
        if kw["model"].startswith("groq/") and not groq_ok:
            raise RuntimeError("Groq down")
        if kw["model"].startswith("cerebras/") and not cerebras_ok:
            raise RuntimeError("Cerebras down")
        if kw["model"].startswith("deepinfra/"):
            content = "DEEPINFRA-ANSWER"
        elif kw["model"].startswith("groq/"):
            content = "GROQ-ANSWER"
        elif kw["model"].startswith("cerebras/"):
            content = "CEREBRAS-ANSWER"
        else:
            content = "OLLAMA-ANSWER"
        msg = types.SimpleNamespace(content=content)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    return completion


def _cfg_with_cerebras(**overrides) -> ChatJudgeConfig:
    defaults = dict(
        primary_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        secondary_model="llama-3.3-70b-versatile",
        tertiary_model="gpt-oss-120b",
        fallback_model="phi4:14b",
        fallback_base_url="http://localhost:11434",
    )
    defaults.update(overrides)
    return ChatJudgeConfig(**defaults)


def test_judge_model_falls_back_to_cerebras_when_deepinfra_and_groq_fail_and_tertiary_configured(
    monkeypatch, caplog
):
    from gnomon.cli import _build_judge_model

    record = []
    fake_litellm = types.SimpleNamespace(
        completion=_make_completion_with_cerebras(
            record, deepinfra_ok=False, groq_ok=False, cerebras_ok=True
        )
    )
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    model = _build_judge_model(_cfg_with_cerebras())
    with caplog.at_level("WARNING"):
        assert model.generate("hi") == "CEREBRAS-ANSWER"
    assert len(record) == 3
    assert record[2]["model"] == "cerebras/gpt-oss-120b"
    assert any(
        "llama-3.3-70b-versatile" in r.message and "gpt-oss-120b" in r.message
        for r in caplog.records
        if r.levelname == "WARNING"
    )


def test_judge_model_falls_back_to_ollama_when_deepinfra_groq_and_cerebras_all_fail(monkeypatch):
    from gnomon.cli import _build_judge_model

    record = []
    fake_litellm = types.SimpleNamespace(
        completion=_make_completion_with_cerebras(
            record, deepinfra_ok=False, groq_ok=False, cerebras_ok=False
        )
    )
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    model = _build_judge_model(_cfg_with_cerebras())
    assert model.generate("hi") == "OLLAMA-ANSWER"
    assert len(record) == 4
    assert record[3]["model"] == "ollama/phi4:14b"


def test_judge_model_skips_cerebras_when_tertiary_model_not_configured(monkeypatch):
    # Backward compatibility: existing configs with secondary_model but no
    # tertiary_model keep the DeepInfra -> Groq -> Ollama 3-tier behavior
    # unchanged.
    from gnomon.cli import _build_judge_model

    record = []
    fake_litellm = types.SimpleNamespace(
        completion=_make_completion_with_cerebras(
            record, deepinfra_ok=False, groq_ok=False, cerebras_ok=True
        )
    )
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    cfg = _cfg_with_cerebras(tertiary_model=None)
    model = _build_judge_model(cfg)
    assert model.generate("hi") == "OLLAMA-ANSWER"
    assert len(record) == 3
    assert record[2]["model"] == "ollama/phi4:14b"


def test_judge_model_requests_json_object_response_format_on_every_tier(monkeypatch):
    # GEval needs valid {"score", "reason"} JSON back; our custom model has no
    # native structured-output support, so DeepEval falls back to a plain-text
    # extraction path that breaks whenever a free-tier model wraps its answer
    # in prose or markdown fences. Forcing JSON mode on every provider call
    # (not just the primary) is the fix -- a fallback tier crashing on
    # malformed JSON is just as bad as the primary doing it.
    from gnomon.cli import _build_judge_model

    record = []
    fake_litellm = types.SimpleNamespace(
        completion=_make_completion_with_cerebras(
            record, deepinfra_ok=False, groq_ok=False, cerebras_ok=False
        )
    )
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    model = _build_judge_model(_cfg_with_cerebras())
    model.generate("hi")
    assert len(record) == 4
    for call in record:
        assert call.get("response_format") == {"type": "json_object"}, call["model"]


def test_judge_model_requests_a_timeout_on_every_tier(monkeypatch):
    # 2026-07-09 incident, part 1: no tier but Ollama had a client-side
    # timeout, so one stuck connection hung the whole 206-case run
    # indefinitely instead of falling through. Every tier needs one -- paid
    # provider or not, any single network call can stall.
    #
    # Part 2, same day: an initial flat 10s guess (copied from NIM, which
    # really was that fast-or-dead) turned out too short for DeepInfra
    # specifically -- a real GEval-sized prompt (conversation + rubric +
    # JSON-format instructions, not a toy "reply OK") measured 15-23s end to
    # end against DeepInfra's live API, so a 10s cap was timing out nearly
    # every real call before the answer ever arrived. DeepInfra's timeout
    # must have headroom above that; Groq/Cerebras (both known for very fast
    # inference hardware) and Ollama (explicitly a short-leash last resort,
    # see the 2026-07-09 "avoid a slow Ollama blocking the run" discussion)
    # can stay short.
    from gnomon.cli import _build_judge_model

    record = []
    fake_litellm = types.SimpleNamespace(
        completion=_make_completion_with_cerebras(
            record, deepinfra_ok=False, groq_ok=False, cerebras_ok=False
        )
    )
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    model = _build_judge_model(_cfg_with_cerebras())
    model.generate("hi")
    assert len(record) == 4
    for call in record:
        assert isinstance(call.get("timeout"), int | float), call["model"]

    deepinfra_call, groq_call, cerebras_call, ollama_call = record
    # Above the observed 15-23s real-prompt latency, with headroom.
    assert 25 <= deepinfra_call["timeout"] <= 35
    assert groq_call["timeout"] <= 15
    assert cerebras_call["timeout"] <= 15
    assert ollama_call["timeout"] <= 15


def test_pilot_selection_covers_hallucination_and_tone_brand_metrics():
    # Bug 1: a plain cases[:5] file-order slice can never reach the
    # tone-*/hallucination-* cases near the end of the dataset, so those two
    # gate metrics never get computed during --pilot. select_pilot_cases must
    # prioritize coverage of all 3 metrics instead of a blind slice.
    from gnomon.cli import select_pilot_cases
    from gnomon.dataset.chat_loader import load_chat_cases

    cases = load_chat_cases("datasets/lina_chateval/cases.json")
    pilot_cases = select_pilot_cases(cases)

    assert len(pilot_cases) == 5
    assert any(c.criteria and c.criteria_metric == "hallucination" for c in pilot_cases), (
        "pilot selection must include at least one hallucination case"
    )
    assert any(c.criteria and c.criteria_metric == "tone_brand" for c in pilot_cases), (
        "pilot selection must include at least one tone_brand-criteria case"
    )


def test_pilot_selection_does_not_starve_tone_brand_when_hallucination_alone_fills_n():
    # Bug 2: a flat sorted-by-priority-then-slice degrades back to bug 1's
    # symptom once a single priority group (e.g. hallucination) has >= n cases
    # on its own -- the whole pilot becomes that one metric with zero
    # tone_brand coverage. select_pilot_cases must round-robin across metric
    # groups instead of draining the highest-priority group first.
    from gnomon.cli import select_pilot_cases

    def case(id_, metric):
        return types.SimpleNamespace(id=id_, criteria="check something", criteria_metric=metric)

    hallucination_cases = [case(f"hallucination-{i}", "hallucination") for i in range(5)]
    tone_cases = [case(f"tone-{i}", "tone_brand") for i in range(5)]

    pilot_cases = select_pilot_cases(hallucination_cases + tone_cases, n=5)

    assert len(pilot_cases) == 5
    assert any(c.criteria_metric == "hallucination" for c in pilot_cases)
    assert any(c.criteria_metric == "tone_brand" for c in pilot_cases)


def test_pilot_selection_is_a_noop_shape_for_non_chat_case_objects():
    # Guards select_pilot_cases against assuming every element has
    # .criteria/.criteria_metric (the existing test_chat_pilot_slices_cases_to_five
    # test feeds it plain sentinel strings) -- must degrade to file order, not crash.
    from gnomon.cli import select_pilot_cases

    sentinel_cases = [f"case-{i}" for i in range(7)]
    assert select_pilot_cases(sentinel_cases) == sentinel_cases[:5]


def test_pilot_mode_prints_per_case_scores(monkeypatch, capsys):
    import gnomon.cli as cli
    from gnomon.domain.chat import ChatCase, ChatResult

    cases = [
        ChatCase(
            id="case-1",
            conversation=[{"role": "user", "content": "Oi"}],
            tenant={"name": "T", "tone": "amigavel"},
            expected_tools=["answer_question"],
        ),
        ChatCase(
            id="case-2",
            conversation=[{"role": "user", "content": "Oi 2"}],
            tenant={"name": "T", "tone": "amigavel"},
            expected_tools=["answer_question"],
        ),
    ]

    class _StubTarget:
        def run(self, case):
            return ChatResult(
                tool_called="answer_question",
                reply_text="Funcionamos das 9h as 18h.",
                total_tokens=10,
                latency_ms=100.0,
            )

    class _StubJudge:
        def score(self, case, result):
            return {"tool_selection_accuracy": 1.0}

    monkeypatch.setattr(cli, "load_chat_cases", lambda path: cases)
    monkeypatch.setattr(cli, "ChatTarget", lambda **kwargs: _StubTarget())
    monkeypatch.setattr(cli, "ChatJudge", lambda **kwargs: _StubJudge())

    cli.run_chat_from_config(_make_cfg(), pilot=True)

    captured = capsys.readouterr()
    assert "case-1" in captured.out
    assert "case-2" in captured.out
    assert "answer_question" in captured.out
    assert "tool_selection_accuracy" in captured.out


def test_pilot_mode_prints_judge_reasons_when_available(monkeypatch, capsys):
    # A raw score alone doesn't explain a surprising result (e.g. an
    # apparently-correct reply scoring 0.0) -- when the judge exposes
    # last_reasons (ChatJudge does), --pilot must print it per case.
    import gnomon.cli as cli
    from gnomon.domain.chat import ChatCase, ChatResult

    cases = [
        ChatCase(
            id="case-1",
            conversation=[{"role": "user", "content": "Qual o endereco?"}],
            tenant={"name": "T", "tone": "amigavel"},
            expected_tools=["answer_question"],
        ),
        ChatCase(
            id="case-2",
            conversation=[{"role": "user", "content": "Qual o endereco 2?"}],
            tenant={"name": "T", "tone": "amigavel"},
            expected_tools=["answer_question"],
        ),
    ]

    class _StubTarget:
        def run(self, case):
            return ChatResult(
                tool_called="answer_question",
                reply_text="Nao tenho essa informacao.",
                total_tokens=10,
                latency_ms=100.0,
            )

    class _StubJudgeWithReasons:
        def __init__(self):
            self.last_reasons = {}

        def score(self, case, result):
            self.last_reasons = {"tool_selection_accuracy": "tool matched expected"}
            return {"tool_selection_accuracy": 1.0}

    monkeypatch.setattr(cli, "load_chat_cases", lambda path: cases)
    monkeypatch.setattr(cli, "ChatTarget", lambda **kwargs: _StubTarget())
    monkeypatch.setattr(cli, "ChatJudge", lambda **kwargs: _StubJudgeWithReasons())

    cli.run_chat_from_config(_make_cfg(), pilot=True)

    captured = capsys.readouterr()
    assert "tool matched expected" in captured.out
