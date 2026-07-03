import json

import pytest
from pydantic import ValidationError

from gnomon.dataset.loader import DatasetError
from gnomon.dataset.session_loader import load_sessions
from gnomon.domain.session import Session, TurnCost


def _write(tmp_path, payload):
    path = tmp_path / "sessions.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_session_holds_id_topic_and_turns_and_is_frozen():
    session = Session(
        id="session-1",
        topic="Latency trade-offs",
        turns=["What changed?", "We removed the extra layer."],
    )
    assert session.id == "session-1"
    assert session.topic == "Latency trade-offs"
    assert session.turns == ["What changed?", "We removed the extra layer."]

    with pytest.raises(ValidationError):
        session.topic = "Another topic"


def test_turn_cost_holds_usage_fields_and_is_frozen():
    cost = TurnCost(
        session_id="session-1",
        turn=0,
        arm="axon",
        prompt_tokens=10,
        completion_tokens=12,
        total_tokens=22,
        latency_ms=42.5,
        usage_source="provider",
    )
    assert cost.session_id == "session-1"
    assert cost.turn == 0
    assert cost.arm == "axon"
    assert cost.prompt_tokens == 10
    assert cost.completion_tokens == 12
    assert cost.total_tokens == 22
    assert cost.latency_ms == 42.5
    assert cost.usage_source == "provider"

    with pytest.raises(ValidationError):
        cost.turn = 1


def test_session_rejects_fewer_than_two_turns():
    with pytest.raises(ValidationError):
        Session(id="session-1", topic="Topic", turns=["Only one"])


def test_session_rejects_empty_turn_string():
    with pytest.raises(ValidationError):
        Session(id="session-1", topic="Topic", turns=["First", ""])


def test_load_sessions_roundtrip(tmp_path):
    path = _write(
        tmp_path,
        [
            {
                "id": "session-1",
                "topic": "Topic",
                "turns": ["First", "Second"],
            }
        ],
    )

    sessions = load_sessions(path)

    assert len(sessions) == 1
    assert sessions[0].id == "session-1"
    assert sessions[0].topic == "Topic"
    assert sessions[0].turns == ["First", "Second"]


def test_turn_cost_rejects_negative_token_counts():
    with pytest.raises(ValidationError):
        TurnCost(
            session_id="session-1",
            turn=0,
            arm="axon",
            prompt_tokens=-1,
            completion_tokens=0,
            total_tokens=0,
            latency_ms=0.0,
            usage_source="provider",
        )


def test_turn_cost_rejects_unknown_arm():
    with pytest.raises(ValidationError):
        TurnCost(
            session_id="session-1",
            turn=0,
            arm="hybrid",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            latency_ms=0.0,
            usage_source="provider",
        )


def test_load_sessions_rejects_missing_file(tmp_path):
    with pytest.raises(DatasetError):
        load_sessions(tmp_path / "absent.json")


def test_load_sessions_rejects_empty_array(tmp_path):
    path = _write(tmp_path, [])

    with pytest.raises(DatasetError):
        load_sessions(path)


def test_load_sessions_labels_malformed_entry(tmp_path):
    path = _write(tmp_path, ["not-a-session"])

    with pytest.raises(DatasetError) as exc:
        load_sessions(path)

    assert "index 0" in str(exc.value)


def test_load_sessions_rejects_duplicate_ids(tmp_path):
    path = _write(
        tmp_path,
        [
            {"id": "session-1", "topic": "Topic A", "turns": ["First", "Second"]},
            {"id": "session-1", "topic": "Topic B", "turns": ["Third", "Fourth"]},
        ],
    )

    with pytest.raises(ValueError) as exc:
        load_sessions(path)

    assert "session-1" in str(exc.value)
