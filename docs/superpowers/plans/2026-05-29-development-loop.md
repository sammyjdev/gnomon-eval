# Development Loop + AXON Onboarding — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the development loop playbook (`docs/DEVELOPMENT_LOOP.md`), align the project identity to GNOMON in the docs, and onboard the project into AXON (index + new ADRs + session memory).

**Architecture:** Process and documentation work, not product code. No changes to `src/gnomon/`. Three independent milestones: (1) name reconciliation, (2) playbook, (3) AXON onboarding. Order matters: the name is aligned before indexing so the vault does not capture `rag_eval`.

**Tech Stack:** Markdown, git, AXON (`pb` CLI + MCP tools `mcp__axon__*`).

**Note on TDD:** These tasks produce docs and operational side effects (index, ADRs in the vault), not executable code. The Iron Law of TDD does not apply; each task uses **explicit verification** (grep, command output, `get_adrs`/`search_code`) in place of the red-green cycle.

---

## File map

- Modify: `docs/ARCHITECTURE.md` — lines 1, 83, 102 (title + folder tree)
- Modify: `docs/REQUIREMENTS.md` — line 1 (title)
- Modify: `docs/PRODUCT_OVERVIEW.md` — line 1 (title)
- Modify: `README.md` — lines 1, 15 (title + clone path)
- Create: `docs/DEVELOPMENT_LOOP.md` — the operational loop playbook
- AXON effects (no file in the repo): index in Qdrant, ADRs in the store, session memory

---

## Task 1: Reconcile identity to GNOMON in the docs

Resolves design decision 6. Surgical changes: only identifiers (package path, repo path, clone path) and H1 titles. Prose describing the category ("RAG evaluation harness") stays intact.

**Files:**
- Modify: `docs/ARCHITECTURE.md:1,83,102`
- Modify: `docs/REQUIREMENTS.md:1`
- Modify: `docs/PRODUCT_OVERVIEW.md:1`
- Modify: `README.md:1,15`

- [ ] **Step 1: Fix the folder tree and identifiers in ARCHITECTURE.md**

In `docs/ARCHITECTURE.md`, replace the tree root (line ~83) from:

```
rag-eval-harness/
```

to:

```
gnomon-eval/
```

And the src package (line ~102) from:

```
│   └── rag_eval/             # models and interfaces, no infrastructure dependency
```

to:

```
│   └── gnomon/               # models and interfaces, no infrastructure dependency
```

- [ ] **Step 2: Align the H1 titles to GNOMON**

Replace line 1 of each file:

- `docs/ARCHITECTURE.md`: `# RAG Eval Harness — Arquitetura` → `# GNOMON — Arquitetura`
- `docs/REQUIREMENTS.md`: `# RAG Eval Harness — Requisitos` → `# GNOMON — Requisitos`
- `docs/PRODUCT_OVERVIEW.md`: `# RAG Eval Harness` → `# GNOMON`
- `README.md`: `# RAG Eval Harness` → `# GNOMON`

- [ ] **Step 3: Fix the clone path in the README**

In `README.md` (line ~15), replace:

```bash
cd rag-eval-harness
```

with:

```bash
cd gnomon-eval
```

- [ ] **Step 4: Verify zero occurrences of the old identifier (outside the spec)**

Run:
```bash
grep -rn -e 'rag_eval' -e 'rag-eval-harness' docs README.md | grep -v 'superpowers/specs'
```
Expected: no output (exit 1). The only remaining occurrences live in the design doc at `docs/superpowers/specs/`, which discusses the divergence itself and must keep them.

- [ ] **Step 5: Commit**

```bash
git add docs/ARCHITECTURE.md docs/REQUIREMENTS.md docs/PRODUCT_OVERVIEW.md README.md
git commit -m "docs: alinhar identidade do projeto para GNOMON / gnomon-eval

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Write the docs/DEVELOPMENT_LOOP.md playbook

Operational artifact A: the "how we work in this repo", derived from the design. Leaner than the design doc (which records the why).

**Files:**
- Create: `docs/DEVELOPMENT_LOOP.md`

- [ ] **Step 1: Create the playbook with the full content**

Create `docs/DEVELOPMENT_LOOP.md` with exactly:

```markdown
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
```

- [ ] **Step 2: Verify the playbook matches the design**

Run:
```bash
test -f docs/DEVELOPMENT_LOOP.md && grep -q 'milestone' docs/DEVELOPMENT_LOOP.md && grep -q 'vertical slice' docs/DEVELOPMENT_LOOP.md && echo OK
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add docs/DEVELOPMENT_LOOP.md
git commit -m "docs: playbook do loop de desenvolvimento

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: AXON Onboarding (milestone 0)

Indexes the project in the vault (ctx personal), registers new decisions as ADRs in AXON, and captures Phase 1 memory. The name changes (Task 1) and the playbook (Task 2) are already committed before this step, so the index captures the correct GNOMON identity.

**Files:**
- AXON effects (no versioned file in the repo)

- [ ] **Step 1: Update the project manifest and index**

Run:
```bash
pb scan ~/dev --depth 2
pb index <repo-root> --ctx personal
```
Expected: `scan` lists `gnomon-eval` among the discovered repos; `index` reports indexed files without error.

- [ ] **Step 2: Verify the code entered the vault**

Use MCP tool `mcp__axon__search_code`:
```
search_code(query="aggregate_metric confidence interval t-interval", ctx="personal")
```
Expected: returns nodes from `src/gnomon/metrics/confidence.py` (the `aggregate_metric` function). If it returns empty, indexing failed — investigate before proceeding.

- [ ] **Step 3: Register the open point from ADR-002 (judge N runs)**

Use `mcp__axon__save_adr`:
```
save_adr(
  project="gnomon-eval",
  title="ADR-002 open point: judge N runs per metric",
  context="The metrics use a nondeterministic LLM judge. The CI depends on N runs; more N tightens the CI but multiplies cost/time, critical on offline Ollama.",
  decision="The computability floor is N=2. N=2 is useless for a gate (t critical 12.7 → CI too wide). Provisional recommendation: start with N=8 and re-measure with the real Ollama judge; final N = smallest N whose CI half-width < half the smallest threshold spacing.",
  rationale="Measurement on the Phase 1 slice (StubJudge, σ≈0.046): half-width drops from 0.21 (N=2) to ~0.036 (N=8) and ~0.029 (N=10); elbow at N≈8-10. The real number requires measuring Ollama's variance, not yet done."
)
```
Expected: returns an ADR id.

- [ ] **Step 4: Register the cache granularity decision (ADR-002)**

```
save_adr(
  project="gnomon-eval",
  title="ADR-002 open point: judge cache granularity",
  context="The judge uses a cache for reproducibility. The key granularity decides the trade-off contamination vs savings.",
  decision="A fine key (case, response, judge model, seed) is the default. Only loosen to a coarser key with evidence that the cost justifies it.",
  rationale="The fine key is the safest against cross-contamination of scores. Cache not yet implemented in Phase 1; decision to confirm with the real Ollama cost in Phase 2."
)
```
Expected: returns an ADR id.

- [ ] **Step 5: Register the confidence interval clamp decision**

```
save_adr(
  project="gnomon-eval",
  title="Clamp of the confidence interval to the metric range",
  context="Metrics like faithfulness are bounded to [0,1]. With small N the t critical is large and the raw CI can exceed 1.0 (e.g. ci_high=1.49 for N=2).",
  decision="The mean is reported raw; the CI bounds are clamped to [0,1]. An 'upper bound' of 1.49 for a bounded metric is an artifact of the t critical, not a meaningful claim.",
  rationale="Keeps statistical honesty (uncertainty shows via ci_low) without reporting a meaningless number to the reader. Decision made in Phase 1, not covered by the original docs."
)
```
Expected: returns an ADR id.

- [ ] **Step 6: Verify the ADRs entered the store**

Use `mcp__axon__get_adrs`:
```
get_adrs(project="gnomon-eval")
```
Expected: lists the 3 registered ADRs (judge N runs, cache granularity, confidence interval clamp).

- [ ] **Step 7: Capture Phase 1 memory**

Use `mcp__axon__axon_capture`:
```
axon_capture(
  summary="gnomon-eval Phase 1 delivered: end-to-end vertical slice (typed domain, MockTarget, seeded StubJudge, aggregation with t-interval CI, runner, reporting, fail-closed config). 44 tests green, ruff clean. Non-negotiable invariants 1,2,3,4,6 covered by test. Decisions: CI clamp, N=8 recommendation, GNOMON name.",
  repo="gnomon-eval",
  files=["src/gnomon/metrics/confidence.py","src/gnomon/judge/stub.py","src/gnomon/runner/runner.py","src/gnomon/domain/models.py"],
  symbols=["aggregate_metric","StubJudge","run_eval","MetricResult"]
)
```
Expected: returns a captured decision id.

- [ ] **Step 8: Confirm the AXON footprint**

Use `mcp__axon__get_session_memory`:
```
get_session_memory(project="gnomon-eval")
```
Expected: no longer returns "Nenhuma memória de sessão"; shows the Phase 1 summary.

---

## Self-Review (filled in)

**Spec coverage:**
- Decision 1 (process) → Task 2 (playbook is process, no product code). ✓
- Decision 2 (vertical slice) → documented in the playbook (Task 2 Step 1). ✓
- Decision 3 (lightweight playbook) → "Out of the loop" section of the playbook. ✓
- Decision 4 (ctx personal) → Task 3 Step 1 (`--ctx personal`). ✓
- Decision 5 (AXON per milestone, incremental) → playbook AXON section + Task 3 only registers new decisions. ✓
- Decision 6 (GNOMON name) → Task 1. ✓
- Definition of Done → playbook (Task 2 Step 1). ✓
- AXON onboarding (index + new save_adr + session) → Task 3. ✓

**Placeholders:** no TODO/TBD; all doc content and all tool calls are complete.

**Consistency:** `project="gnomon-eval"` in all AXON calls; `--ctx personal` consistent; symbol names (`aggregate_metric`, `StubJudge`, `run_eval`, `MetricResult`) match Phase 1 code.
