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
- A ChatEval dataset case whose `expected_tools` names a tool with required
  parameters (e.g. `book`'s `availability_slot_id` in the sibling `lina-mvp`
  repo's `shared-schemas/book.schema.json`) must give the target enough
  conversation turns to actually obtain those parameters before the turn
  that's expected to trigger the call -- a single-shot "confirma meu
  agendamento" message with no prior `check_availability` offer can never
  produce a valid `availability_slot_id`, so the target correctly declining
  to call `book` is not a target bug, it's an unrealistic test case. Found
  during the first real pilot run: `hallucination-no-false-booking-confirmation`
  was written as 1 turn while the dataset's other two `book`-expecting cases
  (`book-proceeds-on-clear-confirmation`, `book-slot-unavailable-graceful`)
  correctly use 3 turns (ask -> offer -> confirm). The tool schema already
  existed in `lina-mvp` a day before this dataset was written (checked via
  git log), so this wasn't a timing/availability issue -- the dataset author
  just didn't cross-reference the target repo's actual tool schemas before
  writing a scenario that expects a specific tool call. A check that would
  catch it: before adding any ChatEval case with a non-empty `expected_tools`,
  read that tool's schema in the target repo and confirm the conversation's
  turns actually establish every required parameter. (source: first real
  pilot run against lina-mvp, gnomon-eval, 2026-07-06)
- A "grep for the literal file path in tests/" precheck (e.g. `grep -rn
  "config/chat.toml" tests/`) misses references built via `pathlib` joins
  (`repo_root / "config" / "chat.toml"`), f-strings, or any construction that
  doesn't contain the literal substring -- `tests/unit/test_chat_config.py`'s
  `test_real_chat_toml_matches_spec` loads the real file this way and was
  missed by exactly that grep pattern, hard-pinning the pre-recalibration gate
  thresholds. A check that would catch it: search for the bare filename
  (`grep -rn "chat.toml" tests/`) or the loader call site
  (`grep -rn "ChatRunConfig.from_file" tests/`) instead of the joined path
  string, before treating a config-file change as "no test depends on this."
  (source: issue #22, gate-phase discovery, gnomon-eval, 2026-07-08)
