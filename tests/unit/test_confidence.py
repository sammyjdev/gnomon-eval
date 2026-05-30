"""Confidence-interval aggregation tests (RF-06 / RNF-03 / ADR-002).

The judge produces N scores per metric. This module turns those into a
MetricResult with a t-based confidence interval. A single number is never
an acceptable output, and N below the minimum needed for an interval is
rejected (VAL-04).
"""

import math

import pytest

from gnomon.metrics.confidence import MIN_JUDGE_RUNS, aggregate_metric


def test_mean_is_the_arithmetic_mean_of_scores():
    result = aggregate_metric("faithfulness", [0.8, 0.9, 1.0], confidence_level=0.95)
    assert result.mean == pytest.approx(0.9)


def test_interval_brackets_the_mean():
    result = aggregate_metric("faithfulness", [0.7, 0.8, 0.9, 0.85], confidence_level=0.95)
    assert result.ci_low <= result.mean <= result.ci_high


def test_identical_scores_give_zero_width_interval():
    result = aggregate_metric("faithfulness", [0.8, 0.8, 0.8], confidence_level=0.95)
    assert result.ci_low == pytest.approx(0.8)
    assert result.ci_high == pytest.approx(0.8)


def test_more_spread_gives_wider_interval():
    tight = aggregate_metric("faithfulness", [0.80, 0.81, 0.79, 0.80], confidence_level=0.95)
    wide = aggregate_metric("faithfulness", [0.20, 0.95, 0.55, 0.80], confidence_level=0.95)
    assert (wide.ci_high - wide.ci_low) > (tight.ci_high - tight.ci_low)


def test_matches_hand_computed_t_interval():
    # n=4, mean=0.85, sample stdev computed below, df=3, t_0.95(3)=3.182.
    scores = [0.80, 0.90, 0.85, 0.85]
    result = aggregate_metric("faithfulness", scores, confidence_level=0.95)
    mean = sum(scores) / len(scores)
    var = sum((s - mean) ** 2 for s in scores) / (len(scores) - 1)
    margin = 3.182 * math.sqrt(var) / math.sqrt(len(scores))
    assert result.mean == pytest.approx(mean)
    assert result.ci_low == pytest.approx(mean - margin, abs=1e-3)
    assert result.ci_high == pytest.approx(mean + margin, abs=1e-3)


def test_interval_is_clamped_to_metric_unit_range():
    # n=2 yields a huge t critical value; the bounded metric must not report
    # a CI outside [0, 1].
    result = aggregate_metric("faithfulness", [0.2, 1.0], confidence_level=0.95)
    assert result.ci_low >= 0.0
    assert result.ci_high <= 1.0


def test_result_records_n_and_confidence_level():
    result = aggregate_metric("faithfulness", [0.8, 0.9, 1.0], confidence_level=0.95)
    assert result.n == 3
    assert result.confidence_level == 0.95
    assert result.metric == "faithfulness"


def test_below_minimum_n_is_rejected_with_clear_message():
    # VAL-04: one run cannot yield a confidence interval.
    assert MIN_JUDGE_RUNS >= 2
    with pytest.raises(ValueError, match="at least 2"):
        aggregate_metric("faithfulness", [0.9], confidence_level=0.95)


def test_unsupported_confidence_level_is_rejected():
    with pytest.raises(ValueError, match="confidence level"):
        aggregate_metric("faithfulness", [0.8, 0.9], confidence_level=0.42)
