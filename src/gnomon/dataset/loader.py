"""Load the versioned evaluation dataset from a file (RF-01).

The dataset is the source of truth and lives next to the code, not in an
external store. Loading fails closed (VAL-01): a missing file, an empty
dataset or a malformed case stops the run with an error that names the
offending case. The harness never evaluates partially in silence.
"""

import json
from pathlib import Path

from pydantic import ValidationError

from gnomon.domain.models import EvalCase


class DatasetError(Exception):
    """Dataset missing, empty or malformed (VAL-01)."""


def load_dataset(path: str | Path) -> list[EvalCase]:
    path = Path(path)
    if not path.is_file():
        raise DatasetError(f"dataset file not found: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetError(f"dataset {path} is not valid JSON: {exc}") from exc

    if not isinstance(raw, list) or not raw:
        raise DatasetError(f"dataset {path} must be a non-empty JSON array of cases")

    cases: list[EvalCase] = []
    for index, entry in enumerate(raw):
        case_id = entry.get("id") if isinstance(entry, dict) else None
        label = case_id or f"index {index}"
        try:
            cases.append(EvalCase(**entry))
        except (ValidationError, TypeError) as exc:
            raise DatasetError(f"malformed case ({label}): {exc}") from exc
    return cases
