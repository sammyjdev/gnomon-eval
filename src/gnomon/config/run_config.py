"""Production run configuration, loaded from TOML and validated up front.

Composes the Phase-1 EvalConfig with the target, judge and gate config that
the CLI needs, without touching EvalConfig itself (RNF-07: config is external;
the vertical-slice contract stays intact). Invalid configuration — including
a gate threshold outside the metric's [0, 1] range (VAL-05) — fails closed
here, before any model call.
"""

import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from gnomon.config.config import EvalConfig


class TargetConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["openai_compat", "mock"]
    base_url: str | None = None
    model: str | None = None
    api_key_env: str | None = None
    timeout_s: float = Field(default=30.0, gt=0.0)


class JudgeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    provider: Literal["ollama", "stub"]
    model: str | None = None
    base_url: str | None = None
    timeout_s: float = Field(default=60.0, gt=0.0)


class GateConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    thresholds: dict[str, float]

    @field_validator("thresholds")
    @classmethod
    def _thresholds_in_unit_range(cls, value: dict[str, float]) -> dict[str, float]:
        for metric, threshold in value.items():
            if not 0.0 <= threshold <= 1.0:
                raise ValueError(
                    f"gate threshold for {metric!r} out of [0, 1] range: {threshold} (VAL-05)"
                )
        return value


class RunConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    dataset_path: str = Field(min_length=1)
    eval: EvalConfig
    target: TargetConfig
    judge: JudgeConfig
    gate: GateConfig

    @classmethod
    def from_file(cls, path: str | Path) -> "RunConfig":
        path = Path(path)
        data: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
        gate = data.get("gate", {})
        # TOML [gate] is a flat table of metric=threshold; wrap into thresholds.
        if "thresholds" not in gate:
            data["gate"] = {"thresholds": gate}
        return cls(**data)
