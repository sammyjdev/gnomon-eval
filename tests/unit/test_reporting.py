"""Reporting tests (RF-08).

The report is serialised for machines and for humans from the same source
object, so the two cannot diverge. Both forms carry, per metric, the mean,
the interval bounds and N, plus cost and latency.
"""

import json

from gnomon.domain.models import CaseCost, CaseScore, EvalReport, MetricResult
from gnomon.reporting.report import to_dict, to_text

REPORT = EvalReport(
    metrics=[
        MetricResult(
            metric="faithfulness",
            mean=0.85,
            ci_low=0.80,
            ci_high=0.90,
            n=8,
            confidence_level=0.95,
        )
    ],
    per_case_cost=[CaseCost(case_id="case-1", total_tokens=137, latency_ms=512.0)],
    case_scores={"faithfulness": [CaseScore(case_id="case-1", score=0.9)]},
)


def test_machine_format_is_json_serialisable_and_carries_interval():
    payload = to_dict(REPORT)
    json.dumps(payload)  # must not raise
    metric = payload["metrics"][0]
    assert metric["metric"] == "faithfulness"
    assert metric["mean"] == 0.85
    assert metric["ci_low"] == 0.80
    assert metric["ci_high"] == 0.90
    assert metric["n"] == 8


def test_machine_format_carries_cost_and_latency():
    payload = to_dict(REPORT)
    assert payload["cost"]["total_tokens"] == 137
    assert payload["cost"]["mean_latency_ms"] == 512.0
    assert payload["per_case"][0]["case_id"] == "case-1"


def test_human_format_shows_interval_n_and_cost():
    text = to_text(REPORT)
    assert "faithfulness" in text
    assert "0.85" in text
    assert "0.80" in text and "0.90" in text
    assert "8" in text  # N of runs
    assert "137" in text  # tokens
    assert "512" in text  # latency


def test_both_formats_agree_on_the_mean():
    # Same source → no divergence between machine and human.
    payload = to_dict(REPORT)
    text = to_text(REPORT)
    assert str(payload["metrics"][0]["mean"]) in text


def test_machine_format_carries_case_scores():
    # Issue #52: case_scores (per-case denoised scores, ADR-G8) must reach
    # the CLI --json output -- previously only reachable via run_from_config
    # directly, forcing consumers to write their own capture scripts.
    payload = to_dict(REPORT)
    assert payload["case_scores"]["faithfulness"][0]["case_id"] == "case-1"
    assert payload["case_scores"]["faithfulness"][0]["score"] == 0.9
