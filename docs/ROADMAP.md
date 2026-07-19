# GNOMON — Roadmap v2

> **Status: draft, not committed.** This document is a backlog of candidates for after v1, with dependencies and a **proposed** sequencing (adjustable). It is not an executable plan: when a wave is chosen, it becomes a plan via `superpowers:writing-plans`, following `docs/DEVELOPMENT_LOOP.md`.
>
> **Measurement/dataset ops live as GitHub issues, not here:** #4 (second judge), #5 (session dataset expansion, owner-gated), #6 (single-turn case expansion). This roadmap covers feature waves only.

v1 (delivered) is in `docs/REQUIREMENTS.md`. The "Out of scope for v1" section lists what was deliberately deferred; this roadmap details those items and adds the debt discovered while validating the real path (Ollama judge).

## Non-negotiable invariants inherited by v2

Every item below must preserve:

- **Statistical honesty** (RNF-03) — no judge metric without uncertainty; no inflating `n` (see ADR-008).
- **Dependency direction** (RNF-02) — the core depends on contracts, not implementations.
- **Offline-first** (RF-10) and **reproducibility** (RNF-01).
- **Cost and latency as first-class** (ADR-004), **fail-closed**, and **documentary honesty** (RNF-05).

## Cross-cutting enabler: using the ground truth

`EvalCase` already carries `expected_answer` and `expected_contexts`, but the v1 judge **ignores them** — it scores the response against the *retrieved* contexts (faithfulness) and the relevance of the contexts to the question (context precision). New metrics that compare against the reference ground truth (context recall, answer relevance with reference) **depend** on the pipeline passing that ground truth to the judge/metric.

→ This is the first structural piece of v2: expose `expected_*` to the judge and to the metrics, without violating the dependency direction.

## Backlog A — features deferred from v1

| # | Item | What / why | Touches | Depends on |
|---|------|------------|---------|------------|
| A1 | **Answer relevance** | Metric: does the response answer the question (regardless of being grounded)? Can be with reference (`expected_answer`) or without. | judge (prompt), metrics, V1_METRICS→V2_METRICS | enabler (if with reference) |
| A2 | **Context recall** | Metric: did retrieval bring back **all** necessary contexts? Compares retrieved contexts vs `expected_contexts`. | judge/metric, dataset | **enabler** (ground truth) |
| A3 | **History persistence** | Store run results over time (file: sqlite/jsonl). | new store layer | — |
| A4 | **Temporal dashboard** | Track metrics per run/time. | reporting/CLI, store | **A3** |
| A5 | **Multi-target comparison** | Run N targets and produce a side-by-side comparative report. | runner, reporting, config | (maybe A3) |

## Backlog B — debt and items discovered in v1

| # | Item | Origin | Touches |
|---|------|--------|---------|
| B1 | **`judge_runs=1` for deterministic judge** | ADR-002/008: with `temperature=0` the runs are copies; floor `>=2` (VAL-04) is wasteful. | `config.py`, tests |
| B2 | **Pluggable confidence interval method** | ADR-008 alternatives: Wilson/Jeffreys (binary judge, F1) and hierarchical (noisy judge, C) in addition to the current bootstrap. | `confidence.py`, config |
| B3 | **Persistent judge cache (disk)** | ADR-002 (cache point): currently in-memory, lost between processes; persisting saves cost and reinforces cross-process reproducibility. | `judge/cache.py`, config |
| B4 | **Judge capacity bar / repair** | Real path: `phi3:mini` emitted an invalid key (`faithlessness`) → fail-closed correct, but the entire run fails. Validate/calibrate the judge, or re-prompt/repair with K attempts. | judge, possibly a new calibration stage |
| B5 | **Cost in currency + paid provider** | ADR-004 / RF-10: today only tokens; an isolated paid path and tokens→cost conversion. | metrics, config, target/judge |
| B6 | **Recorded fixtures / per-question MockTarget** | MockTarget returns a fixed response; demos and golden tests would benefit from per-question responses (recorded from a real RAG). | `targets/`, datasets |
| B7 | **More target adapters** | Beyond OpenAI-compat, as real RAG needs arise. | `targets/` |

## Dependencies (summary)

```
enabler (ground truth) ──> A2 (context recall)
                       └─> A1 (answer relevance with reference)
A3 (persistence) ──> A4 (dashboard)
                 └─> A5 (multi-target, optional)
```

B1, B2, B3, B5, B6, B7 are independent of each other and of the rest (can be picked up at any time).

## Proposed sequencing (PROPOSAL — adjust freely)

- **Wave 1 — cheap foundations:** enabler (ground truth), B1 (`judge_runs=1`), B3 (persistent cache), B4 (judge capacity bar). All low-risk, unlocks new metrics, and closes loose ends from v1.
- **Wave 2 — new metrics:** A2 (context recall) and A1 (answer relevance). The core value of v2.
- **Wave 3 — scale and observability:** A3 (persistence) → A4 (dashboard) → A5 (multi-target).
- **When need arises:** B2 (pluggable CI) if a noisy or binary judge is introduced; B5/B6/B7 as real cases appear.

## Open questions (decide when opening v2)

1. Is the v2 focus **new metrics** (Wave 2) or **scale/observability** (Wave 3) first?
2. Answer relevance (A1): **with** reference (uses `expected_answer`) or **without** (question↔response only)?
3. Persistence (A3): local file (sqlite/jsonl, versionable) or a service? Offline-first pulls toward local file.
4. Judge capacity bar (B4): one-shot validation at configuration time, or per-call repair/retry? (retry with a deterministic judge requires varying seed/prompt).

## How this becomes an executable plan

Once a wave (or a vertical slice of it) is chosen, run `superpowers:writing-plans` to produce the task-by-task plan, then execute via `superpowers:subagent-driven-development` — the same loop that delivered v1. Non-obvious decisions become ADRs in `docs/adr/` (next free number: ADR-009).
