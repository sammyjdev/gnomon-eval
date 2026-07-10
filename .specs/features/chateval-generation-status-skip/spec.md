# ChatEval: surface generation-failure telemetry, skip the LLM judge on a known suppression

Blueprint pass status: **schematic**, produced by `forge blueprint` from a raw
idea (no pre-existing design doc). This file is the requirement-closure +
spec artifact `quench` anchors evidence against.

## Goal

Thread a new `generation_events` telemetry list from the lina-mvp adapter
script's JSON response through `ChatResult` to `ChatJudge`, and short-circuit
the GEval/LLM criteria call with a deterministic 0.0 score whenever a
suppression event (`malformed_reply_suppressed`,
`unverified_action_claim_suppressed`, `persona_leak_suppressed`) already
tells us the cause of a generic fallback reply — so the judge never
misjudges a known generation-level failure as a content/hallucination
verdict, and never spends an LLM call whose answer is already known.

## Requirements (traceable IDs)

| ID | Requirement |
|---|---|
| CR-01 | `gnomon.domain.chat.ChatResult` gains `generation_events: list[dict] = Field(default_factory=list)`. No new nested Pydantic model — matches the raw idea's explicit instruction and the adapter's untyped-dict wire shape. |
| CR-02 | `gnomon.targets.chat_target.ChatTarget.run()` reads `body.get("generation_events", [])` from the adapter's JSON and passes it into the `ChatResult` constructor. Must default to `[]` when the key is absent (backward compatible with an adapter that hasn't landed the companion lina-mvp change yet). |
| CR-03 | `gnomon.judge.chat_judge.ChatJudge._score_criteria` checks `result.generation_events` for any entry whose `event_type` is one of the three suppression types, BEFORE calling `self._geval_factory(...)`. On a match: return score `0.0`, skip the GEval `measure()` call entirely (no LLM call), and surface which `event_type` fired. On no match: existing GEval flow, unchanged. |
| CR-04 | `ChatJudge` exposes the per-case suppression outcome as a new `self.last_generation_status: str | None` instance attribute (mirrors the existing `last_reasons` pattern), reset to `None` at the start of every `score()` call, set to the matched `event_type` only when CR-03's short-circuit fires. `score()`'s public return type (`dict[str, float]`) is unchanged. |
| CR-05 | `gnomon/cli.py`'s `_print_pilot_case_score` / `_PilotScorePrinter` (the only call site that reads judge internals beyond the scores dict — grep-confirmed, see Verification below) prints `generation_status` per case when the wrapped judge exposes a non-`None` `last_generation_status`, via the same `getattr(..., default)` pattern already used for `last_reasons`. No other call site (`chat_runner.run_chat_eval`, gate evaluation) needs changes, since none of them read judge attributes beyond the returned scores dict. |

## Verification performed during this blueprint pass (ore)

- Read `src/gnomon/domain/chat.py`, `src/gnomon/targets/chat_target.py`,
  `src/gnomon/judge/chat_judge.py`, `src/gnomon/cli.py` (lines 329-415),
  `src/gnomon/runner/chat_runner.py` in full before writing this spec.
- `grep -rn "last_reasons|\.score(|ChatJudge("` across `src/` and `tests/`
  confirms the only non-test call sites reading judge attributes beyond the
  scores dict are `cli.py`'s `_print_pilot_case_score`/`_PilotScorePrinter`.
  `chat_runner.run_chat_eval` and `runner/runner.py` (RAG arm, unrelated
  judge) only ever consume the returned `dict[str, float]`.
- `ChatJudge._score_criteria`'s current signature returns `tuple[float, str |
  None]` (score, reason) — confirmed by reading the method body directly,
  not assumed from the idea's paraphrase.
- `axon_get_context` (dec-596, dec-584, dec-640, dec-569/571/574) shows this
  area (`ChatJudge`, GEval routing, provider fallback resilience) has been
  actively iterated this session and last; nothing in that history already
  covers generation-event telemetry or a judge skip-path, so this is new
  ground, not a duplicate.
- `axon_get_context`'s dec-640 title ("make the ChatEval judge chain
  resilient to provider failures and preserve g[eneration work]") is the most
  recent related decision but addresses provider-failure resilience
  (NIM/Groq/Ollama fallback), a different concern from this idea's
  deterministic-telemetry skip.
- Uncommitted working-tree state at blueprint time already modifies
  `cli.py`, `chat_judge.py`, `test_chat_cli.py`, `test_chat_judge.py`, plus
  new `rubrics.py`/`test_rubrics.py` (same-session rubric fix, explicitly
  out of scope for this pass per the raw idea's instruction — read but not
  altered).

## Assumptions (signed, per Requirement Closure Gate)

- **A1**: `generation_events` stays `list[dict]` with no dedicated
  `GenerationEvent` Pydantic model — the raw idea states this field shape
  explicitly; introducing a stricter nested model is a speculative
  generalization this pass does not add.
- **A2**: `last_generation_status` carries the raw `event_type` string
  verbatim (e.g. `"malformed_reply_suppressed"`), not a paraphrased message —
  simplest deterministic signal, and what CR-03 explicitly asks the return
  value to be.
- **A3**: Tool-selection scoring (`_score_tool_selection` /
  `ToolCorrectnessMetric`) is unaffected by a suppression event — it is
  already a deterministic diff, not an LLM judge call, and the idea only
  asks to skip "the GEval/LLM call."
- **A4**: If `case.criteria` is falsy, no criteria scoring happens at all
  (pre-existing behavior in `score()`), so `last_generation_status` stays
  `None` regardless of `generation_events` — this feature only activates on
  the criteria-scoring path, since that's the only path with an LLM call to
  skip.
- **A5**: If `generation_events` contains more than one suppression-matching
  entry (not expected in practice — the adapter fires at most one per turn),
  the first match in list order wins. Arbitrary tie-break, not load-bearing.
- **A6**: Downstream aggregation (`chat_runner.run_chat_eval`,
  `aggregate_metric`, gate thresholds) is unchanged — `generation_status` is
  a pilot-mode/debugging surface only, not folded into the aggregated
  `EvalReport` or the gate's pass/fail decision, since the criteria metric
  still receives its correct `0.0` score through the existing
  `scores[case.criteria_metric]` path either way.

## Out of scope (explicit)

| Item | Why out of scope |
|---|---|
| `rubrics.py` / `EVALUATION_STEPS` content | Explicitly excluded by the raw idea; just-fixed and validated this session. |
| GEval call shape for the non-suppressed path | Explicitly excluded; only a pre-check short-circuit is added ahead of the existing call. |
| The lina-mvp companion adapter change that produces `generation_events` | Separate sibling-repo task with its own ordering; this pass only consumes the contract defensively (defaults to `[]`). |
| A dedicated `GenerationEvent` Pydantic model | A1 — raw idea specifies plain `list[dict]`. |
| Folding `generation_status` into `EvalReport`/gate aggregation | A6 — pilot/debug surface only per the raw idea's scope (CLI reporting, pilot-mode printer). |
| `chat_runner.py` / `runner/runner.py` changes | Neither reads judge attributes beyond the scores dict (Verification above); no change needed. |

## Classification (schematic)

- **Public/backlog vs exploratory**: **Exploratory**. The raw idea is fully
  scoped (exact fields, exact call sites, exact test files to read first)
  and ends with "Open a PR when done; do not merge" — a direct instruction to
  run the work through now in this session, not file it for a later `forge
  task` pass.
- **Depth**: **Medium** (3 source files + their existing test files touched;
  well under 10 discrete tasks; no new component, no schema/migration). Spec
  only — no separate `design.md`/`tasks.md`.

## Tier note (execution, separate axis from the classification above)

`chat_judge.py` is a named `risk_area` in `.claude/loop.yaml` (`judge`), so
the `task`-mode tier classifier's hard rule applies during execution:
`risk_area_hit: true` forces `effective_tier: Legendary` regardless of this
spec's Medium depth — depth sizes the spec/paperwork, tier sizes the
maker/reviewer machinery, and they are independent axes by design.

## Confirmation (per blueprint.md step 3)

This blueprint pass is being relayed to a human who gave the raw idea with
an explicit "Open a PR when done; do not merge" instruction and no
opportunity for a live back-and-forth in this run. Given the unambiguous
exploratory + Medium signal above, this pass proceeds directly to the
smith → gate → quench → anneal → ship flow in a spec-slug worktree rather
than pausing for a confirmation reply with no one present to answer it. The
human reviewing the resulting PR is the actual confirmation point.
