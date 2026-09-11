import json

import pytest

from gnomon.dataset.labels import LabelError, load_labels
from gnomon.dataset.loader import DatasetError


def _item(case_id="c1", arm="on", *, answer="answer", **overrides):
    item = {
        "case_id": case_id,
        "arm": arm,
        "answer": answer,
        "contexts": ["context"],
        "verdict": "pass",
        "critique": "reviewed",
        "rubric_version": "v2",
    }
    item.update(overrides)
    return item


def _write(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_loads_items_in_path_then_file_order(tmp_path):
    first = _write(tmp_path, "first.json", [_item("c1"), _item("c2")])
    second = _write(tmp_path, "second.json", [_item("c3", question="display question")])

    items = load_labels(first, second)

    assert [(item.case_id, item.arm) for item in items] == [
        ("c1", "on"),
        ("c2", "on"),
        ("c3", "on"),
    ]
    assert items[0].question is None
    assert items[2].question == "display question"


def test_empty_contexts_is_accepted(tmp_path):
    path = _write(tmp_path, "labels.json", [_item(contexts=[])])

    assert load_labels(path)[0].contexts == []


def test_label_error_is_a_dataset_error():
    assert issubclass(LabelError, DatasetError)


def test_no_paths_is_rejected():
    with pytest.raises(LabelError):
        load_labels()


def test_missing_file_fails_closed(tmp_path):
    path = tmp_path / "nope.json"
    with pytest.raises(LabelError) as exc:
        load_labels(path)
    assert str(path) in str(exc.value)


def test_invalid_json_fails_closed(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(LabelError) as exc:
        load_labels(path)
    assert str(path) in str(exc.value)


@pytest.mark.parametrize("payload", [[], {"not": "a list"}])
def test_empty_or_non_array_document_fails_closed(tmp_path, payload):
    path = _write(tmp_path, "bad.json", payload)
    with pytest.raises(LabelError) as exc:
        load_labels(path)
    assert str(path) in str(exc.value)


def test_non_object_item_names_the_item(tmp_path):
    path = _write(tmp_path, "labels.json", [_item(), "x"])
    with pytest.raises(LabelError) as exc:
        load_labels(path)
    assert str(path) in str(exc.value)
    assert "item 1" in str(exc.value)


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"critique": None}, "critique"),
        ({"score": 0.9}, "score"),
        ({"verdict": None}, "verdict"),
        ({"verdict": "maybe"}, "verdict"),
        ({"rubric_version": ""}, "rubric_version"),
        ({"critique": ""}, "critique"),
    ],
)
def test_invalid_item_field_names_file_item_and_field(tmp_path, changes, fragment):
    item = _item()
    if changes.get("critique") is None and "critique" in changes:
        del item["critique"]
    else:
        item.update(changes)
    path = _write(tmp_path, "labels.json", [item])
    with pytest.raises(LabelError) as exc:
        load_labels(path)
    assert str(path) in str(exc.value)
    assert "item 0" in str(exc.value)
    assert fragment in str(exc.value)


def test_duplicate_real_item_within_a_file_fails_closed(tmp_path):
    path = _write(tmp_path, "labels.json", [_item(), _item(answer="another")])
    with pytest.raises(LabelError) as exc:
        load_labels(path)
    assert str(path) in str(exc.value)
    assert "item 1" in str(exc.value)


def test_duplicate_across_files_names_the_later_file(tmp_path):
    first = _write(tmp_path, "first.json", [_item()])
    second = _write(tmp_path, "second.json", [_item()])
    with pytest.raises(LabelError) as exc:
        load_labels(first, second)
    assert str(second) in str(exc.value)
    assert "item 0" in str(exc.value)


def test_negative_arm_accepts_several_items_per_case_with_different_answers(tmp_path):
    path = _write(
        tmp_path,
        "labels.json",
        [
            _item(arm="negative:owner", answer="n1", verdict="fail"),
            _item(arm="negative:owner", answer="n2", verdict="fail"),
        ],
    )
    assert [item.answer for item in load_labels(path)] == ["n1", "n2"]


def test_negative_duplicate_answer_fails_closed(tmp_path):
    path = _write(
        tmp_path,
        "labels.json",
        [
            _item(arm="negative:owner", answer="n1", verdict="fail"),
            _item(arm="negative:owner", answer="n1", verdict="fail"),
        ],
    )
    with pytest.raises(LabelError) as exc:
        load_labels(path)
    assert str(path) in str(exc.value)
    assert "item 1" in str(exc.value)


def test_perturbation_uniqueness_is_case_and_arm(tmp_path):
    path = _write(
        tmp_path,
        "labels.json",
        [
            _item(arm="perturbation:number_swap", verdict="fail", rubric_version="construction"),
            _item(
                arm="perturbation:number_swap",
                answer="another",
                verdict="fail",
                rubric_version="construction",
            ),
        ],
    )
    with pytest.raises(LabelError) as exc:
        load_labels(path)
    assert str(path) in str(exc.value)
    assert "item 1" in str(exc.value)


@pytest.mark.parametrize(
    "item",
    [
        _item(arm="negative:owner", verdict="pass"),
        _item(arm="perturbation:number_swap", verdict="pass", rubric_version="construction"),
        _item(arm="perturbation:number_swap", verdict="fail", rubric_version="v2"),
        _item(arm="negative:", verdict="fail"),
        _item(arm="perturbation:", verdict="fail", rubric_version="construction"),
    ],
)
def test_invalid_prefixed_arm_states_fail_closed(tmp_path, item):
    path = _write(tmp_path, "labels.json", [item])
    with pytest.raises(LabelError) as exc:
        load_labels(path)
    assert str(path) in str(exc.value)
    assert "item 0" in str(exc.value)


def test_mixed_rubric_across_real_arms_within_a_file_fails_closed(tmp_path):
    path = _write(
        tmp_path,
        "labels.json",
        [_item("c1", rubric_version="v1"), _item("c2", rubric_version="v2")],
    )
    with pytest.raises(LabelError) as exc:
        load_labels(path)
    assert str(path) in str(exc.value)
    assert "item 1" in str(exc.value)
    assert "v1" in str(exc.value)
    assert "v2" in str(exc.value)


def test_mixed_rubric_across_files_fails_closed(tmp_path):
    first = _write(tmp_path, "first.json", [_item(rubric_version="v1")])
    second = _write(tmp_path, "second.json", [_item("c2", rubric_version="v2")])
    with pytest.raises(LabelError) as exc:
        load_labels(first, second)
    assert str(second) in str(exc.value)


def test_construction_and_negative_rubrics_do_not_count_as_mixed(tmp_path):
    path = _write(
        tmp_path,
        "labels.json",
        [
            _item(rubric_version="v2"),
            _item("c2", "perturbation:number_swap", verdict="fail", rubric_version="construction"),
            _item("c3", "negative:owner", verdict="fail", rubric_version="v1"),
        ],
    )
    assert len(load_labels(path)) == 3
