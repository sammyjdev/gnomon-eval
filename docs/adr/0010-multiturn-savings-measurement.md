# ADR-010: Multi-turn savings measurement

**Date:** 2026-07-03
**Status:** Accepted

## Context

ADR-009 established that any "AXON saves tokens" claim must come from a
real multi-turn measurement, not from a single-turn A/B and not from the
retired deterministic projection. The missing decision was the exact
measurement design: what each arm sends, which token counts define the
headline, how confidence intervals are computed, and what quality gate keeps
the cost claim from publishing over a quality collapse.

This decision also needs to make the early-turn behavior explicit. A fixed
recall budget can cost more than a forwarded transcript at the start of a
session, so savings may be negative before the baseline transcript grows
enough for the fixed-budget arm to cross over. That crossover is part of the
claim, not a nuisance to hide.

## Decision

ADR-010 defines the session savings harness as a dual-arm replay over scripted
sessions. Each session runs twice:

- AXON arm: zero conversation history, `include_context=true`,
  `recall_max_tokens=2000`. The 2000 is a per-request cap, not a guaranteed
  spend: AXON's retrieval enforces `min(2000, strategy.max_chars / 4)`, an
  effective budget between 1000 and 2000 tokens depending on the strategy
  selected per query. The published claim must state the cap semantics, since
  a smaller effective budget inflates savings relative to a literal reading.
- Baseline arm: full growing transcript forwarded with
  `forward_history=true`, `include_context=false`.

The headline metric is prompt tokens on the input side. Completion tokens are
reported for transparency but are excluded from the savings headline.

Savings at turn `k` is defined per session as:

`1 - axon_prompt_k / baseline_prompt_k`

Per-turn and cumulative savings are aggregated over sessions with
`aggregate_metric`, using the bootstrap-over-sessions method from ADR-008.
Savings may be negative on early turns. The crossover turn, defined as the
first turn whose savings CI is entirely above zero, is part of the published
claim and must be reported alongside the headline.

Final-turn quality is a publish gate, not a side metric. Each arm's final-turn
faithfulness is judged against what that arm actually saw:

- AXON arm: the retrieved contexts returned on the final turn.
- Baseline arm: the forwarded transcript seen by the target on the final turn.

Each session-arm is scored with `judge_runs` samples on the final turn only,
then aggregated over sessions with the ADR-008 bootstrap CI. If the AXON
arm's final-turn faithfulness CI falls entirely below the baseline arm's CI,
the savings result is not publishable.

ADR-010 also records the zero-evidence rule used by the harness. If an arm's
final turn has empty contexts, that session-arm receives faithfulness `0.0`
by metric definition and the judge is not called. This can happen for the
AXON arm when the final question is referential and the bare final-turn query
retrieves nothing. The session stays in the CI and lowers the arm's gate.
Excluding it would bias the gate upward, and crashing would discard already
collected token-cost evidence.

Session provenance is part of the claim: sessions are LLM-drafted from vault
topics anchored to Wave 1's 17 validated cases, then owner-reviewed before
commit.

The retired deterministic projection remains in the AXON repo at
`benchmarks/model.py`, explicitly labeled RETIRED, to preserve the
projection-versus-measurement provenance trail. Its output is not evidence and
must never be cited as measured savings.

## Consequences

**Upsides:**
- The savings claim is tied to real provider prompt-token usage, which matches
  ADR-004's cost-first stance and satisfies ADR-009's measurement bar.
- The curve can honestly show early negative savings and the crossover turn,
  instead of collapsing the story into a single decontextualized percentage.
- The publish gate is conservative: retrieval misses on the final turn lower
  the AXON arm's faithfulness instead of being silently excluded.

**Downsides / trade-offs:**
- The harness is more expensive than Wave 1 single-turn A/B runs because it
  replays full sessions and adds final-turn judge calls per arm.
- The parity gate has a stated asymmetry: the baseline arm is judged for
  faithfulness against its own forwarded transcript, so answers drawing on
  parametric knowledge read as ungrounded. This systematically understates
  baseline faithfulness and makes the gate more permissive. The limitation
  must be published next to the number.
- A good savings curve is not enough on its own. The number is blocked if the
  final-turn faithfulness gate fails.
- The published claim must carry session assumptions and provenance, because
  the measurement is over scripted sessions, not live traffic.

**Neutral / to watch:**
- Completion tokens remain in the report dict for operator visibility, but the
  headline stays scoped to prompt tokens only.
- Early negative turns are expected in some runs. They indicate the crossover
  shape, not a harness error.

## Alternatives considered

| Alternative | Why it was rejected |
|---|---|
| Use total tokens or completion tokens as the headline | The claim under test is input-side savings from fixed recall versus forwarded history; completion tokens are useful telemetry but do not measure that design claim. |
| Drop the quality gate and publish savings alone | A cheaper arm that is less faithful on the final answer is not an acceptable savings claim. Cost without the parity check would repeat the same category error ADR-009 fixed for single-turn runs. |
| Exclude empty-context final turns from faithfulness aggregation | Exclusion would systematically bias the AXON gate upward by removing retrieval misses from the measured population. |
| Crash the run on empty final-turn contexts | Crashing would throw away already collected prompt-token data and prevent the quality gate from reflecting the actual failure mode. |
| Keep citing the deterministic 52.3% figure as the headline | `benchmarks/model.py` is a projection, not a measurement. ADR-009 already retired that category of evidence. |

## Relations

- ADR-010 requires ADR-009.
- ADR-010 relates to ADR-004.
- ADR-010 relates to ADR-008.
- ADR-010 requires AXON request fields `forward_history` and
  `recall_max_tokens`.
