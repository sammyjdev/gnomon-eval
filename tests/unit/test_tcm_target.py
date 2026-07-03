"""TcmTarget unit tests (Phase C2).

Verifies test-body lookup for Python files via ast.parse.
"""

import textwrap

from gnomon.domain.interfaces import RagTarget
from gnomon.targets.tcm_target import _NO_TEST_FOUND, TcmTarget


def test_tcm_target_conforms_to_rag_target_protocol(tmp_path):
    target = TcmTarget(plan_path="", tests_dir=str(tmp_path))
    assert isinstance(target, RagTarget)


def test_tcm_target_finds_test_body(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_retry.py").write_text(
        textwrap.dedent("""\
            def test_s01_retry():
                # retry on failure scenario
                assert True
        """)
    )

    target = TcmTarget(plan_path="", tests_dir=str(tests_dir))
    resp = target.query("S-01 - retry on failure")

    assert resp.contexts[0] != _NO_TEST_FOUND
    assert "test_s01_retry" in resp.contexts[0]


def test_tcm_target_returns_not_found_when_no_match(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    # Only S-01 tests exist; querying S-02 should return no match.
    (tests_dir / "test_s01.py").write_text("def test_s01_something(): pass\n")

    target = TcmTarget(plan_path="", tests_dir=str(tests_dir))
    resp = target.query("S-02 - something else")

    assert resp.contexts == [_NO_TEST_FOUND]


def test_tcm_target_no_story_id_in_description_returns_not_found(tmp_path):
    target = TcmTarget(plan_path="", tests_dir=str(tmp_path))
    resp = target.query("no story id here")
    assert resp.contexts == [_NO_TEST_FOUND]


def test_tcm_target_missing_tests_dir_returns_not_found(tmp_path):
    absent = tmp_path / "nonexistent"
    target = TcmTarget(plan_path="", tests_dir=str(absent))
    resp = target.query("S-01 - some story")
    assert resp.contexts == [_NO_TEST_FOUND]


def test_tcm_target_finds_underscore_variant(tmp_path):
    """s_01 naming variant is recognized."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_s_01.py").write_text(
        textwrap.dedent("""\
            def test_s_01_happy_path():
                assert 1 + 1 == 2
        """)
    )

    target = TcmTarget(plan_path="", tests_dir=str(tests_dir))
    resp = target.query("S-01 - happy path")

    assert "test_s_01_happy_path" in resp.contexts[0]


def test_tcm_target_response_fields_are_valid(tmp_path):
    """RagResponse invariants: total_tokens >= 0, latency_ms >= 0, answer is str."""
    target = TcmTarget(plan_path="", tests_dir=str(tmp_path))
    resp = target.query("S-99 - anything")
    assert resp.total_tokens == 0
    assert resp.latency_ms >= 0.0
    assert resp.answer == ""
