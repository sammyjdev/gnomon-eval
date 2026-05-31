# GNOMON

> Measures the quality of a RAG pipeline and reports the honest number — with the uncertainty margin alongside it — without pretending to more confidence than the data can support.

The name is the gnomon of a sundial: the rod that casts the shadow you read. It also closes as the project backronym: **G**ated **N**umerical **O**ffline **M**etrics **O**ver **N**-cases.

## The problem

Engineers shipping a RAG to production have no reliable way to tell whether quality degraded after the last deploy. The evaluation tools that exist report a single quality score, and that number lies for two reasons.

The first is statistical, and more subtle than it looks. The intuition says the problem is that the LLM judge is nondeterministic, so the tool runs the judge N times and reports a mean with a confidence interval. That sounds rigorous. But when the judge runs in reproducible mode — temperature zero — it is deterministic: the N runs are identical copies. Counting identical copies as independent observations narrows the interval by a factor of the square root of N. That is rigour as facade, a guess dressed as measurement.

The uncertainty that actually matters is not the judge rescoring the same case. It is that your test dataset is a small sample of every question users will ever ask. The honest number carries the margin of that sampling: the confidence interval is computed over the cases, not over judge repetitions. Per-case aggregation is what statistical honesty requires (ADR-008). A single score hides this, and the standard "fix" of repeating the judge makes it worse.

The second reason is that quality appears alone, decoupled from cost and latency. The answer with quality 0.95 that consumed four times more tokens and three times more time than the one scoring 0.91 looks better in the report, but may be the wrong choice for the use case. The real decision is never "which answers better" but "which answers well enough for what it costs".

## What it is

A harness that runs against any RAG speaking the OpenAI-compat protocol. It defines a set of evaluation cases with a question, an expected answer, and expected contexts; executes the target RAG against those cases; and computes quality metrics.

The difference is in three points. Every judge-based metric is reported with a confidence interval, never as a bare number, so the reader sees the noise rather than ignoring it. Cost and latency per question appear in the same report as quality, side by side, so the decision can be made on the real trade-off. And the harness runs as a regression gate in CI, failing the build when a metric drops below a configurable threshold, which turns evaluation from a manual report into an automated gate.

The example target is a real RAG system, not a toy. The harness evaluates RPG Master AI through the REST API it already exposes, and switching to a different RAG is a one-line config change.

## Who it is for

Engineers maintaining a RAG pipeline in production who need a reliable signal that quality has not regressed between deploys. Small teams without evaluation infrastructure who do not want to build one from scratch. Anyone comparing models or retrieval strategies who needs numbers with statistical significance, not impressions.

## How it works

1. You define an evaluation dataset: questions, expected answers, and expected contexts, versioned alongside the code.
2. Configure the target by pointing at your RAG via an OpenAI-compat endpoint.
3. Run the harness. It executes each evaluation case against the RAG and collects the response, contexts, token counts, and latency.
4. An LLM judge scores each response for faithfulness and context precision. The N runs per case denoise; the confidence interval comes from the spread **across cases** via bootstrap, not from judge repetition (ADR-008).
5. The report shows each metric with its confidence interval, plus cost and latency aggregated and per question.
6. In CI, the same eval runs as a test and fails the build if a metric crosses the configured threshold.

## Stack

- Language: Python 3.11
- Offline evaluation: Ollama via Docker
- Judge and target: OpenAI-compat protocol
- Tests and gate: pytest
- Lint and formatting: ruff

## Current status

v1 delivered. Real target (OpenAI-compat), Ollama judge, per-case aggregation with bootstrap confidence intervals (ADR-008), regression gate, single-command CLI, offline Docker infrastructure, and CI — 77 tests green, 8 ADRs. The offline execution path with Ollama is the default from the first cut. v2 backlog in `docs/ROADMAP.md`.

## What it does not do (yet)

- Answer relevance and context recall are deferred to v2. The judge architecture already supports them, but they are not in the first cut.
- No temporal trend dashboard. The report is per execution. Persisted history and visualization come later.
- No comparison of multiple targets in a single execution. That will be added when the orchestrator consuming this harness needs it.
- It does not replace human evaluation for high-criticality cases. It measures what can be measured reproducibly and is honest about the margin.

## Links

- Repository: https://github.com/sammyjdev/gnomon-eval
- Technical documentation: see `README.md` and `docs/`
- Architecture decisions: see `docs/adr/`
