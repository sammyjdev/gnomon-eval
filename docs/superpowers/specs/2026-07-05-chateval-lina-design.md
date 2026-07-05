# ChatEval: conversational/tool-calling eval arm, first target Lina

**Goal:** Add a new GNOMON arm -- ChatEval -- that evaluates a multi-turn, tool-calling chat agent (starting with Lina, a WhatsApp AI agent) using a real LLM judge, reusing GNOMON's existing harness (CLI, bootstrap-CI reporting, gate) while delegating tool-calling and criteria-based scoring to DeepEval instead of hand-rolling it.

**Architecture:** A new `targets/chat_target.py` and `runner/chat_runner.py` in `gnomon-eval`, following the same pattern as the existing `session` arm (own target, own runner, own CLI subcommand, own dataset loader) rather than forcing this into the original `RagTarget`/`Judge` protocol shape, which does not fit multi-turn tool-calling. Scoring is delegated to DeepEval's `ToolCorrectnessMetric` and `GEval` rather than a new hand-rolled judge -- a thin adapter converts DeepEval's per-case results into GNOMON's existing `MetricScores`/bootstrap-CI/report/gate pipeline, so GNOMON remains the single branded tool and report format across the user's projects, while DeepEval supplies the tool-calling/criteria-scoring primitives it already has.

**Tech Stack:** Python, GNOMON's existing `src/gnomon/` package, DeepEval (new dependency), NVIDIA NIM (`meta/llama-3.3-70b-instruct`, free tier, already used elsewhere in this toolchain) as the primary judge model via LiteLLM, local Ollama (`phi4:14b`, already installed) as fallback if NIM is unavailable. Lina's side needs a small adapter script exposing its real conversation loop (real Anthropic/litellm call, no scripted fake) for ChatEval to invoke per case.

## Context

GNOMON was built for RAG evaluation (`RagTarget.query(question) -> answer + contexts`, scored on faithfulness/context_precision). It has already been extended twice beyond that shape (`TcmTarget` for a test-body-extraction case, and the `session`/AXON arm for multi-turn memory-savings measurement) -- each extension added its own target/runner/judge rather than forcing the original protocol, which is the precedent this design follows.

Lina's own regression eval suite (built earlier, `gateway/tests/test_scenarios.py` in `lina-mvp`, 11 scenarios, scripted fake LLM, gates CI) proves the *code* is correct -- routing, persistence, tool execution, session lifecycle. It structurally cannot answer three questions that require a real model making real decisions: does the model pick the right tool given a realistic conversation, is the Portuguese natural and on-brand, does it avoid hallucinating against real tool output. ChatEval is that layer, deliberately kept separate: it costs money (real LLM calls) and is run manually/on-demand, never as a CI gate.

A related, separate gap surfaced during this design (documented as `sammyjdev/lina-mvp#1`, not part of this spec): Lina has no way to look up which of a tenant's configured services/prices applies to an ambiguous request (e.g. gendered pricing for the same service name), and no mechanism for marking a service as "human-only, never AI." That gap blocks specifically the "variable service pricing" test cases and is out of scope here -- the 17-case dataset below does not include those cases.

## Golden dataset (17 cases, Lina as first target)

Lives at `gnomon-eval/datasets/lina_chateval/`, following the existing `datasets/<name>/` convention (see `datasets/rpg_master_example/`, `datasets/second_brain/`).

- `answer_question` (3): real FAQ match, no-match fallback without hallucinating an answer, does not invent an answer absent from the FAQ.
- `check_availability` (3): correct date/service extraction, ambiguous date handled (asks, doesn't guess), correctly reports "no slots" rather than inventing one.
- `book` (3): only proceeds with a clear confirmed slot, does not book without confirmation, handles `slot_unavailable` gracefully.
- `capture_lead` (2): captures name/interest without asking for phone (regression check for the schema fix shipped earlier today), triggers correctly on a real interest signal.
- `request_handoff` (2): triggers on an explicit request for a human, does not trigger prematurely on a simple question.
- Tone/brand (2): never says "I'm Lina," matches the tenant's configured tone.
- Hallucination vs. tool output (2): does not claim a slot is free when `check_availability` said otherwise, does not confirm a booking that failed.

Each case: `input` (the conversation so far), `expected_tools` (DeepEval's field, empty list if a pure-text reply is correct), and a natural-language `criteria` string for the GEval-scored cases (tone, hallucination).

## Judge and gates

- **Primary judge**: NVIDIA NIM `meta/llama-3.3-70b-instruct`, free tier, confirmed live against the API during this design session. Chosen over anything locally runnable on the Mac (largest local model is 14B, none validated for natural-language judgment) and consistent with this toolchain's own "reviewers stay frontier" principle (a weak judge produces false approvals).
- **Fallback judge**: local Ollama `phi4:14b`, used only if the NIM call fails/times out -- mirrors the existing `local_m1`/`fallback` pattern already established in `~/.claude/models.yaml`.
- **Pilot step (required before the full run)**: run 4-5 cases first to confirm the judge's Portuguese-language quality is good enough -- no documentation confirms this for DeepEval's judge integration, so this is validated empirically, not assumed.
- **Gates** (mirrors GNOMON's existing gate-on-CI-low philosophy, ADR-0006, applied manually here since this isn't a CI gate):
  - Tool selection: `ToolCorrectnessMetric` pass rate >= 90% across the dataset (tolerates 1-2 ambiguous cases out of 17).
  - Tone/brand: `GEval` mean score >= 0.8.
  - Hallucination vs. tool output: `GEval` mean score >= 0.9 (the strictest gate -- near-zero tolerance).
  - Report format matches GNOMON's existing report (mean + bootstrap CI per metric, cost/latency), not a bare pass/fail.

## Cadence

Manual, on-demand only (e.g. before changing the system prompt, before Milestone B). Never scheduled, never a CI gate -- real LLM calls cost money per run.

## Cross-repo split

- **`gnomon-eval`** (the ChatEval module itself): `targets/chat_target.py`, `runner/chat_runner.py`, a DeepEval-to-`MetricScores` adapter in `metrics/`, a dataset loader for the new case format, a `gnomon chat` CLI subcommand, judge wiring for NIM + Ollama fallback, config section, and the 17-case dataset content.
- **`lina-mvp`** (the thing being evaluated): a small adapter script (e.g. `gateway/scripts/run_chateval_case.py`) that runs one real conversation through `MessageProcessor.process()` against a real Postgres tenant fixture, with a **real** `CoreClient` (actual Anthropic/litellm call, not the `ScriptedCore` fake used in the regression suite) and a **fake** `WhatsAppSender` (to avoid real sends), then reports back which tool(s) fired and the final reply text -- reusing the `scenario_tenant`-style fixture pattern already built for the regression suite, minus the LLM fake.
- Neither repo depends on the other at the code level; ChatEval's `LinaAdapter` (in `gnomon-eval`) invokes `lina-mvp`'s script as a subprocess (matching GNOMON's existing adapter-based-target philosophy, ADR-0001), passing a case's conversation input and reading back structured JSON (tool called + reply text).

## Execution

Both repos need `.claude/loop.yaml` bootstrapped before `forge` can run tasks in them (neither has one today). Config per repo, following the `Orion-AI/.claude/loop.yaml` template already in use elsewhere in this environment:
- `gnomon-eval`: `gate_cmd` runs its existing test suite (unaffected by ChatEval, which needs real API keys and is not part of the gate); `posture: research` (matches its nature as an evaluation tool, not a shipped product).
- `lina-mvp`: reuses the same `gate_cmd` as its GitHub Actions workflow (the deterministic pytest suite, not ChatEval).

## Deferred (not this design)

- The service-catalog/`list_services`/human-only-service gap (`sammyjdev/lina-mvp#1`) -- separate product design.
- Expanding ChatEval to a second target (Lume) -- this design's dataset/gates are Lina-specific; a `LumeAdapter` and Lume-specific golden dataset are future work once Lume's own chat loop is ready to evaluate.
- Any change to Lina's production code -- ChatEval only observes/evaluates, it does not change `gateway/src/lina_gateway/`.

## Testing

The regression suite already proves the harness works with a fake LLM; ChatEval's own "test" is the pilot batch (4-5 cases against the real NIM judge) confirming judge quality before committing to the full 17-case run. The DeepEval-to-`MetricScores` adapter itself should have ordinary unit tests (matching GNOMON's existing test conventions in `tests/unit/`) verifying the score/CI conversion is correct independent of any real API call, using a stubbed DeepEval result.
