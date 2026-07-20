import random

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from gnomon.metrics.confidence import MIN_CASES, aggregate_metric


@given(
    scores=st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        min_size=2,
        max_size=30,
    )
)
@settings(deadline=None)
def test_mean_is_permutation_invariant(scores):
    shuffled = scores.copy()
    random.Random(0).shuffle(shuffled)  # noqa: S311 - deterministic test shuffle, not cryptographic.
    a = aggregate_metric("m", scores, confidence_level=0.95, seed=1)
    b = aggregate_metric("m", shuffled, confidence_level=0.95, seed=1)
    assert a.mean == pytest.approx(b.mean)
    # ci_low and ci_high are order-sensitive for a fixed bootstrap seed.


@given(
    scores=st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        min_size=2,
        max_size=50,
    ),
    confidence_level=st.floats(min_value=0.01, max_value=0.99),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
)
@example(scores=[0.0, 0.0], confidence_level=0.01, seed=0)
@example(scores=[1.0, 1.0], confidence_level=0.99, seed=2**31 - 1)
@example(scores=[0.0, 1.0], confidence_level=0.95, seed=1)
# Regression pin: a low confidence_level with asymmetric data is where the
# percentile bootstrap can place ci_low above the mean before the clamp -
# hypothesis's random search only hits this region a fraction of the time
# (verified: ~4/5 runs with a fresh example database), so pin it explicitly
# rather than rely on the search finding it.
@example(scores=[0.145, 0.295, 0.687, 0.639, 0.953, 0.537], confidence_level=0.023, seed=10)
@settings(deadline=None)
def test_bounds_hold_for_any_valid_input(scores, confidence_level, seed):
    result = aggregate_metric("m", scores, confidence_level=confidence_level, seed=seed)
    assert 0.0 <= result.ci_low <= result.mean <= result.ci_high <= 1.0


def test_ci_width_is_positive_for_dispersed_low_confidence_case():
    """Regression pin against a min/max-swap style mutation collapsing the
    interval: with real dispersion, ci_high must stay strictly above
    ci_low. Not hypothesis-quantified - asserting this for arbitrary
    n/confidence_level would itself be flaky (verified empirically: ~6% of
    random dispersed n=3..5 cases legitimately bootstrap to a zero-width
    percentile window even with correct code), so this pins one
    well-verified deterministic case instead of a blanket property.
    """
    result = aggregate_metric(
        "m",
        [0.145, 0.295, 0.687, 0.639, 0.953, 0.537],
        confidence_level=0.023,
        seed=10,
    )
    assert result.ci_high - result.ci_low > 0


@given(
    value=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    case_count=st.integers(min_value=MIN_CASES, max_value=50),
    confidence_level=st.floats(min_value=0.01, max_value=0.99),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
)
@settings(deadline=None)
def test_identical_scores_always_give_zero_width_interval(
    value, case_count, confidence_level, seed
):
    result = aggregate_metric(
        "m",
        [value] * case_count,
        confidence_level=confidence_level,
        seed=seed,
    )
    assert result.ci_low == pytest.approx(value)
    assert result.mean == pytest.approx(value)
    assert result.ci_high == pytest.approx(value)
