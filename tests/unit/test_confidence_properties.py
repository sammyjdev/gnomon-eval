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
    random.Random(0).shuffle(shuffled)
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
@settings(deadline=None)
def test_bounds_hold_for_any_valid_input(scores, confidence_level, seed):
    result = aggregate_metric("m", scores, confidence_level=confidence_level, seed=seed)
    assert 0.0 <= result.ci_low <= result.mean <= result.ci_high <= 1.0


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
