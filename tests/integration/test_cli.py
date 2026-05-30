import json

from gnomon.cli import build_judge, build_target, run_from_config
from gnomon.config.run_config import RunConfig
from gnomon.domain.interfaces import Judge, RagTarget


def _stub_run_config(tmp_path):
    dataset = tmp_path / "cases.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "id": "c1",
                    "question": "q1",
                    "expected_answer": "a1",
                    "expected_contexts": ["ctx1"],
                },
                {
                    "id": "c2",
                    "question": "q2",
                    "expected_answer": "a2",
                    "expected_contexts": ["ctx2"],
                },
            ]
        ),
        encoding="utf-8",
    )
    return RunConfig(
        dataset_path=str(dataset),
        eval={"reproducible": True, "seed": 42, "judge_runs": 8},
        target={"kind": "mock"},
        judge={"provider": "stub"},
        gate={"thresholds": {"faithfulness": 0.5, "context_precision": 0.5}},
    )


def test_factories_build_contract_types(tmp_path):
    cfg = _stub_run_config(tmp_path)
    assert isinstance(build_target(cfg.target), RagTarget)
    assert isinstance(build_judge(cfg.judge), Judge)


def test_run_from_config_returns_report_and_gate(tmp_path):
    cfg = _stub_run_config(tmp_path)
    report, gate = run_from_config(cfg)
    assert report.metric("faithfulness").n == 2  # n = number of cases (ADR-008)
    assert gate.passed is True
