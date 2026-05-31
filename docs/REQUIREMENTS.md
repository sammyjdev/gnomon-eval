# GNOMON — Requirements

Requirements document for v1. Each requirement has an identifier for tracing across spec, tests, and ADRs. Functional requirements describe what the system does. Non-functional requirements describe the quality constraints that govern how it does it. Validations describe what the system rejects and how.

## Functional requirements

### RF-01 — Evaluation dataset definition
The system reads a versioned evaluation dataset of cases from a file. Each case contains a question, an expected answer, and a list of expected contexts. The dataset is the source of truth for evaluation and lives alongside the code, not in an external database.

### RF-02 — Target RAG via adapter
The system evaluates any RAG accessible through an adapter. The first concrete adapter speaks the OpenAI-compat protocol over REST. Switching targets means changing configuration, not harness code.

### RF-03 — Case execution against the target
For each case in the dataset, the system sends the question to the target and collects the response, retrieved contexts, tokens consumed, and latency in milliseconds.

### RF-04 — Scoring by LLM judge
An LLM judge scores each case/response pair on the v1 quality metrics. The judge runs under seed control and cache to support reproducibility.

### RF-05 — v1 metrics
The system calculates faithfulness (the response is grounded in the retrieved contexts) and context precision (the retrieved contexts are relevant to the question).

### RF-06 — Judge variance with confidence interval
The system runs the judge scoring N times per metric and reports the mean with a confidence interval. No judge-based metric is emitted as a single number.

### RF-07 — Cost and latency per question
The system reports tokens and latency per question and as aggregates. These outputs appear in the same report as quality metrics, not in a separate report.

### RF-08 — Run report
The system produces a machine-readable and human-readable report containing, for each metric, the mean, lower and upper bounds of the confidence interval, and the number of judge runs, plus the cost and latency numbers.

### RF-09 — Regression gate
The system exposes the evaluation as an executable test that fails when a metric drops below a configurable threshold. The threshold is defined per metric in configuration.

### RF-10 — Offline execution by default
The execution path documented in the README runs with Ollama via Docker, without a paid API key. The path with a paid provider exists behind isolated, optional configuration.

### RF-11 — Example reproducibility
The README example run produces, within the reported variance, the same numbers on every run on the same machine with the same configuration and seed.

## Non-functional requirements

### RNF-01 — Reproducibility
Same input, same seed, and same judge model produce the same result within the measured and reported variance. Reproducibility is a project invariant, verified by test, not a documentation promise.

### RNF-02 — Dependency direction
The harness depends on targets by contract (the adapter interface), never on internals of a concrete implementation. A target is defined by interface. Evolution of the target RAG does not break the harness as long as the public contract holds.

### RNF-03 — Statistical honesty
The system never presents a judge-based quality number without an uncertainty margin. A single score for a nondeterministic metric is treated as a defect, not an acceptable simplification.

### RNF-04 — Execution accessibility
A third party clones the repository, brings up the environment with Docker, and runs the example evaluation with one command. No step in the default path requires a paid credential or infrastructure the evaluator does not have locally.

### RNF-05 — Documentation and code consistency
Every claim in the README has a command that reproduces it. A claim without a corresponding command is treated as a documentation defect.

### RNF-06 — Predictable execution cost
The number of judge calls per run is an explicit function of the dataset size and the variance runs N. The system makes no model calls outside this declared calculation.

### RNF-07 — Configuration isolation
Target configuration, judge model, seed, number of runs, and gate thresholds live in external configuration. Changing any of them does not require editing source.

### RNF-08 — Verified code quality
The project runs lint and tests in continuous integration. Lint, compilation, and a green test suite are a release barrier.

## Expected validations

### VAL-01 — Malformed dataset fails closed
A missing dataset, or a dataset with a case missing a question, expected answer, or expected contexts, rejects the run with an explicit error pointing to the offending case. The system never evaluates partially in silence.

### VAL-02 — Unreachable target fails explicitly
A target that does not respond, responds outside the OpenAI-compat protocol, or exceeds the timeout produces a named error that distinguishes a configuration failure from a runtime target failure.

### VAL-03 — Incomplete target response
A response missing contexts, a token count, or latency is rejected or flagged according to the policy defined in the ADR — never treated as a silent zero that contaminates the metric.

### VAL-04 — Insufficient runs N for confidence interval
A judge runs N below the minimum required to calculate a confidence interval rejects the configuration with a message indicating the acceptable minimum.

### VAL-05 — Misconfigured gate threshold
A regression threshold outside the valid range for the metric (for example, a negative threshold or one above the maximum possible) rejects the configuration before any model call.

### VAL-06 — Missing seed in reproducible mode
A run in reproducible mode without a declared seed fails, rather than generating an implicit seed that would break reproducibility across runs.

### VAL-07 — Inconsistent cache
A cache entry whose key does not match the defined identity tuple (case, response, judge model, seed) is treated as a miss, never as a hit that would return a score from the wrong context.

## Traceability

| Requirement | Related ADR |
|---|---|
| RNF-02, RF-02 | ADR-001 (adapter-based target) |
| RNF-01, RNF-03, RF-04, RF-06, VAL-06, VAL-07 | ADR-002 (judge nondeterminism) |
| RF-10, RNF-04 | ADR-003 (offline-first with Ollama) |
| RF-07, RNF-06 | ADR-004 (cost and latency as first-class metrics) |

## Out of scope for v1

Answer relevance, context recall, temporal dashboard, multi-target comparison, and run history persistence are not part of v1. The architecture accommodates adding them without a rewrite, but the initial release does not include them.
