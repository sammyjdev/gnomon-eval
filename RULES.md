# RULES

This repo has no enforced invariants yet. This file exists so the `forge`
loop has somewhere to record lessons; promoting an entry out of "Proposed by
the loop" into an enforced section is a human decision.

## Proposed by the loop

- Dataset loaders that mirror the `session_loader.py`/`chat_loader.py` shape
  (file-not-found and malformed-JSON -> `DatasetError`, duplicate id ->
  `ValueError`) need an explicit test for the empty/non-list JSON payload and
  for a malformed non-dict entry, not just missing-file and duplicate-id.
  Mutation testing on issue #9 (`chat_loader.py`) found both paths silently
  untested there. Correction (Copilot review, PR #17): this gap is
  `chat_loader.py`-specific, not inherited from `session_loader.py` --
  `tests/unit/test_session_models.py::test_load_sessions_rejects_empty_array`
  and `::test_load_sessions_labels_malformed_entry` already cover both paths
  for `session_loader.py`. A check that would have caught it: for any new
  JSON-array dataset loader, require a test asserting `DatasetError` on `[]`
  and on a JSON document that isn't a list.
