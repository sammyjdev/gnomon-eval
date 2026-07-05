import json
from collections import Counter

import pytest

from gnomon.dataset.chat_loader import load_chat_cases
from gnomon.dataset.loader import DatasetError


def test_load_chat_cases_reads_valid_dataset(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "answer_question-1",
                    "conversation": [{"role": "user", "content": "Qual o horario?"}],
                    "tenant": {"name": "Clinica Aurora", "tone": "amigavel"},
                    "expected_tools": ["answer_question"],
                }
            ]
        )
    )
    cases = load_chat_cases(path)
    assert len(cases) == 1
    assert cases[0].id == "answer_question-1"


def test_load_chat_cases_missing_file_raises_dataset_error(tmp_path):
    with pytest.raises(DatasetError):
        load_chat_cases(tmp_path / "missing.json")


def test_load_chat_cases_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "cases.json"
    entry = {
        "id": "dup",
        "conversation": [{"role": "user", "content": "Oi"}],
        "tenant": {"name": "Clinica Aurora", "tone": "amigavel"},
        "expected_tools": [],
    }
    path.write_text(json.dumps([entry, entry]))
    with pytest.raises(ValueError):
        load_chat_cases(path)


def test_load_chat_cases_empty_list_raises_dataset_error(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([]))
    with pytest.raises(DatasetError):
        load_chat_cases(path)


def test_load_chat_cases_non_list_json_raises_dataset_error(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"not": "a list"}))
    with pytest.raises(DatasetError):
        load_chat_cases(path)


def test_load_chat_cases_malformed_entry_raises_dataset_error(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(["not-a-dict-case"]))
    with pytest.raises(DatasetError):
        load_chat_cases(path)


def test_the_real_lina_chateval_dataset_loads_and_has_seventeen_cases():
    cases = load_chat_cases("datasets/lina_chateval/cases.json")
    assert len(cases) == 17
    ids = [case.id for case in cases]
    assert len(ids) == len(set(ids))

    prefixes = Counter(case_id.split("-")[0] for case_id in ids)
    assert prefixes == Counter(
        {
            "answer_question": 3,
            "check_availability": 3,
            "book": 3,
            "capture_lead": 2,
            "request_handoff": 2,
            "tone": 2,
            "hallucination": 2,
        }
    )
