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

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gnomon.config.config import EvalConfig


class TargetConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["openai_compat", "mock"]
    base_url: str | None = None
    model: str | None = None
    api_key_env: str | None = None
    timeout_s: float = Field(default=30.0, gt=0.0)
    contexts_field: str = "contexts"
    include_context: bool | None = None


class SessionConfig(TargetConfig):
    recall_max_tokens: int = Field(default=2000, gt=0)
    window_turns: int = Field(default=0, ge=0)


class JudgeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    provider: Literal["ollama", "openai_compat", "stub"]
    model: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    timeout_s: float = Field(default=60.0, gt=0.0)


MIN_PANEL_JUDGES = 2


class PanelJudgeConfig(JudgeConfig):
    """One panel member: everything JudgeConfig has, plus its vendor family
    (ADR-0012 #1 - no two panel members may share a family).
    """

    family: str = Field(min_length=1)
    screening_evidence: str | None = None


class PanelConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    judges: list[PanelJudgeConfig] = Field(min_length=MIN_PANEL_JUDGES)

    @model_validator(mode="after")
    def _distinct_families(self) -> "PanelConfig":
        families = [judge.family for judge in self.judges]
        if len(families) != len(set(families)):
            duplicates = sorted({family for family in families if families.count(family) > 1})
            raise ValueError(
                "panel judges must be from distinct vendor families (ADR-0012); "
                f"duplicate families: {duplicates}"
            )
        return self


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
    panel: PanelConfig | None = None

    @classmethod
    def from_file(cls, path: str | Path) -> "RunConfig":
        path = Path(path)
        data: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
        gate = data.get("gate", {})
        # TOML [gate] is a flat table of metric=threshold; wrap into thresholds.
        if "thresholds" not in gate:
            data["gate"] = {"thresholds": gate}
        return cls(**data)


class SessionRunConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    sessions_path: str = Field(min_length=1)
    eval: EvalConfig
    target: SessionConfig
    judge: JudgeConfig

    @classmethod
    def from_file(cls, path: str | Path) -> "SessionRunConfig":
        path = Path(path)
        data: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
        return cls(**data)
