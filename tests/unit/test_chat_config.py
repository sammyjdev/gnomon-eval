import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from gnomon.config.chat_config import ChatRunConfig

VALID_TOML = textwrap.dedent(
    """
    dataset_path = "datasets/lina_chateval/cases.json"

    [target]
    script_path = "gateway/scripts/run_chateval_case.py"
    cwd = "/Users/samdev/dev/lina"

    [judge]
    primary_model = "meta/llama-3.3-70b-instruct"
    fallback_model = "phi4:14b"
    fallback_base_url = "http://localhost:11434"

    [gate]
    tool_selection_accuracy = 0.90
    tone_brand = 0.80
    hallucination = 0.90
    """
)


def test_chat_run_config_loads_from_toml(tmp_path):
    path = tmp_path / "chat.toml"
    path.write_text(VALID_TOML, encoding="utf-8")
    cfg = ChatRunConfig.from_file(path)

    assert cfg.dataset_path == "datasets/lina_chateval/cases.json"
    assert cfg.target.script_path == "gateway/scripts/run_chateval_case.py"
    assert cfg.target.cwd == "/Users/samdev/dev/lina"
    assert cfg.target.timeout_s == 60.0
    assert cfg.judge.primary_model == "meta/llama-3.3-70b-instruct"
    assert cfg.judge.fallback_model == "phi4:14b"
    assert cfg.judge.fallback_base_url == "http://localhost:11434"
    assert cfg.gate.thresholds["tool_selection_accuracy"] == 0.90
    assert cfg.gate.thresholds["tone_brand"] == 0.80
    assert cfg.gate.thresholds["hallucination"] == 0.90
    assert cfg.seed == 42


def test_chat_run_config_seed_is_overridable(tmp_path):
    toml = VALID_TOML.replace(
        'dataset_path = "datasets/lina_chateval/cases.json"',
        'dataset_path = "datasets/lina_chateval/cases.json"\nseed = 7',
    )
    path = tmp_path / "chat.toml"
    path.write_text(toml, encoding="utf-8")
    cfg = ChatRunConfig.from_file(path)

    assert cfg.seed == 7


def test_real_chat_toml_matches_spec():
    repo_root = Path(__file__).parent.parent.parent
    cfg = ChatRunConfig.from_file(repo_root / "config" / "chat.toml")

    assert cfg.judge.primary_model == "meta/llama-3.3-70b-instruct"
    assert cfg.judge.fallback_model == "phi4:14b"
    assert cfg.gate.thresholds == {
        "tool_selection_accuracy": 0.90,
        "tone_brand": 0.80,
        "hallucination": 0.90,
    }


def test_chat_gate_threshold_out_of_range_rejected(tmp_path):
    toml = VALID_TOML.replace("hallucination = 0.90", "hallucination = 1.5")
    path = tmp_path / "chat.toml"
    path.write_text(toml, encoding="utf-8")

    with pytest.raises(ValidationError):
        ChatRunConfig.from_file(path)
