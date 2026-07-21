"""Panel reporting tests (ADR-0012)."""

import json

from gnomon.domain.models import (
    CaseCost,
    DisagreementStat,
    MetricResult,
    PanelJudgeReport,
    PanelReport,
)
from gnomon.reporting.panel_report import panel_to_dict, panel_to_text

METRIC = MetricResult(
    metric="faithfulness",
    mean=0.85,
    ci_low=0.80,
    ci_high=0.90,
    n=2,
    confidence_level=0.95,
)
REPORT = PanelReport(
    per_case_cost=[CaseCost(case_id="case-1", total_tokens=137, latency_ms=512.0)],
    judge_reports=[
        PanelJudgeReport(judge_id="judge-a", family="vendor-a", metrics=[METRIC]),
        PanelJudgeReport(judge_id="judge-b", family="vendor-b", metrics=[METRIC]),
    ],
    disagreement=[
        DisagreementStat(
            metric="faithfulness",
            case_deltas={"case-1": 0.2},
            pairwise_correlation={"judge-a|judge-b": 0.5},
        )
    ],
)


def test_panel_machine_format_is_json_serialisable():
    json.dumps(panel_to_dict(REPORT))


def test_panel_machine_format_carries_each_judge_and_metric():
    judges = panel_to_dict(REPORT)["judges"]
    assert [(judge["judge_id"], judge["family"]) for judge in judges] == [
        ("judge-a", "vendor-a"),
        ("judge-b", "vendor-b"),
    ]
    assert judges[0]["metrics"][0] == {
        "metric": "faithfulness",
        "mean": 0.85,
        "ci_low": 0.80,
        "ci_high": 0.90,
        "n": 2,
        "confidence_level": 0.95,
    }


def test_panel_machine_format_carries_disagreement():
    disagreement = panel_to_dict(REPORT)["disagreement"][0]
    assert disagreement["case_deltas"] == {"case-1": 0.2}
    assert disagreement["pairwise_correlation"] == {"judge-a|judge-b": 0.5}


def test_panel_machine_format_carries_cost_and_per_case_latency():
    payload = panel_to_dict(REPORT)
    assert payload["cost"] == {"total_tokens": 137, "mean_latency_ms": 512.0}
    assert payload["per_case"] == [{"case_id": "case-1", "total_tokens": 137, "latency_ms": 512.0}]


def test_panel_human_format_shows_each_judge_metric_and_disagreement():
    text = panel_to_text(REPORT)
    assert "Panel evaluation report" in text
    assert "judge-a" in text and "judge-b" in text
    assert "faithfulness" in text
    assert "0.85" in text
    assert "0.80" in text and "0.90" in text
    assert "case-1" in text
    assert "judge-a|judge-b" in text
