"""Unit tests for scripts/audit_hallucination_severity.py's `_classify`.

`scripts/` is not on the normal test import path (unlike `src/`, which
pyproject.toml's `pythonpath` config already covers), so this file adds it
directly, mirroring how the script itself adds `src/` to `sys.path`.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

from audit_hallucination_severity import _classify  # noqa: E402


def test_low_score_with_material_fact_marker_is_material_candidate():
    reason = "The agent invented a price not present in the docs."
    assert _classify(0.2, reason) == "material_candidate"


def test_high_score_is_clearly_fine():
    assert _classify(0.85, "The reply stayed grounded in the provided context.") == "clearly_fine"


def test_low_score_without_material_fact_marker_needs_human_review():
    reason = "The tone was slightly off from the expected persona."
    assert _classify(0.3, reason) == "needs_human_review"


def test_mid_score_needs_human_review():
    assert _classify(0.6, "Mostly correct but a bit verbose.") == "needs_human_review"
