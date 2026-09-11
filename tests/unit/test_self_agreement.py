import json

import pytest

from gnomon.domain.labels import LabeledItem
from gnomon.metrics.alignment import AlignmentError, self_agreement


def _item(case_id, verdict, *, arm="on", answer="ans", contexts=("ctx",), rubric="v2"):
    return LabeledItem(
        case_id=case_id,
        arm=arm,
        answer=answer,
        contexts=list(contexts),
        verdict=verdict,
        critique="reviewed",
        rubric_version=rubric,
    )


def _sa6():
    first = [
        _item(f"c{i}", verdict)
        for i, verdict in enumerate(["pass", "pass", "pass", "fail", "fail", "fail"], 1)
    ]
    second = [
        _item(f"c{i}", verdict)
        for i, verdict in enumerate(["pass", "pass", "fail", "fail", "fail", "pass"], 1)
    ]
    first += [
        _item("c7", "pass"),
        _item("c1", "fail", arm="perturbation:x", answer="first", rubric="construction"),
        _item("c1", "fail", arm="negative:owner"),
    ]
    second += [
        _item("c8", "pass"),
        _item("c1", "fail", arm="perturbation:x", answer="second", rubric="construction"),
        _item("c1", "fail", arm="negative:owner"),
    ]
    return first, second


def _sa10():
    first = [_item(f"c{i}", "pass" if i <= 5 else "fail") for i in range(1, 11)]
    second_verdicts = [
        "pass",
        "pass",
        "pass",
        "pass",
        "fail",
        "fail",
        "fail",
        "fail",
        "pass",
        "pass",
    ]
    return first, [_item(f"c{i}", verdict) for i, verdict in enumerate(second_verdicts, 1)]


def _result(first, second):
    return self_agreement(first, second, confidence_level=0.95, seed=7)


def _all_keys(value):
    if isinstance(value, dict):
        yield from value
        for child in value.values():
            yield from _all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_keys(child)


def test_counts_and_kappa_hand_computed():
    result = _result(*_sa6())
    assert result["counts"] == {
        "first_pass_second_pass": 2,
        "first_pass_second_fail": 1,
        "first_fail_second_pass": 1,
        "first_fail_second_fail": 2,
    }
    assert result["n_pairs"] == 6
    assert result["kappa"]["value"] == pytest.approx(1 / 3, abs=1e-9)
    assert result["kappa"]["ci_low"] is result["kappa"]["ci_high"] is None
    assert (
        result["kappa"]["reason"]
        == "bootstrap needs at least 5 items per owner label class, got pass=3, fail=3"
    )


def test_kappa_interval_with_five_per_class():
    result = _result(*_sa10())
    assert result["kappa"]["value"] == pytest.approx(0.4, abs=1e-9)
    assert result["kappa"]["ci_low"] == pytest.approx(-0.2, abs=1e-9)
    assert result["kappa"]["ci_high"] == pytest.approx(1.0, abs=1e-9)
    assert result["kappa"]["reason"] is None


def test_mismatched_answer_or_contexts_fails_closed():
    first, second = _sa6()
    second[1] = _item("c2", "pass", answer="other")
    with pytest.raises(AlignmentError) as answer:
        _result(first, second)
    assert "c2" in str(answer.value) and "answer" in str(answer.value)
    first, second = _sa6()
    second[1] = _item("c2", "pass", contexts=("ctx", "extra"))
    with pytest.raises(AlignmentError) as contexts:
        _result(first, second)
    assert "c2" in str(contexts.value) and "contexts" in str(contexts.value)


@pytest.mark.parametrize(
    "first, second",
    [
        ([_item("c1", "pass")], [_item("c1", "pass")]),
        ([_item("c1", "pass")], [_item("c2", "pass")]),
    ],
)
def test_fewer_than_two_joined_pairs_fails_closed(first, second):
    with pytest.raises(AlignmentError, match="at least 2"):
        _result(first, second)


def test_confidence_level_rejected():
    with pytest.raises(AlignmentError, match="strictly between 0 and 1"):
        self_agreement(*_sa10(), confidence_level=1.0, seed=7)


def test_no_forbidden_output_key_names_and_same_inputs_are_deterministic():
    first, second = _sa10()
    result = _result(first, second)
    assert not any(
        word in key for key in _all_keys(result) for word in ("accuracy", "agreement", "match")
    )
    assert json.dumps(result, allow_nan=False) == json.dumps(
        _result(first, second), allow_nan=False
    )
