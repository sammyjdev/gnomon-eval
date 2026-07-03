# A/B recall results - 2026-07-02

Setup: dataset `datasets/second_brain/cases.json` (17 owner-validated cases), target
AXON `/v1/chat/completions` with completion pinned to `ollama/llama3.1:8b` (GPU box),
judge `llama3.1:8b` (same box), `judge_runs = 8`, seed 42, 95% CI. Replicates:
3x recall-on, 2x recall-off, sequential, same stack.

## Validated claim

AXON recall lifts faithfulness from 0.40-0.52 (no-recall baseline, means across
replicates) to 0.72-0.76 (means across 3 replicates, 95% CI per run, N=17), at a
measured cost of +2151 real input tokens per turn. In every paired run the on/off
faithfulness CIs do not overlap. Reproduce: `gnomon -c config/axon-recall-on.toml`.

## Replicates

| run | faithfulness | context_precision | total tokens |
|-----|--------------|-------------------|--------------|
| on-1 | 0.755 [0.713, 0.795] | 0.781 [0.710, 0.848] | 42433 |
| on-2 | 0.725 [0.674, 0.772] | 0.712 [0.651, 0.773] | 41675 |
| on-3 | 0.718 [0.654, 0.773] | 0.774 [0.702, 0.850] | 41817 |
| off-1 | 0.400 [0.259, 0.553] | (meaningless: no contexts) | 3015 |
| off-2 | 0.524 [0.353, 0.665] | (meaningless: no contexts) | 3078 |

Recall input cost: +2151 prompt tokens/turn in run 1 and run 2 telemetry
(identical - retrieval is deterministic for a fixed dataset).

## Validity checks (runbook)

- usage_source: 85/85 telemetry records `provider` (zero estimates, zero LLM failures).
- Single model both arms and both roles: `ollama/llama3.1:8b`.
- Stability: faithfulness means mutually within CIs across all 3 on-replicates and
  both off-replicates. PASS.

## Caveats (stated, not hidden)

- context_precision run-to-run judge noise slightly exceeds the within-run CI
  (run-2 mean 0.712, CI [0.651, 0.773] excludes run-1/run-3 means by <= 0.008).
  Report it as the replicate range 0.71-0.78, not a single point estimate.
- Judge and target completion share the same model (llama3.1:8b): same-family
  self-preference bias is possible. It affects both arms equally, so the DELTA
  is more robust than the absolute scores. A different judge model is the
  natural hardening step.
- This is a single-turn quality + cost measurement. It says nothing about token
  savings (ADR-009); the Wave 2 multi-turn harness owns that claim.
