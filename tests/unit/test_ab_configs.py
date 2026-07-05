"""The shipped A/B configs must parse and differ only in the recall flag."""

from pathlib import Path

from gnomon.config.run_config import RunConfig

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def test_recall_on_config_parses_with_flag_true():
    cfg = RunConfig.from_file(_CONFIG_DIR / "axon-recall-on.toml")
    assert cfg.target.include_context is True
    assert cfg.target.kind == "openai_compat"


def test_recall_off_config_parses_with_flag_false_and_no_gate():
    cfg = RunConfig.from_file(_CONFIG_DIR / "axon-recall-off.toml")
    assert cfg.target.include_context is False
    # Baseline run is never gated: context metrics are meaningless without recall.
    assert cfg.gate.thresholds == {}


def test_ab_configs_share_dataset_and_judge():
    on = RunConfig.from_file(_CONFIG_DIR / "axon-recall-on.toml")
    off = RunConfig.from_file(_CONFIG_DIR / "axon-recall-off.toml")
    assert on.dataset_path == off.dataset_path
    assert on.eval == off.eval
    assert on.judge == off.judge
