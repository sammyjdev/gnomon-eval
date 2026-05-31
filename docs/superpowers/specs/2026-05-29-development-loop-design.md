# Design — gnomon-eval development loop

**Date:** 2026-05-29
**Status:** Approved (approved brainstorming), awaiting implementation plan
**Author:** Sam + Claude

## Purpose

Establish a repeatable logic to **evaluate, evolve, validate, and document**
each increment of gnomon-eval, from Phase 1 -> v1 -> v2. It serves two declared
objectives: work organization and portfolio quality. The project is developed
under spec; this loop is the method that keeps the spec, code, tests, and ADRs
in sync as the project grows.

## Scope and design decisions

Four decisions fixed during brainstorming govern this design:

1. **Layer: process, not product.** This is work methodology anchored
   in the available skills, not code inside `src/gnomon/`. No new module
   in the harness comes out of this document.
2. **Unit of work: vertical slice (tracer bullet).** Each cycle delivers
   an end-to-end slice that touches several layers and closes a set of
   requirements from the spec -- the same logic Phase 1 already proved.
   Work does not proceed by isolated requirement (too granular, slices that do
   not close) nor by architectural component (hides the end-to-end flow).
3. **Enforcement: lightweight playbook.** Discipline by convention, not by
   automatic rail. No CI gates dedicated to the loop, no new git hooks, no
   issue tracker. The document is followed by hand. If convention is not
   enough, automation is a future evolution, recorded as such.
4. **AXON context: `personal`.** The project enters the vault under ctx `personal`.
5. **AXON cadence: per milestone.** Synchronization with the vault (`pb
   index` + `save_adr` + session memory) runs when closing a **milestone**
   -- a cohesive milestone or phase --, not on every slice. Content policy:
   always add new documents and changes to the vault incrementally; never
   re-register in bulk what has not changed.
6. **Name `gnomon` everywhere, now.** The divergence `gnomon` (package) vs
   `rag_eval` (docs) is resolved now: all docs are aligned to `gnomon` /
   `gnomon-eval`. This does not remain as a pending item for later.

## The 4-stage loop

Each vertical slice goes through the four stages in order. Each stage has an
anchor skill and a concrete output that unlocks the next.

| Stage | Question it answers | Anchor skill | Output |
|---|---|---|---|
| **1. Evaluation** | What is the next slice? Is it worth building now? Which RF/RNF/VAL does it close? | `superpowers:brainstorming` (scope) + `superpowers:writing-plans` (strategy) | Named slice + list of requirements it satisfies |
| **2. Evolution** | Where does it fit in the architecture without violating the dependency direction? Does any module need to be deepened first? | `improve-codebase-architecture` | Insertion point + prerequisite refactor (if any) |
| **3. Validation** | Is the slice correct and honest? | `superpowers:test-driven-development` + `superpowers:verification-before-completion` | Green suite with RED->GREEN observed + project gates passing |
| **4. Documentation** | What was decided that is not obvious in the code? | `grill-with-docs` + AXON (`save_adr`, `pb index`) | Updated/new ADR + honest README + decision and code in the vault |

The loop closes when the slice passes the Definition of Done and returns to
stage 1 for the next slice.

## Definition of Done for a slice

The gate of the Validation stage **reuses the existing non-negotiable invariants** of
the project; it does not create new criteria. A slice is done when:

1. RED->GREEN was observed for each new production piece (TDD -- Iron Law).
2. `ruff check` and `ruff format --check` pass clean.
3. `pytest` is green, including the reproducibility suite.
4. The non-negotiable invariants touched by the slice are verified by test
   (dependency direction, statistical honesty, reproducibility,
   cost/latency as first-class concerns, fail-closed, offline-first, documentary
   honesty -- as the slice touches each one).
5. A non-obvious decision was made -> ADR updated/created (in `docs/adr/`); new
   assertion in the README -> there is a command that reproduces it (RNF-05).

Steps 1-5 apply **per slice**. Synchronization with AXON does not run on every
slice -- it runs when closing a milestone (see AXON Integration).

## AXON Integration

AXON is where the Documentation stage gains permanence and semantic search.
Synchronization is per **milestone**, not per slice, and is always
incremental: it adds new documents and changes, without re-registering in bulk.

**When closing a milestone (stage 4):**
- `pb index /Users/samdev/dev/gnomon-eval --ctx personal` -> reindexes the code and
  the changed docs; `search_code` starts seeing them, replacing blind `read`
  (golden rule from AXON.md).
- `save_adr(project="gnomon-eval", ...)` for each **new** decision from the milestone ->
  becomes a searchable ADR and feeds `get_adrs`. Already-registered decisions are not
  re-submitted.
- Session memory capture for the milestone -> `get_session_memory` resumes context
  between sessions.

**Milestone 0 -- onboarding + Phase 1 (executed together with this delivery):**
1. `git init` + initial commit of Phase 1. *(Done.)*
2. Align docs to `gnomon` / `gnomon-eval` (decision 6): `ARCHITECTURE.md`
   (`src/rag_eval/` -> `src/gnomon/`) and `README.md` (`rag-eval-harness` ->
   `gnomon-eval`), with surgical changes, without rewriting the rest.
3. `pb scan ~/dev` + `pb index /Users/samdev/dev/gnomon-eval --ctx personal` ->
   indexes code and docs. The 4 ADRs in markdown enter here as searchable
   documents; they are **not** re-registered via `save_adr` (incremental policy).
4. `save_adr(project="gnomon-eval", ...)` only for new decisions that do not yet
   have their own ADR:
   - The two open points from ADR-002 (N of runs, cache granularity).
   - Clamp of the confidence interval to [0,1] for bounded metrics (raw mean, clamped
     interval).
   - Conditional N=8 recommendation (computability floor is 2, but N=2 is useless
     for gate -- critical t 12.7; elbow at N~8-10 for sigma~0.046 from the stub;
     final number depends on measuring the real Ollama judge).
5. Capture session memory for Phase 1.

## Artifact and location

Deliverable A: `docs/DEVELOPMENT_LOOP.md` -- the operational playbook, derived
from this design, in the voice of "how we work in this repo". More concise
than this design (which records the *why* of the choices); the playbook records
the *how* of day-to-day work.

Deliverable B: the AXON onboarding above, executed.

## Out of scope

- Commands/slash-commands or git hooks that automate the loop stages
  (against the "lightweight playbook" choice; future evolution if convention fails).
- Issue tracker for the slices (`to-issues`); slices are tracked in the
  playbook itself and in commits.
- Any changes to `src/gnomon/` code -- this is process work.
- Deciding the open parameters from ADR-002 without real measurement of the Ollama judge.

## Risks and mitigations

- **Convention ignored under pressure.** Lightweight playbook blocks nothing. Mitigation: the
  Definition of Done reuses gates that are already release barriers (ruff, pytest),
  so the critical part of validation remains hard even without a process rail.
- **AXON out of date relative to the code.** If `pb index` does not run at the end of the
  slice, `search_code` lies. Mitigation: indexing is an explicit item in the Definition
  of Done (step 6).
- **Name divergence (`gnomon` vs `rag_eval`).** Resolved in this milestone
  (decision 6): docs aligned to `gnomon`. Residual risk: references to
  `rag_eval` that escape the sweep -- mitigation: `grep` for `rag_eval` and
  `rag-eval-harness` at the end of the alignment, ensuring zero occurrences.
