"""Alignment statistics for owner-labeled judge verdicts."""

import math
import random
from collections.abc import Callable, Mapping, Sequence
from statistics import NormalDist

from gnomon.domain.labels import LabeledItem
from gnomon.metrics.confidence import _BOOTSTRAP_RESAMPLES

MIN_BOOTSTRAP_CLASS_ITEMS = 5


class AlignmentError(ValueError):
    """Alignment inputs invalid (JA-10, JA-17); raised before any statistic."""


def _check_confidence_level(confidence_level: float) -> None:
    if not 0.0 < confidence_level < 1.0:
        raise AlignmentError(
            f"confidence_level must be strictly between 0 and 1 (exclusive), got {confidence_level}"
        )


def _validate(
    items: Sequence[LabeledItem], scores: Mapping[str, Sequence[float]], threshold: float
) -> None:
    if (
        not isinstance(threshold, (int, float))
        or isinstance(threshold, bool)
        or not 0.0 <= threshold <= 1.0
    ):
        raise AlignmentError(f"threshold must be a finite number in [0, 1], got {threshold}")
    for judge_id, judge_scores in scores.items():
        if len(judge_scores) != len(items):
            raise AlignmentError(
                f"judge {judge_id!r} has {len(judge_scores)} scores for {len(items)} items"
            )
        for index, score in enumerate(judge_scores):
            if (
                not isinstance(score, (int, float))
                or isinstance(score, bool)
                or not math.isfinite(score)
                or not 0.0 <= score <= 1.0
            ):
                item = items[index]
                raise AlignmentError(
                    f"judge {judge_id!r} score for item {index} ({item.case_id}/{item.arm}) "
                    f"must be a finite number in [0, 1], got {score}"
                )


def _passes(score: float, threshold: float) -> bool:
    return score >= threshold


def _auc(pos_scores: Sequence[float], neg_scores: Sequence[float]) -> float:
    # ponytail: O(n_pass*n_fail) per resample; use midrank Mann-Whitney past a few hundred/class.
    wins = sum(
        1.0 if pos > neg else 0.5 if pos == neg else 0.0 for pos in pos_scores for neg in neg_scores
    )
    return wins / (len(pos_scores) * len(neg_scores))


def _kappa(pos_verdicts: Sequence[bool], neg_verdicts: Sequence[bool]) -> float:
    a = sum(pos_verdicts)
    b = len(pos_verdicts) - a
    c = sum(neg_verdicts)
    d = len(neg_verdicts) - c
    n = a + b + c + d
    expected = (a + b) * (a + c) + (c + d) * (b + d)
    return (n * (a + d) - expected) / (n * n - expected)


def _wilson(k: int, n: int, z: float) -> tuple[float, float]:
    proportion = k / n
    denominator = 1.0 + z * z / n
    center = (proportion + z * z / (2.0 * n)) / denominator
    half_width = (
        z * math.sqrt(proportion * (1.0 - proportion) / n + z * z / (4.0 * n * n)) / denominator
    )
    low, high = max(0.0, center - half_width), min(1.0, center + half_width)
    low = 0.0 if k == 0 else low
    return low, 1.0 if k == n else high


def _bootstrap(
    pos: Sequence[float] | Sequence[bool],
    neg: Sequence[float] | Sequence[bool],
    statistic: Callable[[Sequence, Sequence], float],
    value: float,
    *,
    confidence_level: float,
    seed: int,
) -> tuple[float, float]:
    rng = random.Random(seed)  # noqa: S311 - deterministic bootstrap sampling is not cryptographic.
    boot = []
    for _ in range(_BOOTSTRAP_RESAMPLES):
        sampled_pos = [pos[rng.randrange(len(pos))] for _ in pos]
        sampled_neg = [neg[rng.randrange(len(neg))] for _ in neg]
        boot.append(statistic(sampled_pos, sampled_neg))
    boot.sort()
    alpha = 1.0 - confidence_level
    lo_index = int((alpha / 2.0) * _BOOTSTRAP_RESAMPLES)
    hi_index = int((1.0 - alpha / 2.0) * _BOOTSTRAP_RESAMPLES) - 1
    return min(boot[lo_index], value), max(boot[hi_index], value)


def _stat(
    value: float | None, ci_low: float | None, ci_high: float | None, reason: str | None
) -> dict:
    return {"value": value, "ci_low": ci_low, "ci_high": ci_high, "reason": reason}


def _absent_reason(n_pass: int, n_fail: int) -> str:
    return (
        "no owner pass labels in this stratum"
        if n_pass == 0
        else "no owner fail labels in this stratum"
    )


def _small_class_reason(n_pass: int, n_fail: int) -> str:
    return (
        f"bootstrap needs at least 5 items per owner label class, got pass={n_pass}, fail={n_fail}"
    )


def _stratum(
    pos_scores: Sequence[float],
    neg_scores: Sequence[float],
    threshold: float,
    z: float,
    confidence_level: float,
    seed: int,
) -> dict:
    n_pass, n_fail = len(pos_scores), len(neg_scores)
    if not n_pass or not n_fail:
        reason = _absent_reason(n_pass, n_fail)
        auc = _stat(None, None, None, reason)
        kappa = _stat(None, None, None, reason)
    else:
        auc_value = _auc(pos_scores, neg_scores)
        pos_verdicts = [_passes(score, threshold) for score in pos_scores]
        neg_verdicts = [_passes(score, threshold) for score in neg_scores]
        kappa_value = _kappa(pos_verdicts, neg_verdicts)
        if min(n_pass, n_fail) < MIN_BOOTSTRAP_CLASS_ITEMS:
            reason = _small_class_reason(n_pass, n_fail)
            auc = _stat(auc_value, None, None, reason)
            kappa = _stat(kappa_value, None, None, reason)
        else:
            auc_low, auc_high = _bootstrap(
                pos_scores,
                neg_scores,
                _auc,
                auc_value,
                confidence_level=confidence_level,
                seed=seed,
            )
            kappa_low, kappa_high = _bootstrap(
                pos_verdicts,
                neg_verdicts,
                _kappa,
                kappa_value,
                confidence_level=confidence_level,
                seed=seed,
            )
            auc = _stat(auc_value, auc_low, auc_high, None)
            kappa = _stat(kappa_value, kappa_low, kappa_high, None)

    if n_pass:
        pass_count = sum(_passes(score, threshold) for score in pos_scores)
        tpr_value = pass_count / n_pass
        tpr_low, tpr_high = _wilson(pass_count, n_pass, z)
        tpr = _stat(tpr_value, tpr_low, tpr_high, None)
    else:
        tpr = _stat(None, None, None, _absent_reason(n_pass, n_fail))
    if n_fail:
        fail_count = sum(not _passes(score, threshold) for score in neg_scores)
        tnr_value = fail_count / n_fail
        tnr_low, tnr_high = _wilson(fail_count, n_fail, z)
        tnr = _stat(tnr_value, tnr_low, tnr_high, None)
    else:
        tnr = _stat(None, None, None, _absent_reason(n_pass, n_fail))
    return {
        "n_owner_pass": n_pass,
        "n_owner_fail": n_fail,
        "auc": auc,
        "tpr": tpr,
        "tnr": tnr,
        "kappa": kappa,
    }


def compute_alignment(
    items: Sequence[LabeledItem],
    scores: Mapping[str, Sequence[float]],
    *,
    threshold: float,
    confidence_level: float,
    seed: int,
) -> dict:
    """Compute per-judge owner-label alignment statistics."""
    _check_confidence_level(confidence_level)
    _validate(items, scores, threshold)
    z = NormalDist().inv_cdf(1.0 - (1.0 - confidence_level) / 2.0)
    arms = sorted({item.arm for item in items})
    real_indexes = [index for index, item in enumerate(items) if item.arm_class == "real"]
    judges = []
    for judge_id in sorted(scores):
        judge_scores = scores[judge_id]

        def stratum(indexes: Sequence[int], judge_scores: Sequence[float] = judge_scores) -> dict:
            pos = [judge_scores[index] for index in indexes if items[index].verdict == "pass"]
            neg = [judge_scores[index] for index in indexes if items[index].verdict == "fail"]
            return _stratum(pos, neg, threshold, z, confidence_level, seed)

        judge_arms = [
            {"arm": arm, **stratum([i for i, item in enumerate(items) if item.arm == arm])}
            for arm in arms
        ]
        judges.append({"judge_id": judge_id, "real": stratum(real_indexes), "arms": judge_arms})
    return {
        "threshold": threshold,
        "confidence_level": confidence_level,
        "seed": seed,
        "rubric_versions": sorted({item.rubric_version for item in items}),
        "judges": judges,
    }


def disagreement_list(
    items: Sequence[LabeledItem], scores: Mapping[str, Sequence[float]], *, threshold: float
) -> list[dict]:
    """List real-arm verdict conflicts for each judge."""
    _validate(items, scores, threshold)
    result = []
    for judge_id in sorted(scores):
        conflicts = []
        for item, score in zip(items, scores[judge_id], strict=True):
            judge_verdict = "pass" if _passes(score, threshold) else "fail"
            if item.arm_class == "real" and judge_verdict != item.verdict:
                conflicts.append(
                    {
                        "case_id": item.case_id,
                        "arm": item.arm,
                        "judge_score": score,
                        "judge_verdict": judge_verdict,
                        "owner_verdict": item.verdict,
                        "owner_critique": item.critique,
                    }
                )
        result.append(
            {
                "judge_id": judge_id,
                "items": sorted(conflicts, key=lambda item: (item["arm"], item["case_id"])),
            }
        )
    return result


def self_agreement(
    first: Sequence[LabeledItem],
    second: Sequence[LabeledItem],
    *,
    confidence_level: float,
    seed: int,
) -> dict:
    """Compute owner self-consistency across two label sets."""
    _check_confidence_level(confidence_level)
    second_real = {(item.case_id, item.arm): item for item in second if item.arm_class == "real"}
    pos: list[bool] = []
    neg: list[bool] = []
    for item in first:
        if item.arm_class != "real":
            continue
        paired = second_real.get((item.case_id, item.arm))
        if paired is None:
            continue
        if item.answer != paired.answer:
            raise AlignmentError(f"joined pair ({item.case_id}, {item.arm}) differs in answer")
        if item.contexts != paired.contexts:
            raise AlignmentError(f"joined pair ({item.case_id}, {item.arm}) differs in contexts")
        (pos if item.verdict == "pass" else neg).append(paired.verdict == "pass")

    n_pairs = len(pos) + len(neg)
    if n_pairs < 2:
        raise AlignmentError(
            f"self-agreement needs at least 2 joined real-arm pairs, got {n_pairs}"
        )
    counts = {
        "first_pass_second_pass": sum(pos),
        "first_pass_second_fail": len(pos) - sum(pos),
        "first_fail_second_pass": sum(neg),
        "first_fail_second_fail": len(neg) - sum(neg),
    }
    if not pos or not neg:
        kappa = _stat(None, None, None, _absent_reason(len(pos), len(neg)))
    else:
        value = _kappa(pos, neg)
        if min(len(pos), len(neg)) < MIN_BOOTSTRAP_CLASS_ITEMS:
            reason = _small_class_reason(len(pos), len(neg))
            kappa = _stat(value, None, None, reason)
        else:
            low, high = _bootstrap(
                pos, neg, _kappa, value, confidence_level=confidence_level, seed=seed
            )
            kappa = _stat(value, low, high, None)
    return {
        "confidence_level": confidence_level,
        "seed": seed,
        "n_pairs": n_pairs,
        "counts": counts,
        "kappa": kappa,
    }
