"""Runs ChatEval cases through a target and judge, aggregating into the same
EvalReport shape the RAG and session arms already produce (RF-06/RNF-03),
via the shared aggregate_metric bootstrap-CI helper unchanged.

Generation and judging are two separate passes over `cases`, in that order --
not interleaved case-by-case -- so that judging (the flakier of the two,
routed through a free/paid-provider fallback chain) can never lose completed
generation work (real Anthropic spend) if it blows up. `generations_path`
persists each result to disk as soon as it's generated, before judging
starts at all, so even a total judge-stage failure leaves the generation
work recoverable from that file (2026-07-09 incident: a run with no such
split lost ~70 real generations to one bad case's judge failure)."""

import contextlib
import json
import logging
from collections.abc import Callable

from gnomon.domain.chat import ChatCase, ChatResult
from gnomon.domain.models import CaseCost, EvalReport, MetricResult
from gnomon.metrics.confidence import aggregate_metric

_logger = logging.getLogger(__name__)


@contextlib.contextmanager
def _maybe_open_for_write(path: str | None):
    if path is None:
        yield None
        return
    with open(path, "w", encoding="utf-8") as f:
        yield f


def load_generations(path: str) -> dict[str, ChatResult]:
    """Reads back a `generations_path` JSONL file into {case_id: ChatResult},
    for a later `run_chat_eval(..., pregenerated=...)` re-judge pass that
    spends zero real generation money on the cases it covers."""
    results: dict[str, ChatResult] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            results[row["case_id"]] = ChatResult.model_validate(row["result"])
    return results


def run_chat_eval(
    cases: list[ChatCase],
    target,
    judge,
    *,
    seed: int,
    confidence_level: float = 0.95,
    on_case_scored: Callable[[ChatCase, ChatResult, dict[str, float]], None] | None = None,
    generations_path: str | None = None,
    pregenerated: dict[str, ChatResult] | None = None,
) -> EvalReport:
    per_case_cost: list[CaseCost] = []
    scores_by_metric: dict[str, list[float]] = {}
    generated: list[tuple[ChatCase, ChatResult]] = []
    pregenerated = pregenerated or {}

    with _maybe_open_for_write(generations_path) as generations_file:
        for case in cases:
            result = pregenerated.get(case.id)
            if result is None:
                result = target.run(case)
            per_case_cost.append(
                CaseCost(
                    case_id=case.id,
                    total_tokens=result.total_tokens,
                    latency_ms=result.latency_ms,
                )
            )
            generated.append((case, result))
            if generations_file is not None:
                generations_file.write(
                    json.dumps({"case_id": case.id, "result": result.model_dump()}) + "\n"
                )
                generations_file.flush()

    for case, result in generated:
        try:
            case_scores = judge.score(case, result)
        except Exception as exc:  # noqa: BLE001 - one unscoreable case (judge
            # chain fully exhausted) must not sink the other 200+; generation
            # cost above is already recorded, only the score is lost.
            _logger.warning("judge scoring failed for case %s, skipping: %s", case.id, exc)
            continue
        if on_case_scored is not None:
            on_case_scored(case, result, case_scores)
        for metric_name, value in case_scores.items():
            scores_by_metric.setdefault(metric_name, []).append(value)

    metrics: list[MetricResult] = [
        aggregate_metric(
            metric_name,
            values,
            confidence_level=confidence_level,
            seed=seed,
        )
        for metric_name, values in scores_by_metric.items()
    ]

    return EvalReport(metrics=metrics, per_case_cost=per_case_cost)
