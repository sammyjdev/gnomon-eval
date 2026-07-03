import json
from pathlib import Path

import pytest

from gnomon import cli
from gnomon.config.run_config import SessionRunConfig

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def test_session_run_config_loads_from_toml(tmp_path):
    path = tmp_path / "session.toml"
    path.write_text(
        """
sessions_path = "datasets/sessions/smoke.json"

[eval]
seed = 42
judge_runs = 2
confidence_level = 0.95

[target]
kind = "openai_compat"
base_url = "http://localhost:8765/v1"
model = "axon"
timeout_s = 120.0

[judge]
provider = "ollama"
model = "llama3.1:8b"
base_url = "http://localhost:11434"
timeout_s = 60.0
""",
        encoding="utf-8",
    )

    cfg = SessionRunConfig.from_file(path)

    assert cfg.sessions_path == "datasets/sessions/smoke.json"
    assert cfg.eval.seed == 42
    assert cfg.eval.judge_runs == 2
    assert cfg.eval.confidence_level == 0.95
    assert cfg.target.kind == "openai_compat"
    assert cfg.target.base_url == "http://localhost:8765/v1"
    assert cfg.target.model == "axon"
    assert cfg.target.timeout_s == 120.0
    assert cfg.target.recall_max_tokens == 2000
    assert cfg.judge.provider == "ollama"
    assert cfg.judge.model == "llama3.1:8b"
    assert cfg.judge.base_url == "http://localhost:11434"
    assert cfg.judge.timeout_s == 60.0


def test_unsupported_judge_provider_is_rejected(tmp_path):
    path = tmp_path / "session.toml"
    path.write_text(
        """
sessions_path = "datasets/sessions/smoke.json"

[eval]
seed = 42
judge_runs = 2
confidence_level = 0.95

[target]
kind = "openai_compat"
base_url = "http://localhost:8765/v1"
model = "axon"
timeout_s = 120.0

[judge]
provider = "stub"
model = "llama3.1:8b"
base_url = "http://localhost:11434"
timeout_s = 60.0
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="judge provider"):
        cli.run_session_from_config(SessionRunConfig.from_file(path))


def test_shipped_session_configs_parse():
    full = SessionRunConfig.from_file(CONFIG_DIR / "axon-session.toml")
    smoke = SessionRunConfig.from_file(CONFIG_DIR / "axon-session-smoke.toml")

    assert full.target.recall_max_tokens == 2000
    assert full.eval.judge_runs == 6
    assert smoke.target.recall_max_tokens == 2000
    assert smoke.eval.judge_runs == 2


def test_session_cli_prints_json_on_gate_pass(monkeypatch, capsys):
    _patch_session_run(monkeypatch, quality_gate="pass")

    exit_code = cli.main(["session", "-c", str(CONFIG_DIR / "axon-session-smoke.toml"), "--json"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"quality_gate": "pass", "ok": True}


def test_session_cli_returns_one_on_gate_fail(monkeypatch, capsys):
    _patch_session_run(monkeypatch, quality_gate="fail")

    exit_code = cli.main(["session", "-c", str(CONFIG_DIR / "axon-session-smoke.toml"), "--json"])

    assert exit_code == 1
    assert json.loads(capsys.readouterr().out) == {"quality_gate": "fail", "ok": True}


def test_plain_config_cli_uses_existing_parser_branch(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "run.toml"
    config_path.write_text("unused", encoding="utf-8")
    gate = type("Gate", (), {"passed": True, "failures": []})()

    monkeypatch.setattr(cli.RunConfig, "from_file", lambda path: ("plain", path))
    monkeypatch.setattr(cli, "run_from_config", lambda cfg: ({"report": cfg}, gate))
    monkeypatch.setattr(cli, "to_dict", lambda report: report)

    exit_code = cli.main(["-c", str(config_path), "--json"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "report": ["plain", str(config_path)],
    }


def _patch_session_run(monkeypatch, *, quality_gate: str):
    loaded_sessions = ["session"]
    run_report = object()

    class FakeSessionTarget:
        def __init__(self, **kwargs):
            assert kwargs == {
                "base_url": "http://localhost:8765/v1",
                "model": "axon",
                "timeout_s": 120.0,
                "recall_max_tokens": 2000,
            }

    class FakeSessionOllamaJudge:
        def __init__(self, **kwargs):
            assert kwargs["model"] == "llama3.1:8b"
            assert kwargs["base_url"] == "http://<judge-host>:11434"
            assert kwargs["timeout_s"] == 60.0
            assert kwargs["cache"] is not None

    def fake_run_sessions(sessions, target, judge, **kwargs):
        assert sessions == loaded_sessions
        assert isinstance(target, FakeSessionTarget)
        assert isinstance(judge, FakeSessionOllamaJudge)
        assert kwargs == {"judge_runs": 2, "seed": 42, "confidence_level": 0.95}
        return run_report

    def fake_savings_report(report, **kwargs):
        assert report is run_report
        assert kwargs == {"seed": 42, "confidence_level": 0.95}
        return {"quality_gate": quality_gate, "ok": True}

    monkeypatch.setattr(cli, "load_sessions", lambda path: loaded_sessions)
    monkeypatch.setattr(cli, "SessionTarget", FakeSessionTarget)
    monkeypatch.setattr(cli, "SessionOllamaJudge", FakeSessionOllamaJudge)
    monkeypatch.setattr(cli, "run_sessions", fake_run_sessions)
    monkeypatch.setattr(cli, "savings_report", fake_savings_report)
