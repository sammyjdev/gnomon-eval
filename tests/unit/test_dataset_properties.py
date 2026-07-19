import json
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from gnomon.dataset.chat_loader import load_chat_cases
from gnomon.dataset.loader import DatasetError, load_dataset
from gnomon.dataset.session_loader import load_sessions
from gnomon.domain.chat import ChatCase
from gnomon.domain.models import EvalCase
from gnomon.domain.session import Session

LOADERS = [
    pytest.param(load_dataset, EvalCase, (DatasetError,), "dataset.json", id="dataset"),
    pytest.param(
        load_chat_cases,
        ChatCase,
        (DatasetError, ValueError),
        "chat.json",
        id="chat",
    ),
    pytest.param(
        load_sessions,
        Session,
        (DatasetError, ValueError),
        "sessions.json",
        id="sessions",
    ),
]

JSON_SCALAR = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(),
)
WRONG_TOP_LEVEL = st.one_of(
    JSON_SCALAR,
    st.dictionaries(st.text(max_size=20), JSON_SCALAR, max_size=5),
    st.just([]),
)
MALFORMED_ENTRY = st.one_of(
    st.none(),
    st.integers(),
    st.text(),
    st.builds(lambda case_id: {"id": case_id}, st.integers()),
)


def _is_valid_json(text: str) -> bool:
    try:
        json.loads(text)
    except Exception:
        return False
    return True


MALFORMED_JSON = st.text().filter(lambda text: bool(text) and not _is_valid_json(text))


@pytest.mark.parametrize(("loader", "model_type", "allowed_errors", "filename"), LOADERS)
@settings(deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(malformed_text=MALFORMED_JSON)
def test_malformed_json_fails_closed(
    loader, model_type, allowed_errors, filename, malformed_text, tmp_path: Path
):
    del model_type, allowed_errors
    path = tmp_path / filename
    path.write_text(malformed_text, encoding="utf-8")

    try:
        loader(path)
    except DatasetError as exc:
        assert "not valid JSON" in str(exc)
    except Exception as exc:
        raise AssertionError(
            f"loader raised unrelated exception {type(exc).__name__}: {exc}"
        ) from exc
    else:
        raise AssertionError("loader accepted malformed JSON")


@pytest.mark.parametrize(("loader", "model_type", "allowed_errors", "filename"), LOADERS)
@settings(deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(payload=WRONG_TOP_LEVEL)
def test_wrong_top_level_shape_fails_closed(
    loader, model_type, allowed_errors, filename, payload, tmp_path: Path
):
    del model_type, allowed_errors
    path = tmp_path / filename
    path.write_text(json.dumps(payload), encoding="utf-8")

    try:
        loader(path)
    except DatasetError:
        pass
    except Exception as exc:
        raise AssertionError(
            f"loader raised unrelated exception {type(exc).__name__}: {exc}"
        ) from exc
    else:
        raise AssertionError("loader accepted an empty or non-list payload")


@pytest.mark.parametrize(("loader", "model_type", "allowed_errors", "filename"), LOADERS)
@settings(deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(entry=MALFORMED_ENTRY)
def test_malformed_entries_never_raise_unrelated_exceptions(
    loader, model_type, allowed_errors, filename, entry, tmp_path: Path
):
    path = tmp_path / filename
    path.write_text(json.dumps([entry]), encoding="utf-8")

    try:
        result = loader(path)
    except allowed_errors:
        return
    except Exception as exc:
        raise AssertionError(
            f"loader raised unrelated exception {type(exc).__name__}: {exc}"
        ) from exc

    assert isinstance(result, list)
    assert all(isinstance(item, model_type) for item in result)


@settings(deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(case_id=st.text(min_size=1, max_size=50))
def test_load_chat_cases_rejects_duplicate_ids(case_id: str, tmp_path: Path):
    entry = {
        "id": case_id,
        "conversation": [{"role": "user", "content": "Hello"}],
        "tenant": {"name": "Clinic", "tone": "friendly"},
        "expected_tools": [],
    }
    path = tmp_path / "chat.json"
    path.write_text(json.dumps([entry, entry]), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate chat case id"):
        load_chat_cases(path)


@settings(deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(session_id=st.text(min_size=1, max_size=50))
def test_load_sessions_rejects_duplicate_ids(session_id: str, tmp_path: Path):
    entry = {
        "id": session_id,
        "topic": "Topic",
        "turns": ["First", "Second"],
    }
    path = tmp_path / "sessions.json"
    path.write_text(json.dumps([entry, entry]), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate session id"):
        load_sessions(path)
