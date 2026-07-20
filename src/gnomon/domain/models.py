"""Typed core of the harness.

The domain knows nothing about infrastructure (RNF-02 / ADR-001). These
models are the contract the rest of the system serialises into.

The central invariant lives here: a judge-based MetricResult cannot be
constructed without mean, confidence interval and N (RNF-03 / ADR-002).
A loose score is a validation error, not an accepted simplification.
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvalCase(BaseModel):
    """One evaluation case: the ground truth for a single question."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    expected_answer: str = Field(min_length=1)
    expected_contexts: list[str] = Field(min_length=1)


class RagResponse(BaseModel):
    """A target's answer to a case, with cost and latency (RF-03 / ADR-004)."""

    model_config = ConfigDict(frozen=True)

    answer: str
    contexts: list[str]
    total_tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0.0)


class MetricScores(BaseModel):
    """Scores from a single judge run, one float per metric, in [0, 1]."""

    model_config = ConfigDict(frozen=True)

    scores: dict[str, float]

    @model_validator(mode="after")
    def _scores_in_unit_range(self) -> "MetricScores":
        for name, value in self.scores.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"score for {name!r} out of [0, 1] range: {value}")
        return self


class MetricResult(BaseModel):
    """Aggregated result for one metric: mean with confidence interval and N.

    Required fields enforce statistical honesty (RNF-03): there is no way to
    represent a judge metric as a single number. `n` is the number of cases the
    interval is taken over (the dataset is the sample; runs denoise within a
    case, see ADR-008), so n >= 2.
    """

    model_config = ConfigDict(frozen=True)

    metric: str = Field(min_length=1)
    mean: float
    ci_low: float
    ci_high: float
    n: int = Field(ge=2)
    confidence_level: float = Field(gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def _interval_is_ordered(self) -> "MetricResult":
        if self.ci_low > self.ci_high:
            raise ValueError(
                f"inverted confidence interval: ci_low={self.ci_low} > ci_high={self.ci_high}"
            )
        return self


class CaseCost(BaseModel):
    """Per-case cost and latency (RF-07 / ADR-004)."""

    model_config = ConfigDict(frozen=True)

    case_id: str = Field(min_length=1)
    total_tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0.0)


class CaseScore(BaseModel):
    """One case's denoised score for one metric (RF-06): the mean of that
    case's judge runs, before the cross-case bootstrap aggregation into
    MetricResult (ADR-008). This is the same value run_eval already computes
    and feeds into aggregate_metric -- exposed here so downstream (glyph
    ADR-G8) can see it without re-deriving it.
    """

    model_config = ConfigDict(frozen=True)

    case_id: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)


class EvalReport(BaseModel):
    """Result of one evaluation run: quality, cost and latency together.

    Quality and cost/latency live in the same object so they cannot drift into
    separate reports (ADR-004). The same source feeds both the machine and
    human serialisations (ARCHITECTURE: Reporting).
    """

    model_config = ConfigDict(frozen=True)

    metrics: list[MetricResult]
    per_case_cost: list[CaseCost]
    case_scores: dict[str, list[CaseScore]] = Field(default_factory=dict)

    def metric(self, name: str) -> MetricResult:
        for result in self.metrics:
            if result.metric == name:
                return result
        raise KeyError(f"no metric named {name!r} in report")

    @property
    def total_tokens(self) -> int:
        return sum(c.total_tokens for c in self.per_case_cost)

    @property
    def mean_latency_ms(self) -> float:
        if not self.per_case_cost:
            return 0.0
        return sum(c.latency_ms for c in self.per_case_cost) / len(self.per_case_cost)
