import json

from gnomon.dataset.labels import load_labels
from gnomon.metrics.alignment import self_agreement


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _config(tmp_path, *, seed=42, reproducible=True):
    seed_line = f"seed = {seed}\n" if seed is not None else ""
    config = tmp_path / "align.toml"
    config.write_text(
        f'''dataset_path = "{tmp_path / "cases.json"}"

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
''',
        encoding="utf-8",
    )
    return config


def _item(case_id, verdict, **overrides):
    return {
        "case_id": case_id,
        "arm": "on",
        "answer": overrides.pop("answer", f"answer {case_id}"),
        "contexts": overrides.pop("contexts", [f"context {case_id}"]),
        "verdict": verdict,
        "critique": "owner critique",
        "rubric_version": "v1",
        **overrides,
    }


def _labels(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _write_json(
        first,
        [
            _item(f"c{index}", verdict)
            for index, verdict in enumerate(["pass", "pass", "pass", "fail", "fail", "fail"], 1)
        ],
    )
    _write_json(
        second,
        [
            _item(f"c{index}", verdict)
            for index, verdict in enumerate(["pass", "pass", "fail", "fail", "fail", "pass"], 1)
        ],
    )
    return first, second


def test_self_agreement_prints_ja17_result(tmp_path, capsys):
    from gnomon.align import align_main

    config = _config(tmp_path)
    first, second = _labels(tmp_path)
    assert align_main(["-c", str(config), "--self-agreement", str(first), str(second)]) == 0
    output = capsys.readouterr().out
    document = json.loads(output)
    assert document == self_agreement(
        load_labels(first), load_labels(second), confidence_level=0.9, seed=42
    )
    assert "kappa" in document


def test_self_agreement_mismatched_answer_exits_nonzero(tmp_path, capsys):
    from gnomon.align import align_main

    config = _config(tmp_path)
    first, second = _labels(tmp_path)
    payload = json.loads(second.read_text(encoding="utf-8"))
    payload[1]["answer"] = "changed"
    _write_json(second, payload)

    assert align_main(["-c", str(config), "--self-agreement", str(first), str(second)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "answer" in captured.err
    assert "c2" in captured.err


def test_self_agreement_too_few_pairs_exits_nonzero(tmp_path, capsys):
    from gnomon.align import align_main

    config = _config(tmp_path)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _write_json(first, [_item("c1", "pass")])
    _write_json(second, [_item("c1", "pass")])

    assert align_main(["-c", str(config), "--self-agreement", str(first), str(second)]) == 1
    assert "at least 2" in capsys.readouterr().err


def test_self_agreement_null_seed_exits_nonzero(tmp_path, capsys):
    from gnomon.align import align_main

    config = _config(tmp_path, seed=None, reproducible=False)
    first, second = _labels(tmp_path)
    assert align_main(["-c", str(config), "--self-agreement", str(first), str(second)]) == 1
    captured = capsys.readouterr()
    assert "seed" in captured.err
    assert captured.out == ""
