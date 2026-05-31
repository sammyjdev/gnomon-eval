# GNOMON

![GNOMON — Gated Numerical Offline Metrics Over N-cases](docs/assets/gnomon-social.png)

> Evaluates a RAG pipeline and reports quality **with the confidence interval included**, plus cost and latency, running offline with Ollama. Statistical honesty is an invariant, not decoration: no judge metric is reported as a bare number.

The name is the gnomon — the rod of a sundial that casts the shadow you read — and it doubles as a backronym for what the project does: **G**ated **N**umerical **O**ffline **M**etrics **O**ver **N**-cases.

## What it does

Reads a versioned dataset of evaluation cases, runs each case against a target RAG (via adapter), scores the responses with an LLM judge, and reports **faithfulness** and **context precision** — each with a confidence interval — alongside token cost and latency in milliseconds. The same eval runs as a regression test in CI and fails the build when a metric drops below a configurable threshold.

The example evaluates a **MockTarget** (canonical responses) scored by a local **Ollama** judge, with no external dependency or paid API key. Switching to a real RAG that speaks the OpenAI-compat protocol means changing the `[target]` block in `config/example.toml` — not the code.

## Run the evaluation (offline, one command)

Prerequisite: Docker. The example evaluates the MockTarget scored by the real Ollama judge — no external RAG service required.

```bash
# 1. Start Ollama and pull the judge model (first run takes a few minutes)
docker compose up -d ollama
docker compose exec ollama ollama pull llama3

# 2. Run the example evaluation (versioned config + dataset)
docker compose run --rm harness
```

The process exits with code **0 if the gate passes**, **1 if any metric falls below the threshold** in `config/docker.toml` (RF-09) — that is what makes it usable as a regression gate in CI.

### Example output

```
Evaluation report
=================

Quality (judge metrics):
  faithfulness: mean=0.933 [0.800, 1.000] (95% CI, N=3)
  context_precision: mean=1.000 [1.000, 1.000] (95% CI, N=3)

Cost & latency:
  total tokens: 411
  mean latency: 512.0 ms

Per case:
  rpg-001: 137 tokens, 512.0 ms
  rpg-002: 137 tokens, 512.0 ms
  rpg-003: 137 tokens, 512.0 ms
```

`N` is the number of **cases** over which the interval is calculated (the dataset is the sample; see ADR-008). The interval is a bootstrap percentile, bounded to [0,1] by construction. To tighten the CI, add more cases to the dataset — not more judge runs.

### Run on the host (local Ollama, no Docker for the harness)

```bash
pip install -e ".[dev]"
# with Ollama running at localhost:11434 and llama3 pulled:
gnomon --config config/example.toml
```

### Deterministic check (no Ollama, no Docker)

```bash
pip install -e ".[dev]"
python -m pytest -q          # 77 tests: unit, reproducibility, and gate smoke
```

### Reproducibility (RF-11 / RNF-01)

Same seed + same config + same machine produce the same numbers. With a deterministic judge (temperature 0) and a seeded bootstrap, the result is identical across runs. Verified by test:

```bash
python -m pytest tests/reproducibility -q
```

## Architecture

The evaluation core depends on interfaces, never on concrete implementations. Targets and judge depend on the core. Details and diagram in `docs/ARCHITECTURE.md`.

```
Config -> Runner -> [Target adapter] -> target RAG (OpenAI-compat or Mock)
                 -> [Judge] --------> faithfulness + context precision
                 -> [Metrics] ------> mean over cases + CI (bootstrap)
                 -> [Reporting] ----> machine + human report (same source)
                 -> [Gate] ---------> pass/fail in CI (compares ci_low)
```

## Configuration

All configuration lives in versioned TOML files (RNF-07):

- `config/example.toml` — run on the host with Ollama at `localhost:11434`
- `config/docker.toml` — run via `docker compose run --rm harness` (judge points to the `ollama` service on the compose network)

The parameters (seed, judge runs, model, gate thresholds, target) are documented inside the files themselves. Invalid configuration — including a gate threshold outside [0,1] or a missing seed in reproducible mode — fails-closed at load time, before any model call.

## How to run the tests

```bash
pip install -e ".[dev]"
python -m pytest -q                         # full suite: 77 tests
python -m pytest tests/unit -q              # unit tests only
python -m pytest tests/reproducibility -q   # reproducibility only
python -m pytest tests/gate -q              # gate smoke only
ruff check src tests && ruff format --check src tests
```

## Design decisions

The decisions governing the project are in `docs/adr/`:

- **ADR-001** — adapter-based target, so the harness can serve any RAG.
- **ADR-002** — judge nondeterminism, with a confidence interval instead of a single number.
- **ADR-003** — offline-first execution with Ollama, so the example runs at zero cost.
- **ADR-004** — cost and latency as first-class metrics.
- **ADR-005** — retrieved contexts in an OpenAI-compat extension field (fail-closed).
- **ADR-006** — gate compares against the lower bound of the CI (`ci_low`), not the mean.
- **ADR-007** — Ollama judge determinism via `seed+run`, one call per case.
- **ADR-008** — per-case aggregation + bootstrap CI (statistical honesty of `n`).

Full requirements in `docs/REQUIREMENTS.md`. Product overview in `docs/PRODUCT_OVERVIEW.md`. The project development loop is in `docs/DEVELOPMENT_LOOP.md`.

## What it does not do (yet)

Answer relevance, context recall, temporal dashboard, multi-target comparison, and history persistence are left for v2. The architecture accommodates these additions without a rewrite. The detailed backlog, with dependencies and proposed sequencing, is in [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Contributing

Commits follow Conventional Commits. The CI gate runs `pytest` and `ruff check` — PRs must pass both.

## License

MIT — see [LICENSE](LICENSE).
