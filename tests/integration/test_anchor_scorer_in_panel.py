"""AnchorScorer through run_panel_eval, checking the "ordinary PanelMember" claim.

The spec asserts the scorer "enters a panel as an ordinary PanelMember, so it
inherits per-case scores, bootstrap CIs and aggregation with no change to
run_panel_eval". That was true by inspection but untested: the scorer appeared
nowhere outside its own module and unit test. These tests put it in a mixed
panel next to an LLM-contract judge and check the claim end to end.

No network: MockTarget and StubJudge are both in-memory.
"""

from gnomon.config.config import EvalConfig
from gnomon.domain.models import EvalCase, MetricResult
from gnomon.judge.anchor_scorer import AnchorScorer
from gnomon.judge.stub import StubJudge
from gnomon.metrics.names import ANCHOR_METRICS, V1_METRICS
from gnomon.runner.panel_runner import PanelMember, run_panel_eval
from gnomon.targets.mock import MockTarget

RECALL, PRECISION = ANCHOR_METRICS

# One anchor of two is retrieved for case-1, the only anchor for case-2, so the
# per-case recall series is [0.5, 1.0] - it varies, which a CI needs.
CASES = [
    EvalCase(
        id="case-1",
        question="where is Foo defined?",
        expected_answer="in foo.py",
        expected_contexts=["class Foo:", "class Bar:"],
    ),
    EvalCase(
        id="case-2",
        question="where is Foo declared?",
        expected_answer="in foo.py",
        expected_contexts=["class Foo:"],
    ),
]

CONTEXTS = ["class Foo:", "unrelated prose"]


def _panel_report(judge_runs: int = 2, *, deterministic_judge: bool = False):
    # deterministic_judge only relaxes the judge_runs floor (VAL-04); it changes
    # nothing about how the anchor scorer is called.
    config = EvalConfig(
        reproducible=True,
        seed=42,
        deterministic_judge=deterministic_judge,
        judge_runs=judge_runs,
    )
    target = MockTarget(answer="a", contexts=CONTEXTS, total_tokens=10, latency_ms=1.0)
    members = [
        PanelMember(judge_id="stub", family="stub", judge=StubJudge()),
        PanelMember(judge_id="anchors", family="deterministic", judge=AnchorScorer()),
    ]
    return run_panel_eval(CASES, target, members, config)


def _anchor_report(report):
    return next(r for r in report.judge_reports if r.judge_id == "anchors")


def test_panel_accepts_the_scorer_with_no_runner_change() -> None:
    report = _panel_report()
    assert [r.judge_id for r in report.judge_reports] == ["stub", "anchors"]
    assert _anchor_report(report).family == "deterministic"


def test_panel_aggregates_exactly_the_anchor_metrics() -> None:
    """It must not acquire the judged V1 metrics, nor lose one of its own."""
    metrics = {metric.metric for metric in _anchor_report(_panel_report()).metrics}
    assert metrics == set(ANCHOR_METRICS)
    assert not metrics & set(V1_METRICS)


def test_panel_gives_the_anchor_metrics_bootstrap_confidence_intervals() -> None:
    for metric in _anchor_report(_panel_report()).metrics:
        assert isinstance(metric, MetricResult)
        assert metric.n == len(CASES)
        assert metric.confidence_level == 0.95
        assert 0.0 <= metric.ci_low <= metric.mean <= metric.ci_high <= 1.0


def test_panel_carries_the_per_case_anchor_scores() -> None:
    case_scores = _anchor_report(_panel_report()).case_scores
    assert [(s.case_id, s.score) for s in case_scores[RECALL]] == [("case-1", 0.5), ("case-2", 1.0)]
    assert [s.score for s in case_scores[PRECISION]] == [0.5, 0.5]
    recall = next(m for m in _anchor_report(_panel_report()).metrics if m.metric == RECALL)
    assert recall.mean == 0.75


def test_extra_judge_runs_are_wasted_work_not_noise_reduction() -> None:
    """The spec's judge_runs claim: deterministic, so averaging runs changes nothing."""
    one = _anchor_report(_panel_report(judge_runs=1, deterministic_judge=True)).metrics
    many = _anchor_report(_panel_report(judge_runs=7)).metrics
    assert {m.metric: m.mean for m in one} == {m.metric: m.mean for m in many}


def test_disagreement_covers_the_anchor_metrics_too() -> None:
    """A mixed panel: only one member scores them, so the spread is zero, not absent."""
    stats = {stat.metric: stat for stat in _panel_report().disagreement}
    assert set(ANCHOR_METRICS) <= set(stats)
    assert set(stats[RECALL].case_deltas.values()) == {0.0}
