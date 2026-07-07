# ChatEval: conversational/tool-calling eval arm, first target Lina

Blueprint pass status: **schematic**, produced by `forge blueprint` from a
pre-existing design + plan (not a raw idea). Source documents, read in full
before this spec, are the primary input and remain the detailed reference:

- Design: `docs/superpowers/specs/2026-07-05-chateval-lina-design.md`
- Plan (adopted as `tasks.md` in this directory, adapted to forge's
  one-issue-per-task convention rather than re-derived): `docs/superpowers/plans/2026-07-05-chateval.md`

This file is the forge-convention spec artifact `quench` anchors evidence
against; it summarizes and traces requirements rather than restating the full
design rationale, which lives in the design doc above.

## Goal

Add a `gnomon chat` arm to this repo that evaluates Lina (a WhatsApp AI agent
in the sibling repo `lina-mvp`) using a real LLM judge, reusing this repo's
existing domain shape (`aggregate_metric`, `evaluate_gate`, `EvalReport`)
unchanged, with DeepEval's `ToolCorrectnessMetric`/`GEval` supplying the actual
scoring instead of a hand-rolled judge.

## Requirements (traceable IDs)

| ID | Requirement | Plan task |
|---|---|---|
| CR-01 | `ChatCase`/`ChatResult` frozen pydantic domain models | Task 2 |
| CR-02 | Chat dataset loader + Lina golden dataset at `datasets/lina_chateval/cases.json` (17 cases at blueprint time, expanded to 28 on 2026-07-06 -- see design doc's "Update" note) | Task 3 |
| CR-03 | `ChatJudge`: DeepEval `ToolCorrectnessMetric` (tool selection) + `GEval` (tone/brand, hallucination), two named error types | Task 4 |
| CR-04 | `ChatTarget`: subprocess call into `lina-mvp`'s adapter script, JSON stdin/stdout contract, no direct import of `lina-mvp` code | Task 5 |
| CR-05 | `run_chat_eval`: orchestrates cases into an `EvalReport`, reusing `aggregate_metric` unchanged | Task 6 |
| CR-06 | `gnomon chat` CLI + `ChatRunConfig` (TOML) + gate wiring, reusing `evaluate_gate` unchanged; judge provider is NIM (`meta/llama-3.3-70b-instruct`) primary, local Ollama (`phi4:14b`) fallback | Task 7 |
| CR-07 | Manual pilot step (4-5 cases) run and read by a human before trusting the full dataset (17 cases at blueprint time, 28 as of 2026-07-06) | Task 8 |
| NFR-01 | ChatEval is never part of any CI gate in either repo; manual/on-demand only (real LLM cost per run) | Tasks 7, 8 |
| NFR-02 | Gates reuse `evaluate_gate`'s existing `ci_low`-based semantics (ADR-006): `tool_selection_accuracy` >= 0.90, `tone_brand` >= 0.80, `hallucination` >= 0.90 | Task 7 |

## Verification performed during this blueprint pass (ore)

Cross-checked the plan's code against the actual current codebase (not just
internal self-consistency) before accepting it as ready to become issues:

- `gnomon.metrics.confidence.aggregate_metric` signature and
  `gnomon.gate.gate.evaluate_gate` (ADR-006, gates on `ci_low`) match exactly
  what Tasks 6-7 assume.
- `gnomon.domain.models.EvalReport.metric()/.total_tokens/.mean_latency_ms`
  and `CaseCost`/`MetricResult` match Task 6's test expectations verbatim.
- `cli.py`'s existing `build_target`/`build_judge`/`session_main`/`main`
  dispatch pattern matches what Task 7 extends.
- ADR-0001 (adapter-based target philosophy) supports extending the adapter
  pattern from HTTP to subprocess, as Task 5 does.
- AXON context (`axon_get_context`, `get_adrs`) shows no prior decision this
  idea contradicts or duplicates; ADR-002/006/007/008 (judge determinism,
  gate-on-ci_low, bootstrap CI) are all reused unchanged, not re-litigated.

## Assumptions (signed, per Requirement Closure Gate)

None of these blocked the design; each is a falsifiable one-liner a human
corrects in review if wrong.

- **A1**: DeepEval `>=2.0`'s `ToolCorrectnessMetric`/`GEval` constructor
  signatures match what Tasks 4 and 7's code assumes. Unverified against the
  live library (not installed in this repo yet) -- Task 4/7's own gate run
  will surface a mismatch immediately if wrong; not a design-blocking
  question now.
- **A2**: litellm's provider prefix for NVIDIA NIM is `nvidia_nim/<model>`.
  Consistent with this machine's already-validated `AXON_ADR_MODEL` setting
  (`nvidia_nim/meta/llama-3.3-70b-instruct`, see `~/.claude/AXON.md`), so
  treated as confirmed rather than a fresh guess.
- **A3**: Task 8 (pilot + full run) cannot execute end-to-end until
  `lina-mvp`'s own adapter-script task (that repo's separate plan) is merged.
  Its GitHub issue is opened labeled `agent:blocked`, not `agent:ready`, with
  the cross-repo dependency stated explicitly -- proactively, rather than
  letting `forge run` discover the block by trying and failing.
- **A4**: This repo's `.claude/loop.yaml` (bootstrapped in Task 1) declares
  labels `agent:ready`/`agent:blocked`, but `docs/agents/triage-labels.md`
  documents a different vocabulary (`ready-for-agent`) for this same repo's
  issue tracker, and neither label existed on GitHub before this pass. The
  two conventions were bootstrapped independently in different sessions and
  are not reconciled here -- issues in this pass use the loop.yaml vocabulary
  (`agent:ready`/`agent:blocked`) since that is what `forge task`/`forge run`
  actually read to select work; reconciling `docs/agents/triage-labels.md` is
  a separate, later cleanup, out of scope for this blueprint.
- **A5**: `docs/agents/domain.md` declares this repo's domain-doc convention
  as "one `CONTEXT.md` + `docs/adr/` at repo root," but no `CONTEXT.md`
  exists at the repo root today (only `docs/adr/` does). Pre-existing gap,
  unrelated to ChatEval, not created by this blueprint pass.

## Out of scope (explicit)

| Item | Why out of scope |
|---|---|
| `lina-mvp`'s adapter script itself | Owned by that repo's own spec (`docs/superpowers/specs/2026-07-05-chateval-adapter-design.md` in `lina-mvp`) and its own `forge` loop |
| Service-catalog / `list_services` / human-only-service gap | Tracked separately as `sammyjdev/lina-mvp#1`; a product gap, not an eval-harness gap |
| Expanding ChatEval to a second target (Lume) | Future work once Lume's own chat loop is ready; this dataset/gates are Lina-specific |
| Any change to Lina's production code | ChatEval only observes/evaluates via subprocess; never touches `gateway/src/lina_gateway/` |
| Making ChatEval part of any CI gate | Deliberately manual/on-demand; real LLM calls cost money per run |
| Creating `CONTEXT.md` at repo root | Pre-existing convention gap (A5), unrelated to this idea |
| Reconciling `docs/agents/triage-labels.md` vocabulary with `loop.yaml` labels | Pre-existing gap (A4), separate cleanup |

## Classification (schematic)

- **Public/backlog vs exploratory**: **Public/backlog**. The source plan
  explicitly frames each remaining task as "one `forge task` unit: one GitHub
  issue, one worktree, TDD, gate, quench, PR," and the cross-repo half of
  this same idea is already tracked as a real issue in the sibling repo
  (`sammyjdev/lina-mvp#1` referenced for the deferred gap). This is backlog
  work carried out over multiple `forge task`/`forge run` passes, not a
  one-off validation run.
- **Depth**: **Large** (multi-component: new domain models, loader, judge,
  target, runner, CLI/config, new dependency, cross-repo subprocess
  boundary). Full spec (this file) + the adopted `tasks.md`. No separate
  `design.md` was written fresh -- the existing design doc
  (`docs/superpowers/specs/2026-07-05-chateval-lina-design.md`) already
  serves that role and is cross-referenced rather than duplicated.

## Confirmation (per blueprint.md step 3)

This blueprint pass is being relayed to a human who was not present in this
session (per the invoking instructions), with an explicit instruction to
"follow whichever path the classifier and blueprint logic actually decide."
Given the unambiguous public/backlog + Large signal above, this pass proceeds
directly to opening GitHub issues (Tasks 2-8) rather than pausing for a live
confirmation reply that has no one to answer it in this run. The human
reviewing the resulting issues/report is the actual confirmation point.
