import copy
import json

import pytest

from gnomon.dataset.labels import load_labels
from gnomon.domain.models import EvalCase
from gnomon.judge.perturbation import known_fail_perturbations

CASES = [
    {
        "id": "c1",
        "question": "q1?",
        "expected_answer": "Use `fn` with 42.",
        "expected_contexts": ["ctx `fn` 42."],
    },
    {
        "id": "c2",
        "question": "q2?",
        "expected_answer": "Plain answer 7.",
        "expected_contexts": ["ctx2"],
    },
    {
        "id": "c3",
        "question": "q3?",
        "expected_answer": "No digits here.",
        "expected_contexts": ["ctx3"],
    },
]

REPORT_ON = {
    "responses": [
        {"case_id": "c1", "answer": "a1", "contexts": ["x"]},
        {"case_id": "c2", "answer": "a2", "contexts": ["y"]},
    ],
    "metrics": [],
}
REPORT_OFF = {
    "responses": [
        {"case_id": "c1", "answer": "a1o", "contexts": ["x"]},
        {"case_id": "c3", "answer": "a3", "contexts": []},
    ]
}


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _config(tmp_path):
    cases = tmp_path / "cases.json"
    _write_json(cases, CASES)
    config = tmp_path / "align.toml"
    config.write_text(
        f'''dataset_path = "{cases}"

[eval]
reproducible = true
seed = 42
judge_runs = 2
confidence_level = 0.9

[target]
kind = "mock"

[judge]
provider = "stub"

[gate]
faithfulness = 0.5
''',
        encoding="utf-8",
    )
    return config


def _reports(tmp_path):
    on = tmp_path / "on.json"
    off = tmp_path / "off.json"
    _write_json(on, REPORT_ON)
    _write_json(off, REPORT_OFF)
    return on, off


def _run_export(config, output, *arms):
    from gnomon.align import align_main

    return align_main(["-c", str(config), "--export", str(output), *arms])


def _expected_perturbations():
    return [
        {
            "case_id": case["id"],
            "arm": f"perturbation:{kind}",
            "answer": answer,
            "contexts": case["expected_contexts"],
            "question": case["question"],
            "verdict": "fail",
            "critique": f"known-fail perturbation: {kind}",
            "rubric_version": "construction",
        }
        for case in CASES
        for kind, answer in known_fail_perturbations(EvalCase(**case))
    ]


def test_export_writes_labels_todo_and_perturbations(tmp_path, capsys):
    config = _config(tmp_path)
    on, off = _reports(tmp_path)
    output = tmp_path / "out"

    assert _run_export(config, output, f"on={on}", f"off={off}") == 0
    assert capsys.readouterr().out == ""
    assert json.loads((output / "labels.todo.json").read_text(encoding="utf-8")) == [
        {
            "case_id": "c1",
            "arm": "on",
            "answer": "a1",
            "contexts": ["x"],
            "verdict": None,
            "critique": "",
            "rubric_version": "",
            "question": "q1?",
        },
        {
            "case_id": "c2",
            "arm": "on",
            "answer": "a2",
            "contexts": ["y"],
            "verdict": None,
            "critique": "",
            "rubric_version": "",
            "question": "q2?",
        },
        {
            "case_id": "c1",
            "arm": "off",
            "answer": "a1o",
            "contexts": ["x"],
            "verdict": None,
            "critique": "",
            "rubric_version": "",
            "question": "q1?",
        },
        {
            "case_id": "c3",
            "arm": "off",
            "answer": "a3",
            "contexts": [],
            "verdict": None,
            "critique": "",
            "rubric_version": "",
            "question": "q3?",
        },
    ]
    assert (
        json.loads((output / "perturbations.json").read_text(encoding="utf-8"))
        == _expected_perturbations()
    )


def test_export_accepts_panel_wrapped_report_shape(tmp_path):
    config = _config(tmp_path)
    on, _ = _reports(tmp_path)
    _write_json(on, {"arm": "on", "panel": {"responses": REPORT_ON["responses"]}})
    output = tmp_path / "out"

    assert _run_export(config, output, f"on={on}") == 0
    assert json.loads((output / "labels.todo.json").read_text(encoding="utf-8")) == [
        {
            "case_id": "c1",
            "arm": "on",
            "answer": "a1",
            "contexts": ["x"],
            "verdict": None,
            "critique": "",
            "rubric_version": "",
            "question": "q1?",
        },
        {
            "case_id": "c2",
            "arm": "on",
            "answer": "a2",
            "contexts": ["y"],
            "verdict": None,
            "critique": "",
            "rubric_version": "",
            "question": "q2?",
        },
    ]


@pytest.mark.parametrize(
    ("payload", "index"),
    [
        ({"metrics": []}, None),
        ({"responses": []}, None),
        ([], None),
        ({"panel": {"judges": []}}, None),
        ({"responses": [{"case_id": "c1"}]}, 0),
    ],
)
def test_export_bad_response_document_fails_closed_naming_file(tmp_path, capsys, payload, index):
    config = _config(tmp_path)
    on, _ = _reports(tmp_path)
    _write_json(on, payload)
    output = tmp_path / "out"

    assert _run_export(config, output, f"on={on}") == 1
    captured = capsys.readouterr()
    assert on.name in captured.err
    if index is not None:
        assert str(index) in captured.err
    assert not (output / "labels.todo.json").exists()


def test_export_unknown_or_duplicate_case_fails_closed(tmp_path, capsys):
    config = _config(tmp_path)
    on, _ = _reports(tmp_path)
    payload = copy.deepcopy(REPORT_ON)
    payload["responses"][0]["case_id"] = "zz"
    _write_json(on, payload)
    output = tmp_path / "unknown"
    assert _run_export(config, output, f"on={on}") == 1
    assert "zz" in capsys.readouterr().err

    _write_json(on, {"responses": [REPORT_ON["responses"][0], REPORT_ON["responses"][0]]})
    output = tmp_path / "duplicate"
    assert _run_export(config, output, f"on={on}") == 1
    assert on.name in capsys.readouterr().err


@pytest.mark.parametrize("target", ["labels.todo.json", "perturbations.json"])
def test_export_refuses_to_overwrite_and_writes_nothing(tmp_path, capsys, target):
    config = _config(tmp_path)
    on, _ = _reports(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    (output / target).write_text("old", encoding="utf-8")

    assert _run_export(config, output, f"on={on}") == 1
    assert target in capsys.readouterr().err
    other = "perturbations.json" if target == "labels.todo.json" else "labels.todo.json"
    assert not (output / other).exists()


@pytest.mark.parametrize(
    "arguments",
    [
        ["onreport"],
        ["on=a", "on=b"],
        ["perturbation:x=a"],
        ["negative:y=a"],
    ],
)
def test_export_bad_arm_tokens_are_usage_errors(tmp_path, capsys, arguments):
    config = _config(tmp_path)
    output = tmp_path / "out"

    assert _run_export(config, output, *arguments) == 2
    assert capsys.readouterr().out == ""
    assert not output.exists()


def test_export_usage_errors_exit_two(tmp_path, capsys):
    from gnomon.align import align_main

    config = _config(tmp_path)
    output = tmp_path / "out"
    assert align_main(["-c", str(config), "--export", str(output)]) == 2
    assert capsys.readouterr().out == ""
    assert not output.exists()


def test_export_rejects_scoring_and_self_agreement_flags(tmp_path, capsys):
    from gnomon.align import align_main

    config = _config(tmp_path)
    on, _ = _reports(tmp_path)
    labels = tmp_path / "labels.json"
    _write_json(labels, [])
    output = tmp_path / "out"

    assert (
        align_main(
            [
                "-c",
                str(config),
                "--export",
                str(output),
                f"on={on}",
                "--labels",
                str(labels),
            ]
        )
        == 2
    )
    assert capsys.readouterr().out == ""
    assert not output.exists()
    assert (
        align_main(
            [
                "-c",
                str(config),
                "--export",
                str(output),
                f"on={on}",
                "--self-agreement",
                "first.json",
                "second.json",
            ]
        )
        == 2
    )
    assert capsys.readouterr().out == ""
    assert not output.exists()


def test_filled_template_and_perturbations_load_with_label_loader(tmp_path):
    config = _config(tmp_path)
    on, off = _reports(tmp_path)
    output = tmp_path / "out"
    assert _run_export(config, output, f"on={on}", f"off={off}") == 0
    todo = json.loads((output / "labels.todo.json").read_text(encoding="utf-8"))
    filled = copy.deepcopy(todo)
    for index, item in enumerate(filled):
        item["verdict"] = "pass" if index % 2 == 0 else "fail"
        item["critique"] = "owner critique"
        item["rubric_version"] = "v1"
    filled_path = tmp_path / "filled.json"
    _write_json(filled_path, filled)

    items = load_labels(filled_path, output / "perturbations.json")
    assert len(items) == len(todo) + len(_expected_perturbations())
    assert all(
        item.arm_class == "real" and item.rubric_version == "v1" for item in items[: len(todo)]
    )
    assert all(
        item.arm_class == "perturbation"
        and item.verdict == "fail"
        and item.rubric_version == "construction"
        and item.arm == f"perturbation:{item.arm.split(':', 1)[1]}"
        for item in items[len(todo) :]
    )
