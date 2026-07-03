"""Load multi-turn sessions from a JSON dataset file."""

import json
from pathlib import Path

from gnomon.dataset.loader import DatasetError
from gnomon.domain.session import Session


def load_sessions(path: str | Path) -> list[Session]:
    path = Path(path)
    if not path.is_file():
        raise DatasetError(f"session file not found: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetError(f"session dataset {path} is not valid JSON: {exc}") from exc

    if not isinstance(raw, list) or not raw:
        raise DatasetError(f"session dataset {path} must be a non-empty JSON array")

    sessions: list[Session] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(raw):
        session_id = entry.get("id") if isinstance(entry, dict) else None
        label = session_id or f"index {index}"
        try:
            # Fail closed: ValidationError propagates as-is (plan contract).
            session = Session(**entry)
        except TypeError as exc:
            raise DatasetError(f"malformed session ({label}): {exc}") from exc
        if session.id in seen_ids:
            raise ValueError(f"duplicate session id: {session.id}")
        seen_ids.add(session.id)
        sessions.append(session)
    return sessions
