import json

import pytest

from gnomon.domain.labels import LabeledItem
from gnomon.metrics.alignment import AlignmentError, compute_alignment, disagreement_list


def _item(case_id, arm, verdict, *, answer="ans", contexts=("ctx",), rubric="v2", critique=None):
    return LabeledItem(
        case_id=case_id,
        arm=arm,
        answer=answer,
        contexts=list(contexts),
        verdict=verdict,
        critique=critique or f"critique {case_id} {arm}",
        rubric_version=rubric,
    )


def _main():
    items = [
        _item("c1", "on", "pass"),
        _item("c2", "on", "pass"),
        _item("c3", "on", "pass"),
        _item("c4", "on", "pass"),
        _item("c5", "on", "fail"),
        _item("c6", "on", "fail"),
        _item("c7", "on", "fail"),
        _item("c1", "off", "pass"),
        _item("c2", "off", "fail"),
        _item("c3", "off", "fail"),
        _item("c1", "perturbation:number_swap", "fail", rubric="construction"),
        _item("c2", "perturbation:number_swap", "fail", rubric="construction"),
        _item("c3", "perturbation:number_swap", "fail", rubric="construction"),
        _item("c4", "perturbation:number_swap", "fail", rubric="construction"),
        _item("c1", "negative:owner", "fail", answer="neg-1"),
        _item("c1", "negative:owner", "fail", answer="neg-2"),
    ]
    scores = [0.9, 0.8, 0.6, 0.4, 0.7, 0.4, 0.3, 0.55, 0.6, 0.2, 0.2, 0.1, 0.3, 0.4, 0.9, 0.1]
    perfect = [0.9 if item.verdict == "pass" else 0.1 for item in items]
    return items, {"b": perfect, "a": scores}


def _report(items, scores):
    return compute_alignment(items, scores, threshold=0.5, confidence_level=0.95, seed=7)


def _arm(report, judge, arm):
    entry = next(value for value in report["judges"] if value["judge_id"] == judge)
    return next(value for value in entry["arms"] if value["arm"] == arm)


def _assert_stat(stat, value, low, high):
    assert stat["value"] == pytest.approx(value, abs=1e-9)
    assert stat["ci_low"] == pytest.approx(low, abs=1e-9)
    assert stat["ci_high"] == pytest.approx(high, abs=1e-9)
    assert stat["reason"] is None


def _all_keys(value):
    if isinstance(value, dict):
        yield from value
        for child in value.values():
            yield from _all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_keys(child)


def test_real_stratum_pools_only_real_arms_and_sorts_shape():
    report = _report(*_main())
    judge = report["judges"][0]
    assert judge["real"]["n_owner_pass"] == 5
    assert judge["real"]["n_owner_fail"] == 5
    assert [arm["arm"] for arm in judge["arms"]] == [
        "negative:owner",
        "off",
        "on",
        "perturbation:number_swap",
    ]
    assert list(judge) == ["judge_id", "real", "arms"]
    assert [judge["judge_id"] for judge in report["judges"]] == ["a", "b"]


def test_hand_computed_on_and_off_strata():
    report = _report(*_main())
    on, off = _arm(report, "a", "on"), _arm(report, "a", "off")
    assert (on["n_owner_pass"], on["n_owner_fail"]) == (4, 3)
    assert on["auc"]["value"] == pytest.approx(0.7916666667, abs=1e-9)
    _assert_stat(on["tpr"], 0.75, 0.3006418426, 0.9544127392)
    _assert_stat(on["tnr"], 2 / 3, 0.2076596008, 0.9385080553)
    assert on["kappa"]["value"] == pytest.approx(0.4166666667, abs=1e-9)
    assert (off["n_owner_pass"], off["n_owner_fail"]) == (1, 2)
    assert off["auc"]["value"] == pytest.approx(0.5, abs=1e-9)
    _assert_stat(off["tpr"], 1.0, 0.2065493144, 1.0)
    _assert_stat(off["tnr"], 0.5, 0.0945312057, 0.9054687943)
    assert off["kappa"]["value"] == pytest.approx(0.4, abs=1e-9)


def test_real_stratum_hand_computed_with_bootstrap_intervals():
    real = _report(*_main())["judges"][0]["real"]
    assert (real["n_owner_pass"], real["n_owner_fail"]) == (5, 5)
    _assert_stat(real["auc"], 0.76, 0.4, 1.0)
    _assert_stat(real["tpr"], 0.8, 0.3755346298, 0.9637758914)
    _assert_stat(real["tnr"], 0.6, 0.2307242813, 0.8823792258)
    _assert_stat(real["kappa"], 0.4, -0.2, 1.0)


def test_bootstrap_resamples_within_owner_label_class():
    items = [_item(f"p{i}", "inv", "pass") for i in range(5)] + [
        _item(f"f{i}", "inv", "fail") for i in range(7)
    ]
    report = _report(items, {"a": [0.1] * 5 + [0.9] * 7})
    kappa = _arm(report, "a", "inv")["kappa"]
    assert kappa["value"] == pytest.approx(-35 / 37, abs=1e-9)
    assert kappa["ci_low"] == kappa["ci_high"] == kappa["value"]


def test_interval_does_not_depend_on_other_strata_or_judges():
    on = [_item(f"p{i}", "on", "pass") for i in range(5)] + [
        _item(f"f{i}", "on", "fail") for i in range(5)
    ]
    off = [_item(f"x{i}", "off", "pass") for i in range(5)] + [
        _item(f"y{i}", "off", "fail") for i in range(5)
    ]
    on_scores = [0.9, 0.8, 0.6, 0.4, 0.55, 0.7, 0.4, 0.3, 0.6, 0.2]
    first = _report(on, {"a": on_scores})
    second = _report(on + off, {"b": [0.9] * 10 + [0.1] * 10, "a": on_scores + [0.5] * 10})
    assert _arm(first, "a", "on") == _arm(second, "a", "on")


def test_arm_literally_named_real_does_not_collide():
    items = [
        _item("p1", "real", "pass"),
        _item("f1", "real", "fail"),
        _item("p2", "on", "pass"),
        _item("f2", "on", "fail"),
    ]
    report = _report(items, {"a": [0.9, 0.1, 0.8, 0.2]})
    assert (
        _arm(report, "a", "real")["n_owner_pass"],
        _arm(report, "a", "real")["n_owner_fail"],
    ) == (1, 1)
    assert (
        report["judges"][0]["real"]["n_owner_pass"],
        report["judges"][0]["real"]["n_owner_fail"],
    ) == (2, 2)


def test_echoes_parameters_and_rubric_versions():
    report = _report(*_main())
    assert (report["threshold"], report["confidence_level"], report["seed"]) == (0.5, 0.95, 7)
    assert report["rubric_versions"] == ["construction", "v2"]


@pytest.mark.parametrize("threshold", [-0.01, 1.01, float("nan")])
def test_threshold_outside_unit_interval_rejected(threshold):
    with pytest.raises(AlignmentError, match="threshold"):
        compute_alignment([], {}, threshold=threshold, confidence_level=0.95, seed=7)


@pytest.mark.parametrize("threshold", [0.0, 1.0])
def test_threshold_bounds_are_accepted(threshold):
    compute_alignment([], {}, threshold=threshold, confidence_level=0.95, seed=7)


@pytest.mark.parametrize("level", [0.0, 1.0])
def test_confidence_level_outside_open_unit_interval_rejected(level):
    with pytest.raises(AlignmentError, match="strictly between 0 and 1"):
        compute_alignment([], {}, threshold=0.5, confidence_level=level, seed=7)


def test_score_count_mismatch_rejected():
    items, scores = _main()
    with pytest.raises(AlignmentError) as exc:
        _report(items, {"a": scores["a"][:-1]})
    assert "'a'" in str(exc.value) and "15" in str(exc.value) and "16" in str(exc.value)


@pytest.mark.parametrize("score", [1.5, -0.1, float("nan")])
def test_score_out_of_range_or_nan_rejected(score):
    items, scores = _main()
    scores["a"][3] = score
    with pytest.raises(AlignmentError) as exc:
        _report(items, {"a": scores["a"]})
    assert "'a'" in str(exc.value) and "item 3" in str(exc.value) and "c4" in str(exc.value)


def test_missing_label_class_nulls_needing_stats_while_other_strata_compute():
    report = _report(*_main())
    perturbation = _arm(report, "a", "perturbation:number_swap")
    for name in ("auc", "tpr", "kappa"):
        stat = perturbation[name]
        assert (stat["value"], stat["ci_low"], stat["ci_high"]) == (None, None, None)
        assert "pass" in stat["reason"]
    _assert_stat(perturbation["tnr"], 1.0, 0.5101091635, 1.0)
    assert _arm(report, "a", "on")["auc"]["value"] == pytest.approx(0.7916666667, abs=1e-9)


def test_kappa_is_null_not_zero_when_owner_labels_are_single_class():
    stat = _arm(_report(*_main()), "a", "negative:owner")["kappa"]
    assert stat["value"] is None and stat["reason"]


def test_bootstrap_intervals_null_below_five_per_class_while_wilson_reports():
    on = _arm(_report(*_main()), "a", "on")
    reason = "bootstrap needs at least 5 items per owner label class, got pass=4, fail=3"
    assert on["auc"]["reason"] == on["kappa"]["reason"] == reason
    assert on["auc"]["ci_low"] is on["auc"]["ci_high"] is None
    assert on["kappa"]["ci_low"] is on["kappa"]["ci_high"] is None
    assert on["tpr"]["reason"] is on["tnr"]["reason"] is None


def test_stratum_with_no_items_of_a_kind_reports_nulls_not_errors():
    items = [_item(f"c{i}", "perturbation:x", "fail", rubric="construction") for i in range(4)]
    real = _report(items, {"a": [0.1] * 4})["judges"][0]["real"]
    assert (real["n_owner_pass"], real["n_owner_fail"]) == (0, 0)
    assert all(
        stat["value"] is None and stat["reason"]
        for stat in (real["auc"], real["tpr"], real["tnr"], real["kappa"])
    )


def test_no_output_key_names_accuracy_agreement_or_match_and_every_number_is_explained():
    report = _report(*_main())
    assert not any(
        word in key for key in _all_keys(report) for word in ("accuracy", "agreement", "match")
    )
    for judge in report["judges"]:
        for stratum in [judge["real"], *judge["arms"]]:
            for name in ("auc", "tpr", "tnr", "kappa"):
                stat = stratum[name]
                if stat["value"] is None:
                    assert stat["ci_low"] is None and stat["ci_high"] is None and stat["reason"]
                elif stat["ci_low"] is not None:
                    assert stat["ci_low"] <= stat["value"] <= stat["ci_high"]
                else:
                    assert stat["reason"]


def test_disagreement_list_holds_exactly_real_arm_conflicts_sorted():
    items, scores = _main()
    result = disagreement_list(items, scores, threshold=0.5)
    assert result == [
        {
            "judge_id": "a",
            "items": [
                {
                    "case_id": "c2",
                    "arm": "off",
                    "judge_score": 0.6,
                    "judge_verdict": "pass",
                    "owner_verdict": "fail",
                    "owner_critique": "critique c2 off",
                },
                {
                    "case_id": "c4",
                    "arm": "on",
                    "judge_score": 0.4,
                    "judge_verdict": "fail",
                    "owner_verdict": "pass",
                    "owner_critique": "critique c4 on",
                },
                {
                    "case_id": "c5",
                    "arm": "on",
                    "judge_score": 0.7,
                    "judge_verdict": "pass",
                    "owner_verdict": "fail",
                    "owner_critique": "critique c5 on",
                },
            ],
        },
        {"judge_id": "b", "items": []},
    ]


def test_disagreement_list_sorts_case_ids_and_treats_threshold_as_pass():
    items = [_item("z", "on", "fail"), _item("a", "on", "pass")]
    result = disagreement_list(items, {"a": [0.5, 0.2]}, threshold=0.5)
    assert result[0]["items"] == [
        {
            "case_id": "a",
            "arm": "on",
            "judge_score": 0.2,
            "judge_verdict": "fail",
            "owner_verdict": "pass",
            "owner_critique": "critique a on",
        },
        {
            "case_id": "z",
            "arm": "on",
            "judge_score": 0.5,
            "judge_verdict": "pass",
            "owner_verdict": "fail",
            "owner_critique": "critique z on",
        },
    ]


def test_disagreement_list_validates_inputs_before_listing():
    item = [_item("c1", "on", "pass")]
    with pytest.raises(AlignmentError):
        disagreement_list(item, {"a": []}, threshold=0.5)
    with pytest.raises(AlignmentError):
        disagreement_list(item, {"a": [0.5]}, threshold=1.5)


def test_same_inputs_and_seed_give_identical_json():
    items, scores = _main()
    assert json.dumps(_report(items, scores), allow_nan=False) == json.dumps(
        _report(items, scores), allow_nan=False
    )
    assert json.dumps(
        disagreement_list(items, scores, threshold=0.5), allow_nan=False
    ) == json.dumps(disagreement_list(items, scores, threshold=0.5), allow_nan=False)


def test_wilson_lower_bound_is_exactly_zero_when_no_successes():
    items = [_item(f"c{i}", "on", "fail") for i in range(1, 16)]
    report = compute_alignment(
        items, {"a": [0.9] * 15}, threshold=0.5, confidence_level=0.95, seed=7
    )

    tnr = report["judges"][0]["real"]["tnr"]
    assert tnr["value"] == 0.0
    assert tnr["ci_low"] == 0.0
    assert tnr["ci_low"] <= tnr["value"] <= tnr["ci_high"]
    assert tnr["reason"] is None
