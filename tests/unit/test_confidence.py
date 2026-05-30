"""Confidence-interval aggregation tests (RF-06 / RNF-03 / ADR-008).

Each case contributes one score per metric (the runner averages the judge's N
runs within a case — runs denoise, they are not independent samples). The
dataset is a sample of questions, so the interval is a seeded percentile
bootstrap over the CASES, bounded to [0, 1] by construction (no clamp) and
reproducible for a given seed. Fewer than two cases cannot bound a population
and is rejected.
"""

import pytest

from gnomon.metrics.confidence import MIN_CASES, aggregate_metric


def test_mean_is_the_arithmetic_mean_of_case_scores():
    result = aggregate_metric("faithfulness", [0.8, 0.9, 1.0], confidence_level=0.95, seed=1)
    assert result.mean == pytest.approx(0.9)


def test_interval_brackets_the_mean():
    result = aggregate_metric("faithfulness", [0.7, 0.8, 0.9, 0.85], confidence_level=0.95, seed=1)
    assert result.ci_low <= result.mean <= result.ci_high


def test_identical_scores_give_zero_width_interval():
    result = aggregate_metric("faithfulness", [0.8, 0.8, 0.8], confidence_level=0.95, seed=1)
    assert result.ci_low == pytest.approx(0.8)
    assert result.ci_high == pytest.approx(0.8)


def test_more_spread_gives_wider_interval():
    tight = aggregate_metric(
        "faithfulness", [0.80, 0.81, 0.79, 0.80], confidence_level=0.95, seed=1
    )
    wide = aggregate_metric("faithfulness", [0.20, 0.95, 0.55, 0.80], confidence_level=0.95, seed=1)
    assert (wide.ci_high - wide.ci_low) > (tight.ci_high - tight.ci_low)


def test_interval_is_bounded_without_a_clamp():
    # Bimodal data: a bootstrap of per-case means stays inside [0, 1] by
    # construction — no clamp, and no t-blowup to amputate.
    result = aggregate_metric("faithfulness", [0.0, 1.0, 1.0, 1.0], confidence_level=0.95, seed=1)
    assert 0.0 <= result.ci_low <= result.mean <= result.ci_high <= 1.0


def test_reproducible_for_a_given_seed():
    a = aggregate_metric("faithfulness", [0.2, 0.9, 0.5, 0.7], confidence_level=0.95, seed=7)
    b = aggregate_metric("faithfulness", [0.2, 0.9, 0.5, 0.7], confidence_level=0.95, seed=7)
    assert (a.ci_low, a.ci_high) == (b.ci_low, b.ci_high)


def test_lower_confidence_level_is_not_wider():
    wide = aggregate_metric("faithfulness", [0.2, 0.9, 0.5, 0.7], confidence_level=0.95, seed=3)
    narrow = aggregate_metric("faithfulness", [0.2, 0.9, 0.5, 0.7], confidence_level=0.80, seed=3)
    assert (narrow.ci_high - narrow.ci_low) <= (wide.ci_high - wide.ci_low)


def test_result_records_n_cases_and_confidence_level():
    result = aggregate_metric("faithfulness", [0.8, 0.9, 1.0], confidence_level=0.95, seed=1)
    assert result.n == 3
    assert result.confidence_level == 0.95
    assert result.metric == "faithfulness"


def test_below_minimum_cases_is_rejected():
    # One case cannot bound a population of questions.
    assert MIN_CASES >= 2
    with pytest.raises(ValueError, match="at least 2 cases"):
        aggregate_metric("faithfulness", [0.9], confidence_level=0.95, seed=1)
