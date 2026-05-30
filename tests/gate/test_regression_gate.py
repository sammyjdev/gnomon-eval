"""Regression gate as an executable CI check (RF-09).

Deterministic path only: mock target + stub judge, so the gate verdict is
stable in CI without Ollama or a live RAG. The real-backend gate is the
documented offline run in the README.
"""

import json

from gnomon.cli import run_from_config
from gnomon.config.run_config import RunConfig


def test_gate_passes_on_the_deterministic_path(tmp_path):
    dataset = tmp_path / "cases.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "id": "c1",
                    "question": "q",
                    "expected_answer": "a",
                    "expected_contexts": ["ctx"],
                }
            ]
        ),
        encoding="utf-8",
    )
    cfg = RunConfig(
        dataset_path=str(dataset),
        eval={"reproducible": True, "seed": 42, "judge_runs": 8},
        target={"kind": "mock"},
        judge={"provider": "stub"},
        gate={"thresholds": {"faithfulness": 0.5, "context_precision": 0.5}},
    )
    _, gate = run_from_config(cfg)
    assert gate.passed, gate.failures
