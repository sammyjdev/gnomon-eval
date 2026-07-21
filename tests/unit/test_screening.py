import json

from gnomon.judge.screening import screen_candidate, screen_probe, write_screening_evidence
from gnomon.metrics.names import V1_METRICS


def _valid_scores() -> dict[str, float]:
    return {metric: 0.8 for metric in V1_METRICS}


def test_clean_probe_passes_capacity_bar():
    verdict = screen_probe("clean", json.dumps(_valid_scores()))

    assert verdict.passed is True
    assert verdict.valid_json is True
    assert verdict.schema_compliant is True
    assert verdict.hallucinated_keys == []
    assert verdict.reason is None


def test_not_valid_json_fails_capacity_bar():
    verdict = screen_probe("invalid-json", "not json at all")

    assert verdict.passed is False
    assert verdict.valid_json is False
    assert "not valid JSON" in verdict.reason


def test_non_object_json_fails_capacity_bar():
    verdict = screen_probe("list", "[1, 2, 3]")

    assert verdict.passed is False
    assert verdict.valid_json is True
    assert verdict.schema_compliant is False


def test_missing_required_key_fails_capacity_bar():
    verdict = screen_probe("missing", json.dumps({"context_precision": 0.8}))

    assert verdict.passed is False
    assert verdict.schema_compliant is False
    assert "missing" in verdict.reason


def test_out_of_range_value_fails_capacity_bar():
    scores = _valid_scores()
    scores[V1_METRICS[0]] = 1.5

    verdict = screen_probe("out-of-range", json.dumps(scores))

    assert verdict.passed is False
    assert "not a float" in verdict.reason


def test_boolean_value_fails_capacity_bar():
    scores = _valid_scores()
    scores[V1_METRICS[0]] = True

    verdict = screen_probe("boolean", json.dumps(scores))

    assert verdict.passed is False


def test_phi3_precedent_shows_missing_and_hallucinated_keys():
    verdict = screen_probe("phi3-precedent", '{"faithlessness": 0.9, "context_precision": 0.8}')

    assert verdict.passed is False
    assert "faithfulness" in verdict.reason
    assert "faithlessness" in verdict.hallucinated_keys


def test_extra_key_fails_even_when_schema_is_compliant():
    scores = _valid_scores()
    scores["toxicity"] = 0.1

    verdict = screen_probe("extra", json.dumps(scores))

    assert verdict.passed is False
    assert verdict.schema_compliant is True
    assert verdict.hallucinated_keys == ["toxicity"]
    assert "hallucinated" in verdict.reason


def test_candidate_fails_closed_when_one_probe_has_hallucinated_key():
    clean = json.dumps(_valid_scores())
    invalid = _valid_scores()
    invalid["toxicity"] = 0.1
    result = screen_candidate(
        "candidate",
        {**{f"clean-{index}": clean for index in range(4)}, "invalid": json.dumps(invalid)},
    )

    assert result.passed is False


def test_candidate_passes_when_all_probes_are_clean():
    clean = json.dumps(_valid_scores())

    result = screen_candidate("candidate", {"one": clean, "two": clean})

    assert result.passed is True


def test_candidate_with_no_probes_cannot_pass():
    result = screen_candidate("candidate", {})

    assert result.passed is False


def test_write_screening_evidence_round_trips_all_probe_fields(tmp_path):
    scores = _valid_scores()
    scores["toxicity"] = 0.1
    result = screen_candidate(
        "candidate", {"clean": json.dumps(_valid_scores()), "extra": json.dumps(scores)}
    )
    path = tmp_path / "new" / "screening.json"

    written_path = write_screening_evidence(result, path)

    assert written_path == path
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "candidate": result.candidate,
        "passed": result.passed,
        "probes": [probe.model_dump() for probe in result.probes],
    }
