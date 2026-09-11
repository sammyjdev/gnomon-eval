"""Run one panel arm and write its panel report JSON.

gnomon has no panel CLI command (deferred in the judge-alignment spec), so this
is the committed driver behind the alignment draw (docs/panel/alignment.md,
section 3). The report carries `responses`, which `gnomon align --export` reads.

    python scripts/run_panel_arm.py -c config/alignment-on.toml --arm on --out PATH
"""

import argparse
import json
import sys
from pathlib import Path

from gnomon.cli import build_judge, build_target
from gnomon.config.run_config import RunConfig
from gnomon.dataset.loader import load_dataset
from gnomon.reporting.panel_report import panel_to_dict
from gnomon.runner.panel_runner import PanelMember, run_panel_eval


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one panel arm.")
    parser.add_argument("-c", "--config", required=True, help="RunConfig TOML with a [panel]")
    parser.add_argument("--arm", required=True, help="arm name recorded in the output")
    parser.add_argument("--out", required=True, help="output JSON path (never overwritten)")
    args = parser.parse_args(argv)

    out = Path(args.out)
    if out.exists():
        sys.exit(f"refusing to overwrite {out}: it holds a scored run")
    cfg = RunConfig.from_file(args.config)
    if cfg.panel is None:
        sys.exit(f"{args.config} has no [panel]")

    # judge_id = family, the same identity `gnomon align` uses for panel members.
    members = [PanelMember(j.family, j.family, build_judge(j)) for j in cfg.panel.judges]
    cases = load_dataset(cfg.dataset_path)
    report = run_panel_eval(
        cases=cases, target=build_target(cfg.target), members=members, config=cfg.eval
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"arm": args.arm, "n_cases": len(cases), "panel": panel_to_dict(report)}
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
