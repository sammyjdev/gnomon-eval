import pytest
from pydantic import ValidationError

from gnomon.domain.chat import ChatCase, ChatResult


def test_chat_case_requires_at_least_one_conversation_turn():
    with pytest.raises(ValidationError):
        ChatCase(
            id="case-1",
            conversation=[],
            tenant={"name": "Clinica Aurora", "tone": "amigavel"},
            expected_tools=[],
            criteria=None,
        )


def test_chat_case_defaults_criteria_to_none():
    case = ChatCase(
        id="case-1",
        conversation=[{"role": "user", "content": "Oi"}],
        tenant={"name": "Clinica Aurora", "tone": "amigavel"},
        expected_tools=["answer_question"],
    )
    assert case.criteria is None


def test_chat_case_defaults_criteria_metric_to_tone_brand():
    case = ChatCase(
        id="case-1",
        conversation=[{"role": "user", "content": "Oi"}],
        tenant={"name": "Clinica Aurora", "tone": "amigavel"},
        expected_tools=["answer_question"],
        criteria="Must sound warm.",
    )
    assert case.criteria_metric == "tone_brand"


def test_chat_result_tool_called_defaults_to_none_for_a_text_only_reply():
    result = ChatResult(
        tool_args={},
        reply_text="Oi! Como posso ajudar?",
        total_tokens=42,
        latency_ms=850.0,
    )
    assert result.tool_called is None
    assert result.reply_text == "Oi! Como posso ajudar?"


def test_chat_result_generation_events_defaults_to_empty_list():
    result = ChatResult(
        reply_text="Oi! Como posso ajudar?",
        total_tokens=42,
        latency_ms=850.0,
    )
    assert result.generation_events == []


def test_chat_result_accepts_generation_events_list_of_dicts():
    events = [{"event_type": "malformed_reply_suppressed"}]
    result = ChatResult(
        reply_text="Oi! Como posso ajudar?",
        total_tokens=42,
        latency_ms=850.0,
        generation_events=events,
    )
    assert result.generation_events == events
