"""Domain model tests.

Covers the minimal typed core of the slice: EvalCase, RagResponse,
MetricScores and MetricResult. The statistical-honesty invariant
(non-negotiable #2 / RNF-03) is encoded here: a judge-based MetricResult
cannot exist without mean, confidence interval and N.
"""

import pytest
from pydantic import ValidationError

from gnomon.domain.models import EvalCase, MetricResult, MetricScores, RagResponse


def test_eval_case_holds_question_expected_answer_and_contexts():
    case = EvalCase(
        id="case-1",
        question="Who is the GM?",
        expected_answer="The game master narrates.",
        expected_contexts=["The GM narrates the world."],
    )
    assert case.id == "case-1"
    assert case.question == "Who is the GM?"
    assert case.expected_answer == "The game master narrates."
    assert case.expected_contexts == ["The GM narrates the world."]


def test_eval_case_rejects_empty_expected_contexts():
    # VAL-01: a case without expected contexts is malformed.
    with pytest.raises(ValidationError):
        EvalCase(
            id="case-1",
            question="q",
            expected_answer="a",
            expected_contexts=[],
        )


def test_rag_response_carries_answer_contexts_tokens_and_latency():
    # RF-03 / ADR-004: every target response collects tokens and latency.
    resp = RagResponse(
        answer="The GM narrates.",
        contexts=["The GM narrates the world."],
        total_tokens=120,
        latency_ms=842.0,
    )
    assert resp.answer == "The GM narrates."
    assert resp.contexts == ["The GM narrates the world."]
    assert resp.total_tokens == 120
    assert resp.latency_ms == 842.0


def test_rag_response_rejects_negative_tokens_and_latency():
    with pytest.raises(ValidationError):
        RagResponse(answer="a", contexts=["c"], total_tokens=-1, latency_ms=10.0)
    with pytest.raises(ValidationError):
        RagResponse(answer="a", contexts=["c"], total_tokens=1, latency_ms=-1.0)


def test_metric_scores_holds_one_judge_runs_scores_per_metric():
    scores = MetricScores(scores={"faithfulness": 0.87})
    assert scores.scores["faithfulness"] == 0.87


def test_metric_scores_rejects_value_out_of_unit_range():
    with pytest.raises(ValidationError):
        MetricScores(scores={"faithfulness": 1.5})


def test_metric_result_requires_mean_ci_and_n():
    result = MetricResult(
        metric="faithfulness",
        mean=0.85,
        ci_low=0.80,
        ci_high=0.90,
        n=5,
        confidence_level=0.95,
    )
    assert result.mean == 0.85
    assert result.ci_low == 0.80
    assert result.ci_high == 0.90
    assert result.n == 5
    assert result.confidence_level == 0.95


def test_metric_result_cannot_be_built_without_confidence_interval():
    # RNF-03: a loose score is a defect. The model must not allow it.
    with pytest.raises(ValidationError):
        MetricResult(metric="faithfulness", mean=0.85, n=5)


def test_metric_result_rejects_inverted_interval():
    with pytest.raises(ValidationError):
        MetricResult(
            metric="faithfulness",
            mean=0.85,
            ci_low=0.90,
            ci_high=0.80,
            n=5,
            confidence_level=0.95,
        )
