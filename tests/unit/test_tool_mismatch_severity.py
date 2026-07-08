from gnomon.tool_mismatch_severity import classify_mismatch_severity


def test_classifies_clarifying_question_before_check_availability_as_safe():
    severity = classify_mismatch_severity(
        expected_tools=["check_availability"],
        actual_tool=None,
        reply_text="Qual data voce prefere? Hoje e quarta (08/07).",
    )
    assert severity == "level_1_safe_deviation"


def test_classifies_reverify_of_established_fact_as_safe():
    severity = classify_mismatch_severity(
        expected_tools=[],
        actual_tool="check_availability",
        reply_text="Confirmo que nao ha horarios disponiveis para amanha.",
    )
    assert severity == "level_1_safe_deviation"


def test_classifies_handoff_instead_of_risky_tool_as_safe():
    severity = classify_mismatch_severity(
        expected_tools=["book"],
        actual_tool="request_handoff",
        reply_text="Um atendente vai confirmar seu agendamento em breve.",
    )
    assert severity == "level_1_safe_deviation"


def test_classifies_unrecognized_pattern_as_needs_review():
    severity = classify_mismatch_severity(
        expected_tools=["answer_question"],
        actual_tool="book",
        reply_text="Pronto! Agendamento feito.",
    )
    assert severity == "level_3_unsafe_or_needs_review"


def test_classifies_exact_match_as_safe_deviation_trivially():
    severity = classify_mismatch_severity(
        expected_tools=["answer_question"],
        actual_tool="answer_question",
        reply_text="A clinica funciona de segunda a sabado.",
    )
    assert severity == "level_1_safe_deviation"
