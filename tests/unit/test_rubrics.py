from gnomon.judge.rubrics import EVALUATION_STEPS


def test_has_steps_for_both_geval_driven_criteria_metrics():
    # tool_selection_accuracy is scored by ToolCorrectnessMetric, not GEval
    # -- only these two go through GEval's evaluation_steps.
    assert set(EVALUATION_STEPS) == {"hallucination", "tone_brand"}


def test_hallucination_steps_treat_an_absent_fact_as_unknown_not_false():
    # Root cause of a real scoring bug (2026-07-09): a reply correctly
    # stating "I don't have that information" for an unconfigured fact was
    # scored 0.0 by an auto-generated step that treated the honest refusal
    # as a violation.
    steps_text = " ".join(EVALUATION_STEPS["hallucination"]).lower()
    assert "unknown" in steps_text or "absent" in steps_text


def test_hallucination_steps_reference_context_as_the_source_of_truth():
    # The judge previously only saw the conversation and the reply -- never
    # the tenant's actual configured data -- so it had no way to verify a
    # claim like "the reply must state the configured price".
    steps_text = " ".join(EVALUATION_STEPS["hallucination"]).lower()
    assert "context" in steps_text


def test_no_rubric_asks_the_judge_to_evaluate_output_format():
    # Root cause of the "does not provide a clear JSON output" false
    # rejection (2026-07-09): GEval's auto-generated steps padded a
    # 2-requirement criteria to a forced 3-4, and the padding hallucinated
    # a JSON-format requirement that exists nowhere in this product (a
    # WhatsApp bot that always replies in natural Portuguese text).
    for metric, steps in EVALUATION_STEPS.items():
        steps_text = " ".join(steps).lower()
        assert "json" in steps_text, f"{metric} rubric should forbid judging output format"
        assert "do not evaluate" in steps_text
