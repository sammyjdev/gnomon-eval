"""External configuration, validated before any model call (RNF-07).

Config lives outside code: changing seed, N of runs or gate thresholds never
requires editing source. Invalid configuration fails closed here, at load
time, rather than mid-run (non-negotiable #6).
"""

from collections.abc import Mapping
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from gnomon.metrics.confidence import MIN_JUDGE_RUNS


def _coerce_bool(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return value


class EvalConfig(BaseModel):
    """Minimal evaluation config for the vertical slice."""

    model_config = ConfigDict(frozen=True)

    reproducible: bool = True
    seed: int | None = None
    deterministic_judge: bool = False
    judge_runs: int
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)

    @field_validator("judge_runs")
    @classmethod
    def _judge_runs_meets_minimum(cls, value: int, info: ValidationInfo) -> int:
        # VAL-04: N below the minimum cannot yield a confidence interval.
        # Roadmap B1: a judge declared deterministic (temperature=0) makes
        # repeated runs identical copies, so the floor relaxes to 1
        # (ADR-002/008 semantics are unaffected for non-deterministic judges).
        minimum = 1 if info.data.get("deterministic_judge") else MIN_JUDGE_RUNS
        if value < minimum:
            raise ValueError(
                f"judge_runs must be at least {minimum} to compute a "
                f"confidence interval, got {value}"
            )
        return value

    @model_validator(mode="after")
    def _seed_required_in_reproducible_mode(self) -> "EvalConfig":
        # VAL-06: never generate an implicit seed in reproducible mode.
        if self.reproducible and self.seed is None:
            raise ValueError(
                "reproducible mode requires an explicit seed; refusing to "
                "invent one that would break reproducibility between runs"
            )
        return self

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "EvalConfig":
        """Build from a string-keyed mapping (env vars / config file)."""
        raw = dict(data)
        if "reproducible" in raw:
            raw["reproducible"] = _coerce_bool(raw["reproducible"])
        return cls(**raw)
