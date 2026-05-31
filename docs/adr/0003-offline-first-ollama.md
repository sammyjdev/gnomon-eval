# ADR-003: Offline-first execution with Ollama

**Date:** 2026-05-29
**Status:** Accepted

## Context

The harness is a portfolio piece that needs to sell. The governing criterion is that a third party can clone the repository and run the example evaluation in minutes. If the README example requires a paid API key, a portion of evaluators will give up before seeing a number, and the portfolio fails to do its job.

At the same time, the harness must serve real use cases, where the judge may be a more capable paid-provider model.

## Decision

The default path documented in the README runs with Ollama via Docker, with no paid credentials. The complete example -- target and judge -- works locally. The paid-provider path exists behind isolated, optional configuration, selectable without editing code.

Offline execution is the first path to work, not a mode added later. The `docker-compose.yml` brings up Ollama and the harness together, and the example evaluation runs with a single command.

## Consequences

**Upsides:**
- Any evaluator can run the example at zero cost and without registering with a provider, satisfying the sellable-portfolio criterion.
- Development under spec is not held hostage to API costs on every test run.
- The offline path forces the harness not to assume capabilities specific to a paid provider.

**Downsides / trade-offs:**
- Local models via Ollama are less capable and slower than top-tier paid models. The offline judge quality is lower, and execution time is greater, which weighs on the variance run N.
- The evaluator must have Docker and must download the model on first run, which adds an initial wait step.

**Neutral / to watch:**
- The behavioral difference between the offline judge and the paid judge must be visible in the documentation so that operators do not treat the offline number as equivalent to the paid one.

## Alternatives considered

| Alternative | Why it was rejected |
|---|---|
| Default to a paid provider | Would require a credential to run the example, defeating the clone-and-run portfolio criterion. |
| Recorded response fixtures as default | Runs anywhere instantly, but the example stops being "live"; the evaluator does not see the system actually execute, only replay a recording. Kept as a possible test mode, not as default. |
| No paid path | Would limit real use cases, where a more capable judge matters. The optional paid path preserves both uses. |
