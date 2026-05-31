# ADR-007: Ollama judge determinism via seed+run

**Date:** 2026-05-30
**Status:** Accepted

## Context

RNF-01 is reproducibility within measured variance, not bit-exact. The Ollama judge needs a deterministic sequence per declared seed so that two runs with the same seed produce comparable results. Without fixing seed and temperature, the judge introduces uncontrolled variance that is confounded with the real variance of the RAG under evaluation.

## Decision

The judge fixes `options.seed = seed + run` and `temperature = 0.0` per call. This produces a fixed sequence for a given model and host. All v1 metrics are scored in a **single model call per `score()`** (the model returns a JSON object with one key per metric), not one call per metric — the real call cost is `len(cases) * judge_runs`, with no multiplier per metric (RNF-06). The reproducibility suite continues using the StubJudge (purely deterministic); reproducibility of the real judge is verified as a variance tolerance, not value equality. The cache (whose key includes seed and run) reinforces stability within the same machine.

## Consequences

**Upsides:**
- Deterministic sequence per declared seed: repeating a run with the same seed produces the same result within the same model and host.
- The cache, by including seed and run in the key, avoids recomputation and reinforces consistency in partial reruns.
- The separation between StubJudge (tests) and real judge (production) keeps tests fast and independent of Ollama.

**Downsides / trade-offs:**
- Switching model or host may change the numbers — expected and reported via CI. Reproducibility is guaranteed within an environment, not across environments.
- `temperature = 0.0` in Ollama is not an absolute guarantee of determinism across all inference backends; seed is the primary mechanism.

**Neutral / to watch:**
- The combination `seed + run` (not just `seed`) is intentional: each run within an execution receives a different seed, which prevents all runs for a question from being identical to each other, preserving variance measurement.

## Alternatives considered

| Alternative | Why it was rejected |
|---|---|
| Fixed seed equal for all runs | All runs for a question would be identical; measured variance would be zero and the CI would be useless. |
| No fixed seed or temperature | Introduces uncontrolled variance in the judge, which is confounded with RAG variance and inflates the CI without real value. |
| Verify reproducibility by bit-exact equality | Incompatible with RNF-01 and with the reality of quantized models on varied hardware; variance tolerance is the correct metric. |
| One model call per metric | Multiplies cost and latency by the number of metrics per run, critical in offline Ollama (ADR-004). A single call that scores all metrics via JSON is cheaper; the cost of a slightly larger prompt is negligible compared to a second full inference. |
