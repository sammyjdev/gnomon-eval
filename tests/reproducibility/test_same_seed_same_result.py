"""Reproducibility suite (RNF-01, non-negotiable #3).

The central invariant: same input, same seed, same judge model produce the
same result within the reported variance. With the deterministic stub judge
the result is bit-identical, which is the strongest form of the guarantee.
The suite also checks that the seed actually drives the result — a different
seed must change it — otherwise "reproducibility" would be a constant in
disguise.
"""

from gnomon.config.config import EvalConfig
from gnomon.domain.models import EvalCase
from gnomon.judge.stub import StubJudge
from gnomon.runner.runner import run_eval
from gnomon.targets.mock import MockTarget

CASE = EvalCase(
    id="case-1",
    question="Who narrates the world?",
    expected_answer="The game master narrates the world.",
    expected_contexts=["The game master narrates the world to the players."],
)


def _target() -> MockTarget:
    return MockTarget(
        answer="The game master narrates the world.",
        contexts=["The game master narrates the world to the players."],
        total_tokens=137,
        latency_ms=512.0,
    )


def _run(seed: int) -> tuple[float, float, float]:
    cfg = EvalConfig(reproducible=True, seed=seed, judge_runs=8)
    m = run_eval([CASE], _target(), StubJudge(), cfg).metric("faithfulness")
    return (m.mean, m.ci_low, m.ci_high)


def test_same_seed_produces_identical_result():
    assert _run(42) == _run(42)


def test_different_seed_changes_the_result():
    assert _run(42) != _run(7)
