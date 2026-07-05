"""Load ChatEval cases from a JSON dataset file (mirrors session_loader.py)."""

import json
from pathlib import Path

from gnomon.dataset.loader import DatasetError
from gnomon.domain.chat import ChatCase


def load_chat_cases(path: str | Path) -> list[ChatCase]:
    path = Path(path)
    if not path.is_file():
        raise DatasetError(f"chat dataset not found: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetError(f"chat dataset {path} is not valid JSON: {exc}") from exc

    if not isinstance(raw, list) or not raw:
        raise DatasetError(f"chat dataset {path} must be a non-empty JSON array")

    cases: list[ChatCase] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(raw):
        case_id = entry.get("id") if isinstance(entry, dict) else None
        label = case_id or f"index {index}"
        try:
            case = ChatCase(**entry)
        except TypeError as exc:
            raise DatasetError(f"malformed chat case ({label}): {exc}") from exc
        if case.id in seen_ids:
            raise ValueError(f"duplicate chat case id: {case.id}")
        seen_ids.add(case.id)
        cases.append(case)
    return cases
