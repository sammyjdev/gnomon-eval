"""Owner-labeled verdict models for judge-alignment metrics."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ArmClass = Literal["real", "perturbation", "negative"]
PERTURBATION_PREFIX = "perturbation:"
NEGATIVE_PREFIX = "negative:"
CONSTRUCTION_RUBRIC = "construction"


class LabeledItem(BaseModel):
    """One owner verdict for an answer in an evaluation arm."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=1)
    arm: str = Field(min_length=1)
    answer: str
    contexts: list[str]
    verdict: Literal["pass", "fail"]
    critique: str = Field(min_length=1)
    rubric_version: str = Field(min_length=1)
    question: str | None = None

    @property
    def arm_class(self) -> ArmClass:
        if self.arm.startswith(PERTURBATION_PREFIX):
            return "perturbation"
        if self.arm.startswith(NEGATIVE_PREFIX):
            return "negative"
        return "real"

    @model_validator(mode="after")
    def _arm_class_constraints(self) -> "LabeledItem":
        if self.arm in {PERTURBATION_PREFIX, NEGATIVE_PREFIX}:
            raise ValueError("prefixed arm must have a non-empty suffix")
        if self.arm_class == "perturbation":
            if self.verdict != "fail":
                raise ValueError("perturbation items must have verdict 'fail'")
            if self.rubric_version != CONSTRUCTION_RUBRIC:
                raise ValueError("perturbation items must use rubric_version 'construction'")
        elif self.arm_class == "negative" and self.verdict != "fail":
            raise ValueError("negative items must have verdict 'fail'")
        return self
