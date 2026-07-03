"""Savings curve reporting for dual-arm session runs."""

from gnomon.domain.models import MetricResult
from gnomon.domain.session import TurnCost
from gnomon.metrics.confidence import aggregate_metric
from gnomon.runner.session_runner import SessionRunReport


def savings_report(report: SessionRunReport, *, seed: int, confidence_level=0.95) -> dict:
    pairs: dict[tuple[str, int], dict[str, TurnCost]] = {}
    non_provider_records = 0
    completion_tokens = {"axon_total": 0, "baseline_total": 0}

    for cost in report.turn_costs:
        if cost.usage_source != "provider":
            non_provider_records += 1
        completion_tokens[f"{cost.arm}_total"] += cost.completion_tokens

        key = (cost.session_id, cost.turn)
        arm_costs = pairs.setdefault(key, {})
        if cost.arm in arm_costs:
            raise ValueError(
                f"duplicate {cost.arm!r} cost for session {cost.session_id!r} turn {cost.turn}"
            )
        arm_costs[cost.arm] = cost

    per_turn_values: dict[int, list[float]] = {}
    per_session_totals: dict[str, dict[str, int]] = {}

    for (session_id, turn), arm_costs in sorted(pairs.items()):
        missing = {"axon", "baseline"} - arm_costs.keys()
        if missing:
            missing_arms = sorted(missing)
            raise ValueError(
                f"incomplete arm pair for session {session_id!r} "
                f"turn {turn}: missing {missing_arms}"
            )

        axon = arm_costs["axon"]
        baseline = arm_costs["baseline"]
        if baseline.prompt_tokens == 0:
            raise ValueError(
                f"baseline prompt_tokens is zero for session {session_id!r} turn {turn}"
            )

        per_turn_values.setdefault(turn, []).append(
            1.0 - axon.prompt_tokens / baseline.prompt_tokens
        )
        totals = per_session_totals.setdefault(session_id, {"axon": 0, "baseline": 0})
        totals["axon"] += axon.prompt_tokens
        totals["baseline"] += baseline.prompt_tokens

    per_turn = []
    crossover_turn = None
    for turn in sorted(per_turn_values):
        result = aggregate_metric(
            f"savings_turn_{turn}",
            per_turn_values[turn],
            confidence_level=confidence_level,
            seed=seed,
        )
        row = _savings_metric(result)
        row["turn"] = turn
        per_turn.append(row)
        if crossover_turn is None and result.ci_low > 0:
            crossover_turn = turn

    cumulative_values = [
        1.0 - totals["axon"] / totals["baseline"] for totals in per_session_totals.values()
    ]
    cumulative = _savings_metric(
        aggregate_metric(
            "savings_cumulative",
            cumulative_values,
            confidence_level=confidence_level,
            seed=seed,
        )
    )

    axon_quality = report.final_faithfulness["axon"]
    baseline_quality = report.final_faithfulness["baseline"]
    quality_gate = "fail" if axon_quality.ci_high < baseline_quality.ci_low else "pass"

    return {
        "per_turn": per_turn,
        "cumulative": cumulative,
        "crossover_turn": crossover_turn,
        "final_faithfulness": {
            "axon": axon_quality.model_dump(),
            "baseline": baseline_quality.model_dump(),
        },
        "quality_gate": quality_gate,
        "validity": {"non_provider_records": non_provider_records},
        "completion_tokens": completion_tokens,
    }


def to_text(report_dict: dict) -> str:
    lines = [
        "Savings report",
        "==============",
        "",
        (f"Cumulative savings: {_fmt_interval(report_dict['cumulative'])}"),
        f"Quality gate: {report_dict['quality_gate']}",
        (f"Validity: {report_dict['validity']['non_provider_records']} non-provider record(s)"),
        "",
        "Savings curve:",
    ]
    for row in report_dict["per_turn"]:
        lines.append(f"  turn {row['turn']}: {_fmt_interval(row)}")
    lines += [
        "",
        f"Crossover turn: {report_dict['crossover_turn']}",
        (
            "Completion tokens: "
            f"axon={report_dict['completion_tokens']['axon_total']} "
            f"baseline={report_dict['completion_tokens']['baseline_total']}"
        ),
    ]
    return "\n".join(lines)


def _savings_metric(result: MetricResult) -> dict:
    return {
        "savings_mean": result.mean,
        "ci_low": result.ci_low,
        "ci_high": result.ci_high,
        "n": result.n,
    }


def _fmt_interval(row: dict) -> str:
    return (
        f"mean={row['savings_mean']:.3f} [{row['ci_low']:.3f}, {row['ci_high']:.3f}] (N={row['n']})"
    )
