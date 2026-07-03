import pytest
from pydantic import ValidationError

from gnomon.config.run_config import GateConfig, RunConfig

VALID_TOML = """
dataset_path = "datasets/rpg_master_example/cases.json"

[eval]
reproducible = true
seed = 42
judge_runs = 8

[target]
kind = "openai_compat"
base_url = "http://localhost:8000/v1"
model = "rpg-master"

[judge]
provider = "ollama"
model = "llama3"
base_url = "http://localhost:11434"

[gate]
faithfulness = 0.7
context_precision = 0.6
"""


def test_loads_from_toml(tmp_path):
    path = tmp_path / "run.toml"
    path.write_text(VALID_TOML, encoding="utf-8")
    cfg = RunConfig.from_file(path)
    assert cfg.eval.judge_runs == 8
    assert cfg.target.kind == "openai_compat"
    assert cfg.gate.thresholds["faithfulness"] == 0.7


def test_threshold_above_one_is_rejected():
    with pytest.raises(ValidationError):
        GateConfig(thresholds={"faithfulness": 1.4})


def test_threshold_negative_is_rejected():
    with pytest.raises(ValidationError):
        GateConfig(thresholds={"faithfulness": -0.1})


def test_target_include_context_parses(tmp_path):
    toml = VALID_TOML.replace(
        'model = "rpg-master"', 'model = "rpg-master"\ninclude_context = false'
    )
    path = tmp_path / "cfg.toml"
    path.write_text(toml, encoding="utf-8")
    cfg = RunConfig.from_file(path)
    assert cfg.target.include_context is False


def test_seed_required_propagates_from_eval():
    with pytest.raises(ValidationError):
        RunConfig(
            dataset_path="d.json",
            eval={"reproducible": True, "judge_runs": 8},
            target={"kind": "mock"},
            judge={"provider": "stub"},
            gate={"thresholds": {"faithfulness": 0.7}},
        )
