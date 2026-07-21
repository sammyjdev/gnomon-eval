"""Offline capacity screening for candidate panel judges (ADR-0012 #5)."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

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

    @property
    def passed(self) -> bool:
        return len(self.probes) > 0 and all(probe.passed for probe in self.probes)


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


def screen_candidate(candidate: str, probes: dict[str, str]) -> ScreeningResult:
    """Screen every raw probe response and aggregate its capacity verdict."""
    return ScreeningResult(
        candidate=candidate,
        probes=[screen_probe(case_id, raw_response) for case_id, raw_response in probes.items()],
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
                "probes": [probe.model_dump() for probe in result.probes],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path
