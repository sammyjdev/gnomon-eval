"""Configuration for `gnomon chat`, loaded from TOML (mirrors run_config.py)."""

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatTargetConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    script_path: str = Field(min_length=1)
    cwd: str = Field(min_length=1)
    timeout_s: float = Field(default=60.0, gt=0.0)


class ChatJudgeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    primary_model: str = Field(min_length=1)
    fallback_model: str = Field(min_length=1)
    fallback_base_url: str = Field(min_length=1)


class ChatGateConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    thresholds: dict[str, float]

    @field_validator("thresholds")
    @classmethod
    def _thresholds_in_unit_range(cls, value: dict[str, float]) -> dict[str, float]:
        for metric, threshold in value.items():
            if not 0.0 <= threshold <= 1.0:
                raise ValueError(f"gate threshold for {metric!r} out of [0, 1] range: {threshold}")
        return value


class ChatRunConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    dataset_path: str = Field(min_length=1)
    target: ChatTargetConfig
    judge: ChatJudgeConfig
    gate: ChatGateConfig
    seed: int = 42

    @classmethod
    def from_file(cls, path: str | Path) -> "ChatRunConfig":
        path = Path(path)
        data: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
        gate = data.get("gate", {})
        if "thresholds" not in gate:
            data["gate"] = {"thresholds": gate}
        return cls(**data)
