import json

import pytest

from gnomon.dataset.loader import DatasetError, load_dataset


def _write(tmp_path, payload):
    p = tmp_path / "cases.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


VALID_CASE = {
    "id": "case-1",
    "question": "Who narrates the world?",
    "expected_answer": "The game master narrates the world.",
    "expected_contexts": ["The game master narrates the world to the players."],
}


def test_loads_valid_dataset(tmp_path):
    path = _write(tmp_path, [VALID_CASE])
    cases = load_dataset(path)
    assert len(cases) == 1
    assert cases[0].id == "case-1"


def test_missing_file_fails_closed(tmp_path):
    with pytest.raises(DatasetError) as exc:
        load_dataset(tmp_path / "nope.json")
    assert "nope.json" in str(exc.value)


def test_empty_dataset_fails_closed(tmp_path):
    path = _write(tmp_path, [])
    with pytest.raises(DatasetError):
        load_dataset(path)


def test_case_missing_field_points_at_the_case(tmp_path):
    bad = {**VALID_CASE, "id": "case-bad"}
    del bad["expected_contexts"]
    path = _write(tmp_path, [VALID_CASE, bad])
    with pytest.raises(DatasetError) as exc:
        load_dataset(path)
    assert "case-bad" in str(exc.value)
