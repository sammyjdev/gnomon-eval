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


def test_the_real_lina_chateval_dataset_loads_and_has_two_hundred_six_cases():
    # Expanded from the original 28 cases (dec-618/dec-619 in lina-mvp's
    # AXON project, 2026-07-08) to get a statistically decision-useful
    # bootstrap CI: 8 hallucination cases and 14 tone_brand cases were too
    # few for the CI half-width to mean anything at the configured gate
    # thresholds. Batch generated via Codex (gpt-5.5) from a diversity-grid
    # brief, validated for schema/id-uniqueness on the host before merging.
    cases = load_chat_cases("datasets/lina_chateval/cases.json")
    assert len(cases) == 221
    ids = [case.id for case in cases]
    assert len(ids) == len(set(ids))

    prefixes = Counter(case_id.split("-")[0] for case_id in ids)
    assert prefixes == Counter(
        {
            "answer_question": 3,
            "check_availability": 6,
            "book": 19,
            "capture_lead": 5,
            "request_handoff": 2,
            "tone": 92,
            "hallucination": 79,
            "injection": 15,
        }
    )


def test_the_real_lina_chateval_dataset_has_enough_cases_per_criteria_metric():
    # Guards against the criteria_metric-defaults-to-tone_brand mislabeling bug:
    # any case with `criteria` but no explicit `criteria_metric` silently scores
    # as tone_brand, so this only counts the real routed bucket per case.
    cases = load_chat_cases("datasets/lina_chateval/cases.json")
    criteria_cases = [case for case in cases if case.criteria]
    metric_counts = Counter(case.criteria_metric for case in criteria_cases)
    assert metric_counts["hallucination"] >= 5
    assert metric_counts["tone_brand"] >= 6


def test_the_real_lina_chateval_dataset_injection_cases_are_correctly_tagged():
    # Guards against a silent criteria_metric mis-tag or blanked criteria on
    # the prompt_injection cases -- discovered as a surviving mutant during
    # issue #26's Quench discrimination sensor: the id-prefix Counter check
    # alone does not verify the criteria_metric FIELD actually matches, nor
    # that criteria text is non-empty.
    cases = load_chat_cases("datasets/lina_chateval/cases.json")
    injection_cases = [case for case in cases if case.id.startswith("injection-")]
    assert len(injection_cases) == 15
    for case in injection_cases:
        assert case.criteria_metric == "prompt_injection", case.id
        assert case.criteria, case.id
