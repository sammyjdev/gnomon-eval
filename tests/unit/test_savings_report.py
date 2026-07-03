import pytest

from gnomon.domain.models import MetricResult
from gnomon.domain.session import TurnCost
from gnomon.reporting.savings import savings_report, to_text
from gnomon.runner.session_runner import SessionRunReport


def _metric(name, mean, lo, hi, n=2):
    return MetricResult(
        metric=name,
        mean=mean,
        ci_low=lo,
        ci_high=hi,
        n=n,
        confidence_level=0.95,
    )


def _cost(session_id, turn, arm, prompt_tokens, *, usage_source="provider"):
    return TurnCost(
        session_id=session_id,
        turn=turn,
        arm=arm,
        prompt_tokens=prompt_tokens,
        completion_tokens=10 if arm == "axon" else 20,
        total_tokens=prompt_tokens + (10 if arm == "axon" else 20),
        latency_ms=25.0,
        usage_source=usage_source,
    )


def _report(*, final_faithfulness=None, usage_source="provider"):
    # Per-turn savings:
    # turn 0: 1 - 120/100 = -0.2; 1 - 240/200 = -0.2; mean = -0.2
    # turn 1: 1 - 80/100 = 0.2; 1 - 160/200 = 0.2; mean = 0.2
    # turn 2: 1 - 50/100 = 0.5; 1 - 100/200 = 0.5; mean = 0.5
    # Cumulative:
    # s1: 1 - (120 + 80 + 50) / (100 + 100 + 100) = 1/6
    # s2: 1 - (240 + 160 + 100) / (200 + 200 + 200) = 1/6
    turn_costs = [
        _cost("s1", 0, "axon", 120, usage_source=usage_source),
        _cost("s1", 1, "axon", 80),
        _cost("s1", 2, "axon", 50),
        _cost("s1", 0, "baseline", 100),
        _cost("s1", 1, "baseline", 100),
        _cost("s1", 2, "baseline", 100),
        _cost("s2", 0, "axon", 240),
        _cost("s2", 1, "axon", 160),
        _cost("s2", 2, "axon", 100),
        _cost("s2", 0, "baseline", 200),
        _cost("s2", 1, "baseline", 200),
        _cost("s2", 2, "baseline", 200),
    ]
    return SessionRunReport(
        turn_costs=turn_costs,
        final_faithfulness=final_faithfulness
        or {
            "axon": _metric("final_faithfulness_axon", 0.80, 0.70, 0.90),
            "baseline": _metric("final_faithfulness_baseline", 0.75, 0.65, 0.85),
        },
    )


def test_per_turn_savings_means_match_hand_computation():
    payload = savings_report(_report(), seed=123)

    assert [row["savings_mean"] for row in payload["per_turn"]] == [
        pytest.approx(-0.2),
        pytest.approx(0.2),
        pytest.approx(0.5),
    ]


def test_cumulative_savings_mean_matches_hand_computation():
    payload = savings_report(_report(), seed=123)

    assert payload["cumulative"]["savings_mean"] == pytest.approx(1 / 6)


def test_negative_savings_are_preserved():
    payload = savings_report(_report(), seed=123)

    assert payload["per_turn"][0]["savings_mean"] == pytest.approx(-0.2)


def test_crossover_turn_is_first_turn_with_positive_ci_low():
    payload = savings_report(_report(), seed=123)

    assert payload["per_turn"][0]["ci_low"] < 0
    assert payload["per_turn"][1]["ci_low"] > 0
    assert payload["crossover_turn"] == 1


def test_quality_gate_fails_only_when_axon_interval_is_entirely_below_baseline():
    failing = _report(
        final_faithfulness={
            "axon": _metric("final_faithfulness_axon", 0.40, 0.30, 0.50),
            "baseline": _metric("final_faithfulness_baseline", 0.70, 0.60, 0.80),
        }
    )
    passing = _report()

    assert savings_report(failing, seed=123)["quality_gate"] == "fail"
    assert savings_report(passing, seed=123)["quality_gate"] == "pass"


def test_non_provider_records_are_counted():
    payload = savings_report(_report(usage_source="estimate"), seed=123)

    assert payload["validity"]["non_provider_records"] == 1


def test_zero_baseline_prompt_tokens_raise_value_error():
    report = _report()
    costs = list(report.turn_costs)
    costs[3] = _cost("s1", 0, "baseline", 0)

    with pytest.raises(ValueError, match="baseline prompt_tokens"):
        savings_report(
            SessionRunReport(
                turn_costs=costs,
                final_faithfulness=report.final_faithfulness,
            ),
            seed=123,
        )


def test_incomplete_arm_pair_raises_value_error():
    report = _report()

    with pytest.raises(ValueError, match="incomplete"):
        savings_report(
            SessionRunReport(
                turn_costs=report.turn_costs[:-1],
                final_faithfulness=report.final_faithfulness,
            ),
            seed=123,
        )


def test_text_output_contains_headline_rows_and_gate_verdict():
    text = to_text(savings_report(_report(), seed=123))

    assert "Savings report" in text
    assert "Cumulative savings" in text
    assert "turn 0" in text
    assert "turn 1" in text
    assert "turn 2" in text
    assert "Quality gate: pass" in text


def test_text_output_renders_absent_crossover():
    report_dict = savings_report(_report(), seed=123)
    report_dict["crossover_turn"] = None

    text = to_text(report_dict)

    assert "None" in text
