"""Offline capacity screening for candidate panel judges (ADR-0012 #5)."""

import json
import math
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from gnomon.judge.ollama import JudgeProtocolError, parse_v1_judge_response
from gnomon.metrics.names import V1_METRICS


class ProbeVerdict(BaseModel):
    """Verdict for one probe case's raw candidate output against the B4 bar."""

    model_config = ConfigDict(frozen=True)
    case_id: str = Field(min_length=1)
    valid_json: bool
    schema_compliant: bool
    hallucinated_keys: list[str]
    passed: bool
    reason: str | None = None


class ScreeningResult(BaseModel):
    """Fail-closed aggregate over every probe for one candidate model."""

    model_config = ConfigDict(frozen=True)
    candidate: str = Field(min_length=1)
    probes: list[ProbeVerdict]
    known_fail_probes: list[ProbeVerdict] = Field(default_factory=list)
    grounded_threshold: float | None = None
    pass_floor: float | None = None
    tnr: float | None = None
    pass_floor_count: int | None = None
    known_fail_grounded_count: int = 0

    @property
    def passed(self) -> bool:
        return (
            self.grounded_threshold is not None
            and self.pass_floor is not None
            and len(self.known_fail_probes) > 0
            and len(self.probes) > 0
            and all(probe.passed for probe in self.probes)
            and all(probe.passed for probe in self.known_fail_probes)
            and self.known_fail_grounded_count == 0
            and self.pass_floor_count is not None
            and self.pass_floor_count >= 1
        )


def _checked_floor(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a numeric float, got {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
    val_f = float(value)
    if not (0.0 <= val_f <= 1.0):
        raise ValueError(f"{name} must be in [0, 1], got {value!r}")
    return val_f


def _faithfulness(raw_response: str) -> float | None:
    try:
        scores = parse_v1_judge_response(raw_response)
        return scores.scores.get("faithfulness")
    except JudgeProtocolError:
        return None


def screen_probe(case_id: str, raw_response: str) -> ProbeVerdict:
    """Verdict one probe's raw text against the B4 capacity bar."""
    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        return ProbeVerdict(
            case_id=case_id,
            valid_json=False,
            schema_compliant=False,
            hallucinated_keys=[],
            passed=False,
            reason=f"not valid JSON: {exc}",
        )

    if not isinstance(parsed, dict):
        return ProbeVerdict(
            case_id=case_id,
            valid_json=True,
            schema_compliant=False,
            hallucinated_keys=[],
            passed=False,
            reason="response is not a JSON object",
        )

    hallucinated_keys = sorted(set(parsed) - set(V1_METRICS))
    missing = [metric for metric in V1_METRICS if metric not in parsed]
    out_of_range = [
        metric
        for metric in V1_METRICS
        if metric in parsed
        and not (
            isinstance(parsed[metric], (int, float))
            and not isinstance(parsed[metric], bool)
            and 0.0 <= float(parsed[metric]) <= 1.0
        )
    ]
    schema_compliant = not missing and not out_of_range
    passed = schema_compliant and not hallucinated_keys
    reason = None
    if missing:
        reason = f"missing required keys: {missing}"
    elif out_of_range:
        reason = f"keys not a float in [0, 1]: {out_of_range}"
    elif hallucinated_keys:
        reason = f"hallucinated keys: {hallucinated_keys}"

    return ProbeVerdict(
        case_id=case_id,
        valid_json=True,
        schema_compliant=schema_compliant,
        hallucinated_keys=hallucinated_keys,
        passed=passed,
        reason=reason,
    )


def screen_candidate(
    candidate: str,
    probes: dict[str, str],
    *,
    known_fail_probes: dict[str, str] | None = None,
    grounded_threshold: float | None = None,
    pass_floor: float | None = None,
) -> ScreeningResult:
    """Screen every raw probe response and aggregate its capacity verdict."""
    checked_grounded = _checked_floor("grounded_threshold", grounded_threshold)
    checked_floor = _checked_floor("pass_floor", pass_floor)

    pass_verdicts = [screen_probe(case_id, raw) for case_id, raw in probes.items()]

    if known_fail_probes is not None:
        kf_verdicts = [screen_probe(case_id, raw) for case_id, raw in known_fail_probes.items()]
    else:
        kf_verdicts = []

    known_fail_grounded_count = 0
    if checked_grounded is not None and known_fail_probes:
        for verdict in kf_verdicts:
            if verdict.passed:
                raw = known_fail_probes[verdict.case_id]
                f = _faithfulness(raw)
                if f is not None and f >= checked_grounded:
                    known_fail_grounded_count += 1

    known_fail_count = len(kf_verdicts)
    if checked_grounded is not None and known_fail_count > 0:
        tnr = (known_fail_count - known_fail_grounded_count) / known_fail_count
    else:
        tnr = None

    if checked_floor is not None:
        pass_floor_count = 0
        for verdict in pass_verdicts:
            if verdict.passed:
                raw = probes[verdict.case_id]
                f = _faithfulness(raw)
                if f is not None and f >= checked_floor:
                    pass_floor_count += 1
    else:
        pass_floor_count = None

    return ScreeningResult(
        candidate=candidate,
        probes=pass_verdicts,
        known_fail_probes=kf_verdicts,
        grounded_threshold=checked_grounded,
        pass_floor=checked_floor,
        tnr=tnr,
        pass_floor_count=pass_floor_count,
        known_fail_grounded_count=known_fail_grounded_count,
    )


def write_screening_evidence(result: ScreeningResult, path: str | Path) -> Path:
    """Write a screening result as a JSON evidence artifact and return its path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "candidate": result.candidate,
                "passed": result.passed,
                "grounded_threshold": result.grounded_threshold,
                "pass_floor": result.pass_floor,
                "known_fail_count": len(result.known_fail_probes),
                "tnr": result.tnr,
                "pass_floor_count": result.pass_floor_count,
                "probes": [probe.model_dump() for probe in result.probes],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path
