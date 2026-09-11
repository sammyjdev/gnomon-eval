"""Tests for response persistence in EvalReport and PanelReport serialization (issue #71)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from gnomon.domain.models import (
    CaseCost,
    CaseResponse,
    CaseScore,
    DisagreementStat,
    EvalReport,
    MetricResult,
    PanelJudgeReport,
    PanelReport,
)
from gnomon.reporting.panel_report import panel_to_dict, panel_to_text
from gnomon.reporting.report import to_dict, to_text

M = MetricResult(
    metric="faithfulness", mean=0.85, ci_low=0.80, ci_high=0.90, n=2, confidence_level=0.95
)
COSTS = [
    CaseCost(case_id="case-1", total_tokens=137, latency_ms=512.0),
    CaseCost(case_id="case-2", total_tokens=63, latency_ms=88.0),
]
RESPONSES = [
    CaseResponse(
        case_id="case-1",
        answer="SENTINEL-ANSWER-1",
        contexts=["SENTINEL-CTX-1a", "SENTINEL-CTX-1b"],
    ),
    CaseResponse(case_id="case-2", answer="SENTINEL-ANSWER-2", contexts=[]),
]
EVAL_KW = {
    "metrics": [M],
    "per_case_cost": COSTS,
    "case_scores": {
        "faithfulness": [
            CaseScore(case_id="case-1", score=0.9),
            CaseScore(case_id="case-2", score=0.8),
        ]
    },
}
LEGACY_EVAL = EvalReport(**EVAL_KW)
EVAL_WITH = EvalReport(**EVAL_KW, responses=RESPONSES)
PANEL_KW = {
    "per_case_cost": COSTS,
    "judge_reports": [
        PanelJudgeReport(judge_id="judge-a", family="vendor-a", metrics=[M]),
        PanelJudgeReport(judge_id="judge-b", family="vendor-b", metrics=[M]),
    ],
    "disagreement": [
        DisagreementStat(
            metric="faithfulness",
            case_deltas={"case-1": 0.2, "case-2": 0.1},
            pairwise_correlation={"judge-a|judge-b": 0.5},
        )
    ],
}
LEGACY_PANEL = PanelReport(**PANEL_KW)
PANEL_WITH = PanelReport(**PANEL_KW, responses=RESPONSES)
EXPECTED_RESPONSES = [
    {
        "case_id": "case-1",
        "answer": "SENTINEL-ANSWER-1",
        "contexts": ["SENTINEL-CTX-1a", "SENTINEL-CTX-1b"],
    },
    {"case_id": "case-2", "answer": "SENTINEL-ANSWER-2", "contexts": []},
]

LEGACY_EVAL_DICT = {
    "metrics": [
        {
            "metric": "faithfulness",
            "mean": 0.85,
            "ci_low": 0.8,
            "ci_high": 0.9,
            "n": 2,
            "confidence_level": 0.95,
        }
    ],
    "cost": {"total_tokens": 200, "mean_latency_ms": 300.0},
    "per_case": [
        {"case_id": "case-1", "total_tokens": 137, "latency_ms": 512.0},
        {"case_id": "case-2", "total_tokens": 63, "latency_ms": 88.0},
    ],
    "case_scores": {
        "faithfulness": [
            {"case_id": "case-1", "score": 0.9},
            {"case_id": "case-2", "score": 0.8},
        ]
    },
}

LEGACY_EVAL_TEXT = (
    "Evaluation report\n"
    "=================\n\n"
    "Quality (judge metrics):\n"
    "  faithfulness: mean=0.850 [0.800, 0.900] (95% CI, N=2)\n\n"
    "Cost & latency:\n"
    "  total tokens: 200\n"
    "  mean latency: 300.0 ms\n\n"
    "Per case:\n"
    "  case-1: 137 tokens, 512.0 ms\n"
    "  case-2: 63 tokens, 88.0 ms"
)

LEGACY_PANEL_DICT = {
    "judges": [
        {
            "judge_id": "judge-a",
            "family": "vendor-a",
            "metrics": [
                {
                    "metric": "faithfulness",
                    "mean": 0.85,
                    "ci_low": 0.8,
                    "ci_high": 0.9,
                    "n": 2,
                    "confidence_level": 0.95,
                }
            ],
        },
        {
            "judge_id": "judge-b",
            "family": "vendor-b",
            "metrics": [
                {
                    "metric": "faithfulness",
                    "mean": 0.85,
                    "ci_low": 0.8,
                    "ci_high": 0.9,
                    "n": 2,
                    "confidence_level": 0.95,
                }
            ],
        },
    ],
    "disagreement": [
        {
            "metric": "faithfulness",
            "case_deltas": {"case-1": 0.2, "case-2": 0.1},
            "pairwise_correlation": {"judge-a|judge-b": 0.5},
        }
    ],
    "cost": {"total_tokens": 200, "mean_latency_ms": 300.0},
    "per_case": [
        {"case_id": "case-1", "total_tokens": 137, "latency_ms": 512.0},
        {"case_id": "case-2", "total_tokens": 63, "latency_ms": 88.0},
    ],
}

LEGACY_PANEL_TEXT = (
    "Panel evaluation report\n"
    "=======================\n\n"
    "Judges:\n\n"
    "  judge-a (vendor-a):\n"
    "    faithfulness: mean=0.850 [0.800, 0.900] (95% CI, N=2)\n\n"
    "  judge-b (vendor-b):\n"
    "    faithfulness: mean=0.850 [0.800, 0.900] (95% CI, N=2)\n\n"
    "Disagreement:\n"
    "  faithfulness:\n"
    "    case-1: delta=0.200\n"
    "    case-2: delta=0.100\n"
    "    judge-a|judge-b: correlation=0.500\n\n"
    "Cost & latency:\n"
    "  total tokens: 200\n"
    "  mean latency: 300.0 ms\n\n"
    "Per case:\n"
    "  case-1: 137 tokens, 512.0 ms\n"
    "  case-2: 63 tokens, 88.0 ms"
)


def test_to_dict_serialises_responses_in_report_order() -> None:
    payload = to_dict(EVAL_WITH)
    assert payload["responses"] == EXPECTED_RESPONSES
    assert list(payload["responses"][0]) == ["case_id", "answer", "contexts"]
    json.dumps(payload)


def test_panel_to_dict_serialises_responses_in_report_order() -> None:
    payload = panel_to_dict(PANEL_WITH)
    assert payload["responses"] == EXPECTED_RESPONSES
    assert list(payload["responses"][0]) == ["case_id", "answer", "contexts"]
    json.dumps(payload)


def test_to_dict_legacy_keys_are_byte_identical() -> None:
    payload = to_dict(EVAL_WITH)
    assert list(payload) == [*LEGACY_EVAL_DICT, "responses"]
    legacy = {k: v for k, v in payload.items() if k != "responses"}
    assert json.dumps(legacy, indent=2) == json.dumps(LEGACY_EVAL_DICT, indent=2)


def test_panel_to_dict_legacy_keys_are_byte_identical() -> None:
    payload = panel_to_dict(PANEL_WITH)
    assert list(payload) == [*LEGACY_PANEL_DICT, "responses"]
    legacy = {k: v for k, v in payload.items() if k != "responses"}
    assert json.dumps(legacy, indent=2) == json.dumps(LEGACY_PANEL_DICT, indent=2)


def test_to_text_is_unchanged_by_responses() -> None:
    text = to_text(EVAL_WITH)
    assert text == LEGACY_EVAL_TEXT
    assert text == to_text(LEGACY_EVAL)
    assert "SENTINEL" not in text and "responses" not in text


def test_panel_to_text_is_unchanged_by_responses() -> None:
    text = panel_to_text(PANEL_WITH)
    assert text == LEGACY_PANEL_TEXT
    assert text == panel_to_text(LEGACY_PANEL)
    assert "SENTINEL" not in text and "responses" not in text


def test_report_built_without_responses_serialises_empty_list() -> None:
    assert LEGACY_EVAL.responses == []
    assert to_dict(LEGACY_EVAL)["responses"] == []
    assert to_dict(EvalReport(metrics=[], per_case_cost=[]))["responses"] == []


def test_panel_report_built_without_responses_serialises_empty_list() -> None:
    assert LEGACY_PANEL.responses == []
    assert (
        panel_to_dict(PanelReport(per_case_cost=[], judge_reports=[], disagreement=[]))["responses"]
        == []
    )


def test_case_response_rejects_empty_case_id() -> None:
    with pytest.raises(ValidationError):
        CaseResponse(case_id="", answer="a", contexts=[])


def test_contract_doc_names_responses_in_eval_and_panel_sections() -> None:
    text = (Path(__file__).resolve().parents[2] / "docs" / "GNOMON_GRAPHRAG_CONTRACT.md").read_text(
        encoding="utf-8"
    )
    assert "`responses`" in text.split("## F.")[1].split("## G.")[0]
    assert "`responses`" in text.split("## I.")[1]
