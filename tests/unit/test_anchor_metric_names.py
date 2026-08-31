def test_anchor_metrics_are_named_once_and_ordered() -> None:
    from gnomon.metrics.names import ANCHOR_METRICS

    assert ANCHOR_METRICS == ("anchor_recall", "anchor_precision")


def test_anchor_metrics_are_not_part_of_the_judged_v1_set() -> None:
    """They are computed, not prompted - the V1 judge must never be asked for them."""
    from gnomon.metrics.names import ANCHOR_METRICS, V1_METRICS

    assert not set(ANCHOR_METRICS) & set(V1_METRICS)


def test_no_source_file_hardcodes_an_anchor_metric_string() -> None:
    """names.py is the single source of truth (RF-05), as it is for V1_METRICS.

    Matches the quoted string, not the bare identifier: `anchor_recall` is also
    a function name in metrics/anchors.py and appears in every import of it.
    """
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "src" / "gnomon"
    offenders = [
        str(path.relative_to(src))
        for path in src.rglob("*.py")
        if path.name != "names.py"
        and ('"anchor_recall"' in path.read_text(encoding="utf-8")
             or "'anchor_recall'" in path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
