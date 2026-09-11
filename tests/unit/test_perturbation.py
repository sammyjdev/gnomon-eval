import json
import re
from pathlib import Path

from gnomon.domain.models import EvalCase
from gnomon.judge.perturbation import (
    FABRICATED_IDENTIFIER_ROOT,
    UNSUPPORTED_CLAIM_SENTENCE,
    known_fail_perturbations,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SECOND_BRAIN_CASES = REPO_ROOT / "datasets" / "second_brain" / "cases.json"


def _load_real_cases() -> list[EvalCase]:
    raw = json.loads(SECOND_BRAIN_CASES.read_text(encoding="utf-8"))
    return [EvalCase.model_validate(item) for item in raw]


def test_number_swap_emitted_when_answer_contains_digit():
    case = EvalCase(
        id="p1",
        question="What is the answer?",
        expected_answer="The answer is 42 items.",
        expected_contexts=["The context mentions items."],
    )
    pairs = known_fail_perturbations(case)
    kinds = [kind for kind, _ in pairs]

    assert "number_swap" in kinds
    number_swap_pair = next(ans for kind, ans in pairs if kind == "number_swap")
    assert "42" not in number_swap_pair
    assert number_swap_pair != case.expected_answer


def test_number_swap_not_emitted_when_answer_has_no_digit():
    case = EvalCase(
        id="p2",
        question="What is the answer?",
        expected_answer="No digits anywhere in this string.",
        expected_contexts=["Context without digits."],
    )
    pairs = known_fail_perturbations(case)
    kinds = [kind for kind, _ in pairs]

    assert "number_swap" not in kinds


def test_identifier_swap_emitted_for_backticked_span():
    case = EvalCase(
        id="p3",
        question="Which function?",
        expected_answer="Call `my_target_fn` to proceed.",
        expected_contexts=["Context references the call."],
    )
    pairs = known_fail_perturbations(case)
    kinds = [kind for kind, _ in pairs]

    assert "identifier_swap" in kinds
    ans = next(ans for kind, ans in pairs if kind == "identifier_swap")
    assert ans != case.expected_answer
    assert FABRICATED_IDENTIFIER_ROOT in ans
    assert "my_target_fn" not in ans


def test_identifier_swap_ignores_plain_text_entity():
    case = EvalCase(
        id="p4",
        question="Which function?",
        expected_answer="Call my_target_fn to proceed without backticks.",
        expected_contexts=["Context references the call."],
    )
    pairs = known_fail_perturbations(case)
    kinds = [kind for kind, _ in pairs]

    assert "identifier_swap" not in kinds


def test_identifier_swap_replaces_only_first_span():
    case = EvalCase(
        id="p5",
        question="Which functions?",
        expected_answer="Swap `first_fn` but keep `second_fn` intact.",
        expected_contexts=["Context."],
    )
    pairs = known_fail_perturbations(case)
    ans = next(ans for kind, ans in pairs if kind == "identifier_swap")

    assert "`second_fn`" in ans
    assert ans.endswith("keep `second_fn` intact.")
    assert ans.count("`") == 4
    assert "first_fn" not in ans


def test_unsupported_claim_not_emitted_when_context_contains_the_sentence():
    case = EvalCase(
        id="p6",
        question="Any claim?",
        expected_answer="Base answer.",
        expected_contexts=[f"Context intro: {UNSUPPORTED_CLAIM_SENTENCE} outro."],
    )
    pairs = known_fail_perturbations(case)
    kinds = [kind for kind, _ in pairs]

    assert "unsupported_claim" not in kinds


def test_no_emitted_answer_equals_original():
    synthetic_cases = [
        EvalCase(
            id="s1",
            question="Q?",
            expected_answer="Only digits 12345.",
            expected_contexts=["Context"],
        ),
        EvalCase(
            id="s2",
            question="Q?",
            expected_answer="Only backtick `ident`.",
            expected_contexts=["Context"],
        ),
        EvalCase(
            id="s3",
            question="Q?",
            expected_answer="Both `ident` and 99.",
            expected_contexts=["Context"],
        ),
        EvalCase(
            id="s4",
            question="Q?",
            expected_answer="Neither digits nor backticks",
            expected_contexts=["Context"],
        ),
    ]
    real_cases = _load_real_cases()

    for case in synthetic_cases + real_cases:
        pairs = known_fail_perturbations(case)
        for _, ans in pairs:
            assert ans != case.expected_answer


def test_swapped_tokens_absent_from_every_context_as_substring():
    real_cases = _load_real_cases()
    assert len(real_cases) == 34

    for case in real_cases:
        pairs = known_fail_perturbations(case)
        for kind, ans in pairs:
            if kind == "number_swap":
                m = re.search(r"\d+", case.expected_answer)
                assert m is not None
                prefix = case.expected_answer[: m.start()]
                suffix = case.expected_answer[m.end() :]
                assert ans.startswith(prefix)
                end_idx = len(ans) - len(suffix) if suffix else len(ans)
                new_run = ans[len(prefix) : end_idx]
                assert new_run != m.group(0)
                for ctx in case.expected_contexts:
                    assert new_run not in ctx
            elif kind == "identifier_swap":
                m = re.search(r"`([^`]+)`", case.expected_answer)
                assert m is not None
                prefix = case.expected_answer[: m.start()]
                suffix = case.expected_answer[m.end() :]
                assert ans.startswith(prefix)
                assert ans.endswith(suffix)
                replacement = (
                    ans[len(prefix) : len(ans) - len(suffix)] if suffix else ans[len(prefix) :]
                )
                assert replacement.startswith("`") and replacement.endswith("`")
                ident = replacement[1:-1]
                assert ident != m.group(1)
                for ctx in case.expected_contexts:
                    assert ident not in ctx
            elif kind == "unsupported_claim":
                assert UNSUPPORTED_CLAIM_SENTENCE in ans
                for ctx in case.expected_contexts:
                    assert UNSUPPORTED_CLAIM_SENTENCE not in ctx


def test_number_swap_handles_digit_run_inside_backticked_span():
    case = EvalCase(
        id="p9",
        question="Which version?",
        expected_answer="Release `v2.1` is live.",
        expected_contexts=["We use `v2.1` in production."],
    )
    pairs = known_fail_perturbations(case)
    kinds = [kind for kind, _ in pairs]

    assert "number_swap" in kinds
    ans = next(ans for kind, ans in pairs if kind == "number_swap")
    assert ans != case.expected_answer
    # The first digit run '2' is replaced
    m = re.search(r"\d+", case.expected_answer)
    assert m is not None
    prefix = case.expected_answer[: m.start()]
    suffix = case.expected_answer[m.end() :]
    assert ans.startswith(prefix)
    assert ans.endswith(suffix)
    new_run = ans[len(prefix) : len(ans) - len(suffix)] if suffix else ans[len(prefix) :]
    assert new_run != m.group(0)
    for ctx in case.expected_contexts:
        assert new_run not in ctx


def test_number_swap_skips_replacements_present_as_substring():
    # Context contains single and double digits of 9 down to 0
    single_and_double_digits = [d * length for length in (1, 2) for d in "9876543210"]
    case = EvalCase(
        id="p10",
        question="Value?",
        expected_answer="Score: 5 points",
        expected_contexts=single_and_double_digits,
    )
    pairs = known_fail_perturbations(case)
    ans = next(ans for kind, ans in pairs if kind == "number_swap")
    m = re.search(r"\d+", case.expected_answer)
    assert m is not None
    prefix = case.expected_answer[: m.start()]
    suffix = case.expected_answer[m.end() :]
    new_run = ans[len(prefix) : len(ans) - len(suffix)] if suffix else ans[len(prefix) :]

    assert new_run != "5"
    assert len(new_run) >= 3
    for ctx in case.expected_contexts:
        assert new_run not in ctx


def test_unsupported_claim_separator_respects_terminal_punctuation():
    punctuated_answers = [
        ("Answer ending with period.", " "),
        ("Answer ending with exclamation!", " "),
        ("Answer ending with question?", " "),
        ("Answer ending with ellipsis…", " "),
        ("Answer without punctuation", ". "),
    ]
    for orig, expected_sep in punctuated_answers:
        case = EvalCase(
            id="p11",
            question="Q?",
            expected_answer=orig,
            expected_contexts=["Context"],
        )
        pairs = known_fail_perturbations(case)
        ans = next(ans for kind, ans in pairs if kind == "unsupported_claim")
        assert ans == orig + expected_sep + UNSUPPORTED_CLAIM_SENTENCE


def test_generator_is_deterministic():
    case = EvalCase(
        id="p12",
        question="Which `func` with 123?",
        expected_answer="Use `func` with 123.",
        expected_contexts=["Context `func` 123."],
    )
    pairs_first = known_fail_perturbations(case)
    pairs_second = known_fail_perturbations(case)

    assert pairs_first == pairs_second


def test_kind_order_and_uniqueness():
    case = EvalCase(
        id="p13",
        question="Which `func` with 123?",
        expected_answer="Use `func` with 123.",
        expected_contexts=["Context."],
    )
    pairs = known_fail_perturbations(case)
    kinds = [kind for kind, _ in pairs]

    assert len(kinds) == len(set(kinds))
    assert kinds == ["number_swap", "identifier_swap", "unsupported_claim"]


def test_real_data_counts_match_applicability():
    cases = _load_real_cases()
    assert len(cases) == 34

    expected_num = sum(1 for c in cases if re.search(r"\d", c.expected_answer))
    expected_ident = sum(1 for c in cases if re.search(r"`[^`]+`", c.expected_answer))
    expected_claim = sum(
        1
        for c in cases
        if all(UNSUPPORTED_CLAIM_SENTENCE not in ctx for ctx in c.expected_contexts)
    )

    num_count = 0
    ident_count = 0
    claim_count = 0

    for case in cases:
        pairs = known_fail_perturbations(case)
        assert len(pairs) >= 1
        for kind, _ in pairs:
            if kind == "number_swap":
                num_count += 1
            elif kind == "identifier_swap":
                ident_count += 1
            elif kind == "unsupported_claim":
                claim_count += 1

    assert num_count == expected_num
    assert ident_count == expected_ident
    assert claim_count == expected_claim


def test_number_swap_emitted_when_digit_run_is_longer_than_every_context():
    case = EvalCase(
        id="x",
        question="q?",
        expected_answer="Build 1234567890 shipped.",
        expected_contexts=["ab"],
    )
    pairs = known_fail_perturbations(case)
    kinds = [k for k, _ in pairs]
    assert "number_swap" in kinds

    ans = next(a for k, a in pairs if k == "number_swap")
    assert ans != case.expected_answer

    prefix = "Build "
    suffix = " shipped."
    assert ans.startswith(prefix)
    assert ans.endswith(suffix)
    assert ans[: len(prefix)] == prefix
    assert ans[len(ans) - len(suffix) :] == suffix

    new_run = ans[len(prefix) : len(ans) - len(suffix)]
    assert new_run.isdigit()
    assert new_run != "1234567890"
    for ctx in case.expected_contexts:
        assert new_run not in ctx
