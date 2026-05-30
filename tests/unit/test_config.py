"""Config validation tests (fail-closed, non-negotiable #6).

Config is validated before any model call (ARCHITECTURE: "Configuração
inválida para a execução antes de qualquer chamada de modelo"). The slice
covers two validations:

  VAL-06 — reproducible mode without a declared seed fails.
  VAL-04 — judge_runs below the minimum for a confidence interval fails.
"""

import pytest
from pydantic import ValidationError

from gnomon.config.config import EvalConfig


def test_valid_reproducible_config_is_accepted():
    cfg = EvalConfig(reproducible=True, seed=42, judge_runs=5)
    assert cfg.seed == 42
    assert cfg.judge_runs == 5
    assert cfg.confidence_level == 0.95


def test_reproducible_mode_without_seed_fails():
    # VAL-06: never invent an implicit seed.
    with pytest.raises(ValidationError, match="seed"):
        EvalConfig(reproducible=True, seed=None, judge_runs=5)


def test_non_reproducible_mode_allows_missing_seed():
    cfg = EvalConfig(reproducible=False, seed=None, judge_runs=5)
    assert cfg.seed is None


def test_judge_runs_below_minimum_fails_with_minimum_in_message():
    # VAL-04: reject before any model call.
    with pytest.raises(ValidationError, match="at least 2"):
        EvalConfig(reproducible=True, seed=42, judge_runs=1)


def test_loads_from_mapping():
    cfg = EvalConfig.from_mapping({"reproducible": "true", "seed": "7", "judge_runs": "5"})
    assert cfg.reproducible is True
    assert cfg.seed == 7
    assert cfg.judge_runs == 5
