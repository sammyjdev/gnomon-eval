"""Compare two eval reports (recall on vs off) and state the honest claim.

Quality deltas come from the two --json reports. The input-token cost of
recall ("+E input tokens/turn") comes from AXON's recall telemetry JSONL,
because gnomon reports only carry total_tokens (no prompt/completion split).

Single-turn A/B measures QUALITY lift and recall COST - never token savings
(that is a multi-turn phenomenon; see docs/adr/0009).

Usage:
    python -m gnomon.reporting.compare on.json off.json \
        [--telemetry ~/.../recall/requests.jsonl]
"""
import argparse
import json
from pathlib import Path


def _fmt_metric(m: dict) -> str:
    return (
        f"mean={m['mean']:.3f} [{m['ci_low']:.3f}, {m['ci_high']:.3f}] "
        f"({int(m['confidence_level'] * 100)}% CI, N={m['n']})"
    )


def compare(on: dict, off: dict) -> str:
    lines = ["A/B comparison: recall ON vs OFF", "=" * 34, "", "Quality:"]
    off_metrics = {m["metric"]: m for m in off["metrics"]}
    for m in on["metrics"]:
        base = off_metrics.get(m["metric"])
        if base is None:
            lines.append(
                f"  {m['metric']}: on {_fmt_metric(m)} (no off-run baseline)"
            )
        else:
            delta = m["mean"] - base["mean"]
            lines.append(
                f"  {m['metric']}: {delta:+.3f} "
                f"(on {_fmt_metric(m)} vs off {_fmt_metric(base)})"
            )

    on_by_case = {c["case_id"]: c["total_tokens"] for c in on["per_case"]}
    off_by_case = {c["case_id"]: c["total_tokens"] for c in off["per_case"]}
    shared = sorted(on_by_case.keys() & off_by_case.keys())
    deltas = [on_by_case[c] - off_by_case[c] for c in shared]
    mean_delta = sum(deltas) / len(deltas) if deltas else 0.0
    lines += [
        "",
        "Cost (total tokens, from gnomon reports):",
        f"  on={on['cost']['total_tokens']} off={off['cost']['total_tokens']} "
        f"mean per-case delta={mean_delta:+.0f}",
    ]
    missing = (on_by_case.keys() | off_by_case.keys()) - set(shared)
    if missing:
        lines.append(f"  WARNING: cases missing from one run: {sorted(missing)}")
    return "\n".join(lines)


def telemetry_cost_line(records: list[dict]) -> str:
    """Mean prompt-token delta (recall on - off) from AXON telemetry records."""
    estimates = [r for r in records if r.get("usage_source") != "provider"]
    on = [r["prompt_tokens"] for r in records if r["include_context"]]
    off = [r["prompt_tokens"] for r in records if not r["include_context"]]
    if not on or not off:
        return "Recall input cost: insufficient telemetry (need both arms)."
    delta = sum(on) / len(on) - sum(off) / len(off)
    line = (
        f"Recall input cost: {delta:+.0f} prompt tokens/turn "
        f"(mean over {len(on)} on / {len(off)} off requests)"
    )
    if estimates:
        line += (
            f"\nWARNING: {len(estimates)} record(s) have usage_source=estimate; "
            "the run is not provider-grade evidence."
        )
    return line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gnomon-compare")
    parser.add_argument("on_report")
    parser.add_argument("off_report")
    parser.add_argument("--telemetry", help="AXON recall requests.jsonl")
    args = parser.parse_args(argv)

    on = json.loads(Path(args.on_report).read_text(encoding="utf-8"))
    off = json.loads(Path(args.off_report).read_text(encoding="utf-8"))
    print(compare(on, off))
    if args.telemetry:
        lines = Path(args.telemetry).read_text(encoding="utf-8").splitlines()
        records = [json.loads(ln) for ln in lines if ln.strip()]
        print()
        print(telemetry_cost_line(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
