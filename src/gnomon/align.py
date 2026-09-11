"""CLI support for comparing judge scores with owner labels."""

import argparse
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path

from gnomon.cli import build_judge
from gnomon.config.run_config import PanelConfig, RunConfig
from gnomon.dataset.labels import LabelError, load_labels
from gnomon.dataset.loader import DatasetError, load_dataset
from gnomon.domain.labels import NEGATIVE_PREFIX, PERTURBATION_PREFIX, LabeledItem
from gnomon.domain.models import EvalCase, RagResponse
from gnomon.judge.perturbation import known_fail_perturbations
from gnomon.metrics.alignment import (
    AlignmentError,
    compute_alignment,
    disagreement_list,
    self_agreement,
)
from gnomon.runner.panel_runner import PanelMember

FAITHFULNESS = "faithfulness"


class _UsageError(ValueError):
    """Invalid align command line."""


class TemplateError(ValueError):
    """Invalid report input or unsafe template output."""


def _parse_arm_reports(tokens: Sequence[str]) -> list[tuple[str, str]]:
    reports = []
    arms = set()
    for token in tokens:
        if "=" not in token:
            raise _UsageError(f"export report must be ARM=PATH, got {token!r}")
        arm, path = token.split("=", 1)
        if not arm or not path:
            raise _UsageError(f"export report must be ARM=PATH, got {token!r}")
        if arm in arms:
            raise _UsageError(f"duplicate export arm {arm!r}")
        if arm.startswith((PERTURBATION_PREFIX, NEGATIVE_PREFIX)):
            raise _UsageError(f"export arm {arm!r} must be a real arm")
        arms.add(arm)
        reports.append((arm, path))
    if not reports:
        raise _UsageError("--export requires at least one ARM=REPORT_PATH")
    return reports


def _report_responses(document: object, path: str) -> list[dict]:
    responses = None
    if isinstance(document, dict):
        responses = document.get("responses")
        if responses is None and isinstance(document.get("panel"), dict):
            responses = document["panel"].get("responses")
    if not isinstance(responses, list) or not responses:
        raise TemplateError(f"report {path} has no non-empty responses list")
    for index, response in enumerate(responses):
        if not isinstance(response, dict):
            raise TemplateError(f"report {path}, response {index} is not an object")
        if not isinstance(response.get("case_id"), str) or not response["case_id"]:
            raise TemplateError(f"report {path}, response {index} has no case_id")
        if not isinstance(response.get("answer"), str):
            raise TemplateError(f"report {path}, response {index} has no answer")
        if not isinstance(response.get("contexts"), list):
            raise TemplateError(f"report {path}, response {index} has no contexts")
    return responses


def _todo_items(
    arm_responses: Sequence[tuple[str, Sequence[dict]]],
    cases: Sequence[EvalCase],
    *,
    dataset_path: str,
) -> list[dict]:
    by_id = {case.id: case for case in cases}
    seen = set()
    items = []
    for arm, responses in arm_responses:
        for response in responses:
            case_id = response["case_id"]
            case = by_id.get(case_id)
            if case is None:
                raise TemplateError(f"case {case_id!r} is not in dataset {dataset_path}")
            key = (case_id, arm)
            if key in seen:
                raise TemplateError(f"duplicate response for {case_id}/{arm}")
            seen.add(key)
            items.append(
                {
                    "case_id": case_id,
                    "arm": arm,
                    "answer": response["answer"],
                    "contexts": response["contexts"],
                    "verdict": None,
                    "critique": "",
                    "rubric_version": "",
                    "question": case.question,
                }
            )
    return items


def _perturbation_items(cases: Sequence[EvalCase]) -> list[dict]:
    return [
        {
            "case_id": case.id,
            "arm": f"{PERTURBATION_PREFIX}{kind}",
            "answer": answer,
            "contexts": list(case.expected_contexts),
            "question": case.question,
            "verdict": "fail",
            "critique": f"known-fail perturbation: {kind}",
            "rubric_version": "construction",
        }
        for case in cases
        for kind, answer in known_fail_perturbations(case)
    ]


def export_templates(
    cases: Sequence[EvalCase], arm_reports: Sequence[tuple[str, str]], out_dir: str | Path
) -> None:
    parsed = []
    for arm, path in arm_reports:
        report_path = Path(path)
        if not report_path.is_file():
            raise TemplateError(f"report file not found: {report_path}")
        try:
            document = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise TemplateError(f"report {report_path} is not valid JSON: {exc}") from exc
        parsed.append((arm, _report_responses(document, str(report_path))))
    todo = []
    for (arm, responses), (_, path) in zip(parsed, arm_reports, strict=True):
        try:
            todo.extend(_todo_items([(arm, responses)], cases, dataset_path="configured dataset"))
        except TemplateError as exc:
            raise TemplateError(f"report {path}: {exc}") from exc
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    todo_path = output / "labels.todo.json"
    perturbations_path = output / "perturbations.json"
    for path in (todo_path, perturbations_path):
        if path.exists():
            raise TemplateError(f"refusing to overwrite {path}")
    with todo_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(todo, indent=2) + "\n")
    with perturbations_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(_perturbation_items(cases), indent=2) + "\n")


def _build_members(panel: PanelConfig) -> list[PanelMember]:
    return [PanelMember(judge.family, judge.family, build_judge(judge)) for judge in panel.judges]


def _resolve_cases(
    items: Sequence[LabeledItem], cases: Sequence[EvalCase], *, dataset_path: str
) -> list[EvalCase]:
    by_id = {case.id: case for case in cases}
    resolved = []
    for item in items:
        case = by_id.get(item.case_id)
        if case is None:
            raise AlignmentError(
                f"label {item.case_id}/{item.arm} is not in dataset {dataset_path}"
            )
        if item.question is not None and item.question != case.question:
            raise AlignmentError(f"label {item.case_id}/{item.arm} question differs from dataset")
        resolved.append(case)
    return resolved


def collect_scores(
    items: Sequence[LabeledItem],
    cases: Sequence[EvalCase],
    members: Sequence[PanelMember],
    *,
    seed: int,
    judge_runs: int,
) -> tuple[dict[str, list[float]], list[dict]]:
    scores = {member.judge_id: [] for member in members}
    entries = []
    for index, (item, case) in enumerate(zip(items, cases, strict=True)):
        response = RagResponse(
            answer=item.answer,
            contexts=list(item.contexts),
            total_tokens=0,
            latency_ms=0.0,
        )
        for member in sorted(members, key=lambda member: member.judge_id):
            try:
                score = (
                    sum(
                        member.judge.score(case, response, seed=seed, run=run).scores[FAITHFULNESS]
                        for run in range(judge_runs)
                    )
                    / judge_runs
                )
            except Exception as exc:  # noqa: BLE001 - judge providers expose arbitrary failures.
                raise AlignmentError(
                    f"judge {member.judge_id} failed on {item.case_id}/{item.arm}: {exc}"
                ) from exc
            scores[member.judge_id].append(score)
            entries.append(
                {
                    "item": index,
                    "case_id": item.case_id,
                    "arm": item.arm,
                    "judge_id": member.judge_id,
                    "score": score,
                }
            )
    return scores, entries


def _alignment_document(
    items: Sequence[LabeledItem],
    judge_scores: dict[str, list[float]],
    score_entries: list[dict],
    *,
    threshold: float,
    confidence_level: float,
    seed: int,
) -> dict:
    document = compute_alignment(
        items,
        judge_scores,
        threshold=threshold,
        confidence_level=confidence_level,
        seed=seed,
    )
    document["disagreements"] = disagreement_list(items, judge_scores, threshold=threshold)
    document["scores"] = score_entries
    return document


def _format_stat(stat: dict) -> str:
    if stat["value"] is None:
        return f"null ({stat['reason']})"
    if stat["ci_low"] is None or stat["ci_high"] is None:
        return f"{stat['value']} ({stat['reason']})"
    return f"{stat['value']} [{stat['ci_low']}, {stat['ci_high']}]"


def _align_to_text(document: dict) -> str:
    lines = []
    for judge in document["judges"]:
        for name, stratum in [
            ("real", judge["real"]),
            *[(arm["arm"], arm) for arm in judge["arms"]],
        ]:
            stats = ", ".join(
                f"{metric}={_format_stat(stratum[metric])}"
                for metric in ("auc", "tpr", "tnr", "kappa")
            )
            lines.append(
                f"{judge['judge_id']} {name}: n_owner_pass={stratum['n_owner_pass']}, "
                f"n_owner_fail={stratum['n_owner_fail']}, {stats}"
            )
    lines.append(f"disagreements={sum(len(entry['items']) for entry in document['disagreements'])}")
    return "\n".join(lines)


def _run_scoring(cfg: RunConfig, args: argparse.Namespace) -> int:
    if not args.labels:
        raise _UsageError("scoring requires at least one --labels")
    if args.threshold is None:
        raise _UsageError("scoring requires --threshold")
    if not math.isfinite(args.threshold) or not 0.0 <= args.threshold <= 1.0:
        raise _UsageError("threshold must be a finite number in [0, 1]")
    if cfg.panel is None:
        raise AlignmentError("align requires a [panel] section")
    if cfg.eval.seed is None:
        raise AlignmentError("align requires eval.seed")
    items = load_labels(*args.labels)
    cases = _resolve_cases(items, load_dataset(cfg.dataset_path), dataset_path=cfg.dataset_path)
    members = _build_members(cfg.panel)
    count = len(items) * len(members) * cfg.eval.judge_runs
    print(
        f"declared judge calls: {count} ({len(items)} items x {len(members)} members x "
        f"{cfg.eval.judge_runs} runs)",
        file=sys.stderr,
    )
    scores, entries = collect_scores(
        items,
        cases,
        members,
        seed=cfg.eval.seed,
        judge_runs=cfg.eval.judge_runs,
    )
    document = _alignment_document(
        items,
        scores,
        entries,
        threshold=args.threshold,
        confidence_level=cfg.eval.confidence_level,
        seed=cfg.eval.seed,
    )
    print(json.dumps(document, indent=2) if args.json else _align_to_text(document))
    return 0


def _run_export(cfg: RunConfig, args: argparse.Namespace) -> int:
    if args.labels or args.threshold is not None:
        raise _UsageError("--export cannot be combined with --labels or --threshold")
    out_dir, *tokens = args.export
    arm_reports = _parse_arm_reports(tokens)
    export_templates(load_dataset(cfg.dataset_path), arm_reports, out_dir)
    return 0


def _run_self_agreement(cfg: RunConfig, args: argparse.Namespace) -> int:
    if args.labels or args.threshold is not None:
        raise _UsageError("--self-agreement cannot be combined with --labels or --threshold")
    if cfg.eval.seed is None:
        raise AlignmentError("align requires eval.seed")
    first, second = args.self_agreement
    result = self_agreement(
        load_labels(first),
        load_labels(second),
        confidence_level=cfg.eval.confidence_level,
        seed=cfg.eval.seed,
    )
    print(json.dumps(result, indent=2))
    return 0


def align_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gnomon align", description="Measure judge alignment.")
    parser.add_argument("-c", "--config", help="path to the run config TOML")
    parser.add_argument("--labels", action="append", metavar="PATH")
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--export", nargs="+", metavar="OUT_DIR ARM=REPORT_PATH")
    parser.add_argument("--self-agreement", nargs=2, metavar=("FIRST", "SECOND"))
    args = parser.parse_args(argv)
    try:
        if args.config is None:
            raise _UsageError("-c/--config is required")
        cfg = RunConfig.from_file(args.config)
        if args.export and args.self_agreement:
            raise _UsageError("--export and --self-agreement are mutually exclusive")
        if args.export:
            return _run_export(cfg, args)
        if args.self_agreement:
            return _run_self_agreement(cfg, args)
        return _run_scoring(cfg, args)
    except _UsageError as exc:
        print(exc, file=sys.stderr)
        return 2
    except (DatasetError, LabelError, AlignmentError, TemplateError) as exc:
        print(exc, file=sys.stderr)
        return 1
