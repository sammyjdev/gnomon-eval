# RULES

No enforced invariants yet. This file exists so the `forge` loop has somewhere
to record proposed rules (see below); promote any of these to an enforced
section above this line only by human decision.

## Proposed by the loop

- When a test stubs a `.measure(test_case)`-style collaborator that records
  `measured_with`, assert on `measured_with`'s constructed arguments (not just
  the returned score) — otherwise a mutation that breaks argument construction
  (e.g. dropping `tools_called`/`expected_tools` before it reaches the real
  provider) survives the test suite silently. (source: issue #10 quench,
  gnomon-eval, 2026-07-05)
- Metric-name routing decisions bucketed by string-matching free text (e.g.
  `chat_judge.py`'s `_criteria_metric_name` picking `"tone_brand"` vs
  `"hallucination"` by scanning `case.criteria`/`case.id` substrings) should be
  pinned down as an explicit case field or a documented rule in the feature's
  spec.md before implementation, not left as an implicit heuristic — a
  silent mis-tag mixes two metric semantics under one aggregated name with no
  error. (source: issue #10 quench, code-quality review, gnomon-eval,
  2026-07-05)
