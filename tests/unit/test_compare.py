"""compare(): quality deltas from two report dicts + recall token cost."""

from gnomon.reporting.compare import compare, telemetry_cost_line


def _metric(name, mean, lo, hi, n=15):
    return {
        "metric": name,
        "mean": mean,
        "ci_low": lo,
        "ci_high": hi,
        "n": n,
        "confidence_level": 0.95,
    }


def _report(metrics, per_case):
    return {
        "metrics": metrics,
        "cost": {
            "total_tokens": sum(c["total_tokens"] for c in per_case),
            "mean_latency_ms": 100.0,
        },
        "per_case": per_case,
    }


_ON = _report(
    [_metric("faithfulness", 0.85, 0.80, 0.90), _metric("context_precision", 0.78, 0.70, 0.86)],
    [
        {"case_id": "c1", "total_tokens": 900, "latency_ms": 100.0},
        {"case_id": "c2", "total_tokens": 1100, "latency_ms": 100.0},
    ],
)
_OFF = _report(
    [_metric("faithfulness", 0.60, 0.52, 0.68)],
    [
        {"case_id": "c1", "total_tokens": 300, "latency_ms": 80.0},
        {"case_id": "c2", "total_tokens": 500, "latency_ms": 80.0},
    ],
)


def test_metric_delta_reported():
    out = compare(_ON, _OFF)
    assert "faithfulness" in out
    assert "+0.250" in out  # 0.85 - 0.60
    assert "[0.800, 0.900]" in out and "[0.520, 0.680]" in out


def test_on_only_metric_flagged_as_no_baseline():
    out = compare(_ON, _OFF)
    assert "context_precision" in out
    assert "no off-run baseline" in out


def test_per_case_token_delta():
    out = compare(_ON, _OFF)
    # mean per-case delta: ((900-300) + (1100-500)) / 2 = 600
    assert "+600" in out


def test_telemetry_cost_line_mean_prompt_delta():
    records = [
        {"include_context": True, "prompt_tokens": 800, "usage_source": "provider"},
        {"include_context": True, "prompt_tokens": 1000, "usage_source": "provider"},
        {"include_context": False, "prompt_tokens": 100, "usage_source": "provider"},
        {"include_context": False, "prompt_tokens": 300, "usage_source": "provider"},
    ]
    line = telemetry_cost_line(records)
    assert "+700" in line  # mean on (900) - mean off (200)


def test_telemetry_cost_line_flags_estimates():
    records = [
        {"include_context": True, "prompt_tokens": 800, "usage_source": "estimate"},
        {"include_context": False, "prompt_tokens": 100, "usage_source": "provider"},
    ]
    line = telemetry_cost_line(records)
    assert "WARNING" in line and "estimate" in line


def test_missing_case_produces_warning():
    off_partial = _report(
        [_metric("faithfulness", 0.60, 0.52, 0.68)],
        [{"case_id": "c1", "total_tokens": 300, "latency_ms": 80.0}],
    )
    out = compare(_ON, off_partial)
    assert "WARNING" in out
    assert "c2" in out


def test_telemetry_insufficient_when_one_arm_empty():
    only_on = [{"include_context": True, "prompt_tokens": 800, "usage_source": "provider"}]
    assert "insufficient telemetry" in telemetry_cost_line(only_on)
    assert "insufficient telemetry" in telemetry_cost_line([])
