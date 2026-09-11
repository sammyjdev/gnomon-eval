import json

import pytest

from gnomon.dataset.labels import load_labels
from gnomon.domain.models import EvalCase, RagResponse
from gnomon.judge.stub import StubJudge
from gnomon.metrics.alignment import disagreement_list

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


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _align_toml(tmp_path, *, panel=True, seed=42, reproducible=True):
    cases = tmp_path / "cases.json"
    _write_json(cases, CASES)
    seed_line = f"seed = {seed}\n" if seed is not None else ""
    members = (
        ""
        if not panel
        else """
[panel]
[[panel.judges]]
provider = "stub"
family = "alpha"
[[panel.judges]]
provider = "stub"
family = "beta"
"""
    )
    config = tmp_path / "align.toml"
    config.write_text(
        f'''dataset_path = "{cases}"

[eval]
reproducible = {str(reproducible).lower()}
{seed_line}judge_runs = 2
confidence_level = 0.9

[target]
kind = "mock"

[judge]
provider = "stub"

[gate]
faithfulness = 0.5
{members}''',
        encoding="utf-8",
    )
    return config


def _label_item(case_id, arm, verdict, **overrides):
    case = next(item for item in CASES if item["id"] == case_id)
    return {
        "case_id": case_id,
        "arm": arm,
        "answer": overrides.pop("answer", case["expected_answer"]),
        "contexts": overrides.pop("contexts", ["ctx"]),
        "verdict": verdict,
        "critique": overrides.pop("critique", f"critique {case_id} {arm}"),
        "rubric_version": overrides.pop("rubric_version", "v2"),
        "question": overrides.pop("question", case["question"]),
        **overrides,
    }


def _labels(tmp_path):
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    _write_json(
        first,
        [_label_item("c1", "on", "pass"), _label_item("c2", "on", "fail")],
    )
    _write_json(
        second,
        [_label_item("c1", "off", "pass"), _label_item("c3", "on", "fail")],
    )
    return first, second


def _expected_scores(labels):
    cases = {item["id"]: EvalCase(**item) for item in CASES}
    items = load_labels(*labels)
    scores = {"alpha": [], "beta": []}
    entries = []
    for index, item in enumerate(items):
        response = RagResponse(
            answer=item.answer,
            contexts=item.contexts,
            total_tokens=0,
            latency_ms=0.0,
        )
        for judge_id in ("alpha", "beta"):
            score = (
                sum(
                    StubJudge()
                    .score(cases[item.case_id], response, seed=42, run=run)
                    .scores["faithfulness"]
                    for run in (0, 1)
                )
                / 2
            )
            scores[judge_id].append(score)
            entries.append(
                {
                    "item": index,
                    "case_id": item.case_id,
                    "arm": item.arm,
                    "judge_id": judge_id,
                    "score": score,
                }
            )
    return scores, entries


def test_main_dispatches_align_subcommand(monkeypatch):
    import gnomon.align as align
    import gnomon.cli as cli

    monkeypatch.setattr(align, "align_main", lambda argv: 7)
    assert cli.main(["align", "-c", "x"]) == 7


def test_align_help_exits_zero():
    from gnomon.align import align_main

    with pytest.raises(SystemExit) as exc:
        align_main(["--help"])
    assert exc.value.code == 0


def test_stub_panel_prints_alignment_report_disagreements_and_scores(tmp_path, capsys):
    from gnomon.align import align_main

    config = _align_toml(tmp_path)
    labels = _labels(tmp_path)
    expected_by_judge, expected_entries = _expected_scores(labels)

    rc = align_main(
        [
            "-c",
            str(config),
            "--labels",
            str(labels[0]),
            "--labels",
            str(labels[1]),
            "--threshold",
            "0.75",
            "--json",
        ]
    )

    document = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert list(document) == [
        "threshold",
        "confidence_level",
        "seed",
        "rubric_versions",
        "judges",
        "disagreements",
        "scores",
    ]
    assert document["threshold"] == 0.75
    assert document["confidence_level"] == 0.9
    assert document["seed"] == 42
    assert [judge["judge_id"] for judge in document["judges"]] == ["alpha", "beta"]
    assert document["scores"] == expected_entries
    assert document["disagreements"] == disagreement_list(
        load_labels(*labels), expected_by_judge, threshold=0.75
    )


def test_declared_call_count_printed_before_first_judge_call_and_is_exact(
    tmp_path, capsys, monkeypatch
):
    import gnomon.align as align

    config = _align_toml(tmp_path)
    labels = _labels(tmp_path)
    record = {"calls": [], "first": None}

    class SpyJudge(StubJudge):
        def score(self, case, response, *, seed, run):
            if record["first"] is None:
                record["first"] = capsys.readouterr()
            record["calls"].append((case.id, run))
            return super().score(case, response, seed=seed, run=run)

    monkeypatch.setattr(align, "build_judge", lambda cfg: SpyJudge())
    rc = align.align_main(
        [
            "-c",
            str(config),
            "--labels",
            str(labels[0]),
            "--labels",
            str(labels[1]),
            "--threshold",
            "0.75",
            "--json",
        ]
    )

    assert rc == 0
    assert len(record["calls"]) == 16
    assert "declared judge calls: 16 (4 items x 2 members x 2 runs)" in record["first"].err
    assert record["first"].out == ""


def test_two_runs_are_byte_identical_json_with_scores(tmp_path, capsys):
    from gnomon.align import align_main

    config = _align_toml(tmp_path)
    labels = _labels(tmp_path)
    args = [
        "-c",
        str(config),
        "--labels",
        str(labels[0]),
        "--labels",
        str(labels[1]),
        "--threshold",
        "0.75",
        "--json",
    ]

    assert align_main(args) == 0
    first = capsys.readouterr().out
    assert align_main(args) == 0
    second = capsys.readouterr().out

    assert first == second
    assert '"scores"' in first


def test_cli_json_keys_avoid_banned_rate_words(tmp_path, capsys):
    from gnomon.align import align_main

    config = _align_toml(tmp_path)
    labels = _labels(tmp_path)
    assert (
        align_main(
            [
                "-c",
                str(config),
                "--labels",
                str(labels[0]),
                "--labels",
                str(labels[1]),
                "--threshold",
                "0.75",
                "--json",
            ]
        )
        == 0
    )
    document = json.loads(capsys.readouterr().out)

    def keys(value):
        if isinstance(value, dict):
            yield from value
            for child in value.values():
                yield from keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from keys(child)

    for key in keys(document):
        assert "accuracy" not in key
        assert "match" not in key
        assert "agreement" not in key or key == "disagreements"


def test_every_alignment_number_carries_interval_or_reason(tmp_path, capsys):
    from gnomon.align import align_main

    config = _align_toml(tmp_path)
    labels = _labels(tmp_path)
    assert (
        align_main(
            [
                "-c",
                str(config),
                "--labels",
                str(labels[0]),
                "--labels",
                str(labels[1]),
                "--threshold",
                "0.75",
                "--json",
            ]
        )
        == 0
    )
    document = json.loads(capsys.readouterr().out)
    for judge in document["judges"]:
        for stratum in [judge["real"], *judge["arms"]]:
            assert isinstance(stratum["n_owner_pass"], int)
            assert isinstance(stratum["n_owner_fail"], int)
            for name in ("auc", "tpr", "tnr", "kappa"):
                stat = stratum[name]
                assert (
                    stat["value"] is None
                    or (stat["ci_low"] is not None and stat["ci_high"] is not None)
                    or stat["reason"] is not None
                )


def test_text_mode_prints_intervals_not_bare_numbers(tmp_path, capsys):
    from gnomon.align import align_main

    config = _align_toml(tmp_path)
    labels = _labels(tmp_path)
    assert (
        align_main(
            [
                "-c",
                str(config),
                "--labels",
                str(labels[0]),
                "--labels",
                str(labels[1]),
                "--threshold",
                "0.75",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "alpha" in output
    assert "auc=" in output
    assert all("[" in line or "null (" in line for line in output.splitlines() if "auc=" in line)
    assert not output.startswith("{")


def test_missing_threshold_is_usage_error_with_zero_judge_calls(tmp_path, capsys, monkeypatch):
    import gnomon.align as align

    config = _align_toml(tmp_path)
    labels = _labels(tmp_path)
    calls = []
    monkeypatch.setattr(align, "build_judge", lambda cfg: calls.append(cfg) or StubJudge())

    assert align.align_main(["-c", str(config), "--labels", str(labels[0])]) == 2
    captured = capsys.readouterr()
    assert calls == []
    assert captured.out == ""


@pytest.mark.parametrize("threshold", ["1.5", "-0.1", "nan"])
def test_threshold_out_of_range_rejected_before_any_judge_call(
    tmp_path, capsys, monkeypatch, threshold
):
    import gnomon.align as align

    config = _align_toml(tmp_path)
    labels = _labels(tmp_path)
    calls = []
    monkeypatch.setattr(align, "build_judge", lambda cfg: calls.append(cfg) or StubJudge())

    assert (
        align.align_main(["-c", str(config), "--labels", str(labels[0]), "--threshold", threshold])
        == 2
    )
    captured = capsys.readouterr()
    assert calls == []
    assert captured.out == ""
    assert "threshold" in captured.err


def test_unknown_case_id_fails_closed_without_report(tmp_path, capsys):
    from gnomon.align import align_main

    config = _align_toml(tmp_path)
    labels = _labels(tmp_path)
    _write_json(labels[0], [_label_item("c1", "on", "pass"), _label_item("c2", "on", "fail")])
    payload = json.loads(labels[0].read_text(encoding="utf-8"))
    payload[0]["case_id"] = "zz"
    _write_json(labels[0], payload)

    assert align_main(["-c", str(config), "--labels", str(labels[0]), "--threshold", "0.75"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "zz" in captured.err


def test_question_mismatch_fails_closed_without_report(tmp_path, capsys):
    from gnomon.align import align_main

    config = _align_toml(tmp_path)
    label = tmp_path / "bad.json"
    _write_json(label, [_label_item("c1", "on", "pass", question="wrong?")])

    assert align_main(["-c", str(config), "--labels", str(label), "--threshold", "0.75"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "c1" in captured.err
    assert "question" in captured.err


def test_judge_error_aborts_with_no_partial_report(tmp_path, capsys, monkeypatch):
    import gnomon.align as align

    config = _align_toml(tmp_path)
    labels = _labels(tmp_path)
    calls = []

    class BrokenJudge(StubJudge):
        def score(self, case, response, *, seed, run):
            calls.append((case.id, run))
            if len(calls) == 2:
                raise RuntimeError("broken")
            return super().score(case, response, seed=seed, run=run)

    monkeypatch.setattr(align, "build_judge", lambda cfg: BrokenJudge())
    assert (
        align.align_main(["-c", str(config), "--labels", str(labels[0]), "--threshold", "0.75"])
        == 1
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "alpha" in captured.err
    assert "c1" in captured.err
    assert 0 < len(calls) < 8


def test_null_seed_fails_closed_before_any_judge_call(tmp_path, capsys, monkeypatch):
    import gnomon.align as align

    config = _align_toml(tmp_path, seed=None, reproducible=False)
    labels = _labels(tmp_path)
    calls = []
    monkeypatch.setattr(align, "build_judge", lambda cfg: calls.append(cfg) or StubJudge())

    assert (
        align.align_main(["-c", str(config), "--labels", str(labels[0]), "--threshold", "0.75"])
        == 1
    )
    captured = capsys.readouterr()
    assert calls == []
    assert captured.out == ""
    assert "seed" in captured.err


def test_missing_panel_section_fails_closed(tmp_path, capsys):
    from gnomon.align import align_main

    config = _align_toml(tmp_path, panel=False)
    labels = _labels(tmp_path)

    assert align_main(["-c", str(config), "--labels", str(labels[0]), "--threshold", "0.75"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "panel" in captured.err


def test_scoring_without_labels_is_usage_error(tmp_path, capsys):
    from gnomon.align import align_main

    config = _align_toml(tmp_path)
    assert align_main(["-c", str(config), "--threshold", "0.75"]) == 2
    assert capsys.readouterr().out == ""
