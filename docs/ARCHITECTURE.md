# GNOMON — Architecture

Architecture document for v1. Describes the components, the dependency direction between them, the data flow of a run, and the repository folder structure.

## Organizing principle

The harness is organized by dependency direction. The evaluation core knows nothing about any specific target or any judge provider. It depends on contracts. The concrete target and judge implementations depend on the core, never the other way around. This rule is what allows the target RAG to evolve independently: as long as the contract holds, RPG Master AI can change internally without breaking the harness.

## Components

### Domain
The typed heart of the system. Contains models for the evaluation case, target response, metric score, and result with confidence interval. Imports nothing from infrastructure. Defines the interfaces that the rest of the system implements.

### Target adapter
Translates between the domain's `RagTarget` contract and a concrete RAG. The first adapter speaks the OpenAI-compat protocol over REST. It receives a question and returns the response, contexts, tokens, and latency in the domain format. A new target is a new adapter — no changes to the core.

### Judge
Scores a case/response pair on the quality metrics. Encapsulates the seed control and cache that underpin reproducibility. Runs the scoring N times to feed the variance calculation. The judge provider is configurable; the default offline mode uses Ollama.

### Metrics
Calculates faithfulness and context precision from the judge scores, and aggregates cost and latency from the target responses. Always produces a `MetricResult` with a mean and confidence interval — never a bare number.

### Runner
Orchestrates a run. Reads the dataset, iterates the cases, calls the target via the adapter, calls the judge, aggregates the metrics, and assembles the report. This is the point where all pieces meet, and the only component that knows all of them.

### Reporting
Serializes the run result into machine-readable and human-readable formats. Same data source for both formats, so there is no divergence between what a machine reads and what a person sees.

### Gate
Compares the result against per-metric thresholds and decides pass or fail. Exposed as a test to run in CI. This is the layer that turns evaluation into a regression gate.

### Config
Loads external configuration: target endpoint and type, judge model, seed, variance runs N, and gate thresholds. Validates the configuration before any model call.

## Dependency direction

```
                 +-------------------+
                 |      Domain       |
                 |  (modelos +       |
                 |   interfaces)     |
                 +-------------------+
                   ^   ^   ^   ^   ^
                   |   |   |   |   |
     +-------------+   |   |   |   +-------------+
     |             +---+   |   +---+             |
     |             |       |       |             |
+----------+  +--------+  +-------+  +--------+  +---------+
| Target   |  | Judge  |  |Metrics|  | Gate   |  |Reporting|
| adapter  |  |        |  |       |  |        |  |         |
+----------+  +--------+  +-------+  +--------+  +---------+
     ^             ^          ^          ^           ^
     |             |          |          |           |
     +-------------+----+-----+----------+-----------+
                        |
                   +---------+
                   | Runner  |
                   +---------+
                        ^
                        |
                   +---------+
                   | Config  |
                   +---------+
```

All arrows point to Domain. Domain points to no one. Runner depends on the implementations; the implementations depend on Domain. No concrete implementation depends on another concrete implementation.

## Data flow of a run

1. Config loads and validates the configuration. Invalid configuration stops the run before any model call.
2. Runner reads the dataset. A malformed dataset stops the run with an error pointing to the offending case.
3. For each case, Runner calls the Target adapter with the question.
4. Target adapter queries the concrete RAG and returns the response, contexts, tokens, and latency in the domain format.
5. Runner passes the case/response pair to the Judge.
6. Judge scores N times under a controlled seed, using the cache for scores already calculated.
7. Metrics calculates faithfulness and context precision with a confidence interval from the N scores, and aggregates cost and latency from the responses.
8. Reporting serializes the result in both formats from the same source.
9. Gate, when running in CI, compares the result against the thresholds and decides pass or fail.

## Folder structure

```
gnomon-eval/
├── README.md
├── pyproject.toml
├── ruff.toml
├── docker-compose.yml          # Ollama + harness for offline execution
├── Dockerfile
├── .github/
│   └── workflows/
│       └── ci.yml              # ruff, pytest matrix, gate smoke
├── docs/
│   ├── PRODUCT_OVERVIEW.md
│   ├── REQUIREMENTS.md
│   ├── ARCHITECTURE.md
│   └── adr/
│       ├── 0001-adapter-based-target.md
│       ├── 0002-judge-nondeterminism.md
│       ├── 0003-offline-first-ollama.md
│       ├── 0004-cost-latency-first-class.md
│       ├── 0005-openai-compat-contexts.md
│       ├── 0006-gate-on-ci-low.md
│       ├── 0007-ollama-judge-determinism.md
│       └── 0008-case-level-bootstrap-ci.md
├── src/
│   └── gnomon/
│       ├── domain/             # models and interfaces, no infrastructure dependency
│       ├── targets/            # adapters; openai_compat is the first
│       ├── judge/              # judge, seed control, cache
│       ├── metrics/            # faithfulness, context precision, cost/latency aggregation
│       ├── runner/             # run orchestration
│       ├── reporting/          # machine and human serialization
│       ├── gate/               # comparison against thresholds
│       └── config/             # config loading and validation
├── datasets/
│   └── rpg_master_example/     # versioned ground truth for the example
└── tests/
    ├── unit/                   # domain, metrics, config, gate with mocks
    ├── integration/            # runner against target via adapter
    └── reproducibility/        # same seed produces same result within variance
```

## Design decisions

The decisions governing this architecture are recorded in ADRs:

- **ADR-001** justifies the adapter-based target over direct coupling to RPG Master AI.
- **ADR-002** defines how the system handles nondeterminism in the LLM judge.
- **ADR-003** explains why the default path is offline with Ollama.
- **ADR-004** records why cost and latency are first-class metrics.
- **ADR-005** extends contexts for OpenAI-compatible targets.
- **ADR-006** gates on the CI lower bound, not the mean.
- **ADR-007** documents the Ollama judge determinism strategy.
- **ADR-008** records the case-level bootstrap confidence interval.

## Test map for the structure

Tests reflect the dependency direction. Unit tests cover domain, metrics, config, and gate in isolation with mocks — no network, no model. Integration tests cover Runner against a target through the adapter. Reproducibility tests verify that the same seed produces the same result within the reported variance, which is the executable verification of RNF-01.
