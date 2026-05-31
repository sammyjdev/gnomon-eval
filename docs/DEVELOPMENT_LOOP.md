# GNOMON Development Loop

How gnomon-eval evolves, vertical slice by vertical slice. A lightweight playbook: discipline by
convention, not by automated rails. The unit of work is the **vertical slice**
(tracer bullet) — an end-to-end increment that touches multiple layers and closes
a set of requirements from the spec.

## The loop

Each slice moves through four stages in order:

1. **Assessment** — what is the next slice? Is it worth it now? Which RF/RNF/VAL does it close?
   - Skills: `superpowers:brainstorming` (scope), `superpowers:writing-plans` (strategy).
   - Output: named slice + list of requirements it satisfies.
2. **Evolution** — where does it fit in the architecture without violating the
   dependency direction? Does any module need to be deepened first?
   - Skill: `improve-codebase-architecture`.
   - Output: insertion point + prerequisite refactor (if any).
3. **Validation** — is the slice correct and honest?
   - Skills: `superpowers:test-driven-development`,
     `superpowers:verification-before-completion`.
   - Output: green suite with RED→GREEN observed + project gates passing.
4. **Documentation** — what was decided that is not obvious in the code?
   - Skill: `grill-with-docs`; AXON when closing milestones.
   - Output: updated/new ADR + honest README.

When the Definition of Done is met, return to stage 1 for the next slice.

## Definition of Done (per slice)

1. RED→GREEN observed for each new production piece (TDD — Iron Law).
2. `ruff check` and `ruff format --check` clean.
3. `pytest` green, including the reproducibility suite.
4. Non-negotiable invariants touched by the slice verified by test.
5. Non-obvious decision → ADR in `docs/adr/`; new claim in the README → has a
   command that reproduces it (RNF-05).

The non-negotiable invariants are in the kickoff and in the ADRs: dependency direction,
statistical honesty, reproducibility, cost/latency as first-class, offline-first, fail-closed,
documentary honesty.

## Synchronization with AXON (per milestone)

AXON does not run on every slice — it runs when closing a **milestone** (a
cohesive phase or marker). Always incremental: adds new documents and changes,
never re-registers in bulk what has not changed.

- `pb index <repo-root> --ctx personal` — reindexes changed code and
  docs. After that, use `search_code` before a blind `read`.
- `save_adr(project="gnomon-eval", ...)` for each **new** decision in the milestone.
- Session memory capture for the milestone (the Claude Code PostStop hook runs
  `pb session-save`, if configured).

## Outside the loop (for now)

Stage automation (slash-commands, hooks), issue tracker. Future evolution, only
if the lightweight convention proves insufficient.
