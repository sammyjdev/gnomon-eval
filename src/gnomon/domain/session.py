"""Session-domain models for multi-turn evaluation runs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Arm = Literal["axon", "baseline"]


class Session(BaseModel):
    """One multi-turn evaluation session."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    turns: list[str] = Field(min_length=2)

    @model_validator(mode="after")
    def _turns_are_not_empty(self) -> "Session":
        if any(turn == "" for turn in self.turns):
            raise ValueError("turns must not contain empty strings")
        return self


class TurnCost(BaseModel):
    """Per-turn cost and latency for one session arm."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    turn: int = Field(ge=0)
    arm: Arm
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0.0)
    # "provider" | "estimate" - validity flag; kept as plain str so an
    # unexpected source value is counted by the report's validity check
    # instead of crashing the run mid-session.
    usage_source: str
