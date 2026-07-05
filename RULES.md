This repo has no enforced invariants yet. This file exists so the `forge`
loop has somewhere to record lessons; promoting an entry out of "Proposed by
the loop" into an enforced section is a human decision.

## Proposed by the loop

- Dataset loaders that mirror the `session_loader.py`/`chat_loader.py` shape
  (file-not-found and malformed-JSON -> `DatasetError`, duplicate id ->
  `ValueError`) need an explicit test for the empty/non-list JSON payload and
  for a malformed non-dict entry, not just missing-file and duplicate-id.
  Mutation testing on issue #9 (`chat_loader.py`) found both paths silently
  untested -- inherited verbatim from `session_loader.py`, which has the same
  gap. A check that would have caught it: for any new JSON-array dataset
  loader, require a test asserting `DatasetError` on `[]` and on a JSON
  document that isn't a list.
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
- A primary-then-fallback provider selector (e.g. `cli.py`'s
  `_build_judge_model` trying NIM then falling back to Ollama on any
  exception) that catches broadly and switches provider with no log/warning
  call lets a full run silently execute entirely on the fallback provider --
  a bad API key, wrong model name, or NIM outage produces a normally-shaped
  passing report with zero operator-visible signal that the primary was never
  used. A check that would catch it: any `except Exception` branch that
  routes to a different backend/provider must have an adjacent
  `logging.warning` (or equivalent) naming the caught exception, and a test
  should assert that log call fires on fallback. (source: issue #13 quench,
  code-quality review, gnomon-eval, 2026-07-05)
