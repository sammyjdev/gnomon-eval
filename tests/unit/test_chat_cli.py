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


def _make_cfg() -> ChatRunConfig:
    return ChatRunConfig(
        dataset_path="datasets/lina_chateval/cases.json",
        target=ChatTargetConfig(
            script_path="gateway/scripts/run_chateval_case.py",
            cwd="<CHATEVAL_TARGET_CWD>",
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

    def fake_run_chat_eval(cases, target, judge, *, seed):
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
        lambda cases, target, judge, *, seed: (seeds_used.append(seed), _empty_report())[1],
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
            cwd="<CHATEVAL_TARGET_CWD>",
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


@pytest.mark.parametrize("gate_passed,expected_exit", [(True, 0), (False, 1)])
def test_chat_main_exit_code_follows_gate(monkeypatch, gate_passed, expected_exit):
    import gnomon.cli as cli

    monkeypatch.setattr(cli.ChatRunConfig, "from_file", classmethod(lambda cls, path: _make_cfg()))
    monkeypatch.setattr(cli, "load_chat_cases", lambda path: ["case-1"])
    monkeypatch.setattr(cli, "ChatTarget", _FakeTarget)
    monkeypatch.setattr(cli, "ChatJudge", _FakeJudge)
    monkeypatch.setattr(cli, "run_chat_eval", lambda cases, target, judge, *, seed: _empty_report())
    monkeypatch.setattr(
        cli,
        "evaluate_gate",
        lambda report, thresholds: types.SimpleNamespace(
            passed=gate_passed, failures=[] if gate_passed else ["x"]
        ),
    )

    exit_code = cli.chat_main(["-c", "config/chat.toml"])
    assert exit_code == expected_exit


def _make_completion(record, nim_ok):
    def completion(**kw):
        record.append(kw)
        if kw["model"].startswith("nvidia_nim/") and not nim_ok:
            raise RuntimeError("NIM down")
        content = "NIM-ANSWER" if kw["model"].startswith("nvidia_nim/") else "OLLAMA-ANSWER"
        msg = types.SimpleNamespace(content=content)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    return completion


def test_run_chat_from_config_wires_judge_model_into_tool_correctness_metric(monkeypatch):
    import deepeval.metrics as deepeval_metrics

    import gnomon.cli as cli

    monkeypatch.setattr(cli, "load_chat_cases", lambda path: ["case-1"])
    monkeypatch.setattr(cli, "ChatTarget", _FakeTarget)
    monkeypatch.setattr(cli, "run_chat_eval", lambda cases, target, judge, *, seed: _empty_report())
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


def test_judge_model_uses_nim_when_ok(monkeypatch):
    from gnomon.cli import _build_judge_model

    record = []
    fake_litellm = types.SimpleNamespace(completion=_make_completion(record, nim_ok=True))
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    cfg = ChatJudgeConfig(
        primary_model="meta/llama-3.3-70b-instruct",
        fallback_model="phi4:14b",
        fallback_base_url="http://localhost:11434",
    )
    model = _build_judge_model(cfg)
    assert model.generate("hi") == "NIM-ANSWER"
    assert len(record) == 1
    assert record[0]["model"] == "nvidia_nim/meta/llama-3.3-70b-instruct"


def test_judge_model_falls_back_to_ollama_on_nim_failure(monkeypatch, caplog):
    from gnomon.cli import _build_judge_model

    record = []
    fake_litellm = types.SimpleNamespace(completion=_make_completion(record, nim_ok=False))
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    cfg = ChatJudgeConfig(
        primary_model="meta/llama-3.3-70b-instruct",
        fallback_model="phi4:14b",
        fallback_base_url="http://localhost:11434",
    )
    model = _build_judge_model(cfg)
    with caplog.at_level("WARNING"):
        assert model.generate("hi") == "OLLAMA-ANSWER"
    assert len(record) == 2
    assert record[1]["model"] == "ollama/phi4:14b"
    assert record[1]["api_base"] == "http://localhost:11434"
    assert any(
        "meta/llama-3.3-70b-instruct" in r.message and "phi4:14b" in r.message
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
        primary_model="meta/llama-3.3-70b-instruct",
        fallback_model="phi4:14b",
        fallback_base_url="http://localhost:11434",
    )
    model = _build_judge_model(cfg)
    with pytest.raises(RuntimeError):
        model.generate("hi")
