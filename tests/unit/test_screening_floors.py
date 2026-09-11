import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from gnomon.judge.screening import screen_candidate, write_screening_evidence


def _scores(value: float) -> str:
    return json.dumps({"faithfulness": value, "context_precision": value})


def test_stub_judge_always_one_fails():
    clean = _scores(1.0)
    result = screen_candidate(
        "candidate",
        {"p1": clean},
        known_fail_probes={"kf1": clean},
        grounded_threshold=0.5,
        pass_floor=0.5,
    )
    assert result.passed is False


def test_stub_judge_always_zero_fails():
    low = _scores(0.0)
    result = screen_candidate(
        "candidate",
        {"p1": low},
        known_fail_probes={"kf1": low},
        grounded_threshold=0.5,
        pass_floor=0.5,
    )
    assert result.passed is False


def test_candidate_with_no_known_fail_probes_fails_closed(tmp_path: Path):
    result = screen_candidate(
        "candidate",
        {"p1": _scores(0.8)},
        known_fail_probes={},
        grounded_threshold=0.5,
        pass_floor=0.5,
    )
    assert result.passed is False
    assert result.tnr is None

    path = tmp_path / "ev1.json"
    write_screening_evidence(result, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["known_fail_count"] == 0
    assert data["tnr"] is None

    result_none = screen_candidate(
        "candidate",
        {"p1": _scores(0.8)},
        known_fail_probes=None,
        grounded_threshold=0.5,
        pass_floor=0.5,
    )
    assert result_none.passed is False
    assert result_none.tnr is None


def test_missing_grounded_threshold_fails_closed_with_null_evidence(tmp_path: Path):
    result = screen_candidate(
        "candidate",
        {"p1": _scores(0.8)},
        known_fail_probes={"kf1": _scores(0.1)},
        pass_floor=0.5,
    )
    assert result.passed is False
    assert result.grounded_threshold is None

    path = tmp_path / "ev_missing_thresh.json"
    write_screening_evidence(result, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["grounded_threshold"] is None


def test_missing_pass_floor_fails_closed_with_null_evidence(tmp_path: Path):
    result = screen_candidate(
        "candidate",
        {"p1": _scores(0.8)},
        known_fail_probes={"kf1": _scores(0.1)},
        grounded_threshold=0.5,
    )
    assert result.passed is False
    assert result.pass_floor is None

    path = tmp_path / "ev_missing_floor.json"
    write_screening_evidence(result, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["pass_floor"] is None


def test_out_of_range_thresholds_raise():
    for bad in [-0.01, 1.01, float("nan"), float("inf"), -float("inf")]:
        with pytest.raises((ValueError, ValidationError)):
            screen_candidate(
                "candidate",
                {"p1": _scores(0.8)},
                known_fail_probes={"kf1": _scores(0.1)},
                grounded_threshold=bad,
                pass_floor=0.5,
            )
        with pytest.raises((ValueError, ValidationError)):
            screen_candidate(
                "candidate",
                {"p1": _scores(0.8)},
                known_fail_probes={"kf1": _scores(0.1)},
                grounded_threshold=0.5,
                pass_floor=bad,
            )


def test_boolean_thresholds_raise():
    for bad in [True, False]:
        with pytest.raises((ValueError, ValidationError)):
            screen_candidate(
                "candidate",
                {"p1": _scores(0.8)},
                known_fail_probes={"kf1": _scores(0.1)},
                grounded_threshold=bad,
                pass_floor=0.5,
            )
        with pytest.raises((ValueError, ValidationError)):
            screen_candidate(
                "candidate",
                {"p1": _scores(0.8)},
                known_fail_probes={"kf1": _scores(0.1)},
                grounded_threshold=0.5,
                pass_floor=bad,
            )


def test_threshold_bounds_are_inclusive():
    # 0.0 and 1.0 must not raise
    screen_candidate(
        "candidate",
        {"p1": _scores(0.8)},
        known_fail_probes={"kf1": _scores(0.1)},
        grounded_threshold=0.0,
        pass_floor=0.0,
    )
    screen_candidate(
        "candidate",
        {"p1": _scores(0.8)},
        known_fail_probes={"kf1": _scores(0.1)},
        grounded_threshold=1.0,
        pass_floor=1.0,
    )


def test_known_fail_probe_exactly_at_grounded_threshold_fails_candidate():
    result = screen_candidate(
        "candidate",
        {"p1": _scores(0.8)},
        known_fail_probes={"kf1": _scores(0.5)},
        grounded_threshold=0.5,
        pass_floor=0.5,
    )
    assert result.passed is False
    assert result.known_fail_grounded_count == 1


def test_pass_probe_exactly_at_pass_floor_counts():
    result = screen_candidate(
        "candidate",
        {"p1": _scores(0.5)},
        known_fail_probes={"kf1": _scores(0.1)},
        grounded_threshold=0.5,
        pass_floor=0.5,
    )
    assert result.passed is True
    assert result.pass_floor_count == 1


def test_tnr_is_fraction_of_ungrounded_known_fail_probes():
    result = screen_candidate(
        "candidate",
        {"p1": _scores(0.8)},
        known_fail_probes={"kf1": _scores(0.6), "kf2": _scores(0.1)},
        grounded_threshold=0.5,
        pass_floor=0.5,
    )
    assert result.tnr == 0.5
    assert len(result.known_fail_probes) == 2
    assert result.known_fail_grounded_count == 1


def test_tnr_is_null_not_zero_when_denominator_empty(tmp_path: Path):
    result = screen_candidate(
        "candidate",
        {"p1": _scores(0.8)},
        known_fail_probes={},
        grounded_threshold=0.5,
        pass_floor=0.5,
    )
    assert result.tnr is None

    path = tmp_path / "ev_empty_kf.json"
    write_screening_evidence(result, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["tnr"] is None


def test_schema_failing_known_fail_probe_fails_candidate_and_counts_ungrounded():
    bad_kf = json.dumps({"faithfulness": 0.9, "context_precision": 0.9, "hallucinated": "bad"})
    result = screen_candidate(
        "candidate",
        {"p1": _scores(0.8)},
        known_fail_probes={"kf1": bad_kf},
        grounded_threshold=0.5,
        pass_floor=0.5,
    )
    assert result.passed is False
    assert result.known_fail_grounded_count == 0
    assert result.tnr == 1.0


def test_schema_failing_pass_probe_not_counted_toward_pass_floor(tmp_path: Path):
    bad_pass = json.dumps({"faithfulness": 0.9, "context_precision": 0.9, "hallucinated": "bad"})
    result = screen_candidate(
        "candidate",
        {"p1": bad_pass},
        known_fail_probes={"kf1": _scores(0.1)},
        grounded_threshold=0.5,
        pass_floor=0.5,
    )
    assert result.passed is False
    assert result.pass_floor_count == 0

    path = tmp_path / "ev_bad_pass.json"
    write_screening_evidence(result, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["pass_floor_count"] == 0


def test_evidence_round_trips_all_floor_fields(tmp_path: Path):
    result = screen_candidate(
        "candidate",
        {"p1": _scores(0.8)},
        known_fail_probes={"kf1": _scores(0.1)},
        grounded_threshold=0.5,
        pass_floor=0.5,
    )
    path = tmp_path / "screening.json"
    written_path = write_screening_evidence(result, path)

    assert written_path == path
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))

    assert set(data.keys()) == {
        "candidate",
        "passed",
        "grounded_threshold",
        "pass_floor",
        "known_fail_count",
        "tnr",
        "pass_floor_count",
        "probes",
    }
    assert isinstance(data["candidate"], str)
    assert isinstance(data["passed"], bool)
    assert isinstance(data["grounded_threshold"], float)
    assert isinstance(data["pass_floor"], float)
    assert isinstance(data["known_fail_count"], int)
    assert isinstance(data["tnr"], float)
    assert isinstance(data["pass_floor_count"], int)
    assert isinstance(data["probes"], list)
