"""Load owner-labeled verdict files for alignment reporting."""

import json
from pathlib import Path

from pydantic import ValidationError

from gnomon.dataset.loader import DatasetError
from gnomon.domain.labels import LabeledItem


class LabelError(DatasetError):
    """Labeled-verdict file missing, malformed or inconsistent (JA-09)."""


def load_labels(*paths: str | Path) -> list[LabeledItem]:
    """Load labels in path and file order, rejecting incomplete input."""
    if not paths:
        raise LabelError("at least one label file is required")

    items: list[LabeledItem] = []
    seen: dict[tuple[str, ...], str] = {}
    real_rubric: tuple[str, str] | None = None
    for input_path in paths:
        path = Path(input_path)
        if not path.is_file():
            raise LabelError(f"label file not found: {path}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise LabelError(f"label file {path} is not valid JSON: {exc}") from exc
        if not isinstance(raw, list) or not raw:
            raise LabelError(f"label file {path} must be a non-empty JSON array of items")

        for index, entry in enumerate(raw):
            where = f"label file {path}, item {index}"
            if not isinstance(entry, dict):
                raise LabelError(f"{where}: item is not a JSON object")
            where += f" (case_id={entry.get('case_id')}, arm={entry.get('arm')})"
            try:
                item = LabeledItem.model_validate(entry)
            except ValidationError as exc:
                raise LabelError(f"{where}: {exc}") from exc

            key = (
                (item.case_id, item.arm, item.answer)
                if item.arm_class == "negative"
                else (item.case_id, item.arm)
            )
            if key in seen:
                raise LabelError(f"{where}: duplicate {key} (first at {seen[key]})")
            seen[key] = where

            if item.arm_class == "real":
                if real_rubric is None:
                    real_rubric = (item.rubric_version, where)
                elif item.rubric_version != real_rubric[0]:
                    first, first_where = real_rubric
                    raise LabelError(
                        f"{where}: rubric_version {item.rubric_version!r} differs from "
                        f"{first!r} at {first_where}; mixed rubric versions across real arms "
                        "cannot produce a report"
                    )
            items.append(item)
    return items
