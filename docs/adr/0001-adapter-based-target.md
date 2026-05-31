# ADR-001: Adapter-based RAG target

**Date:** 2026-05-29
**Status:** Accepted

## Context

The harness needs a RAG to evaluate, and the example target is RPG Master AI. RPG Master is far from its final version and will change substantially under the hood. If the harness couples to its current implementation, every change to RPG Master breaks the harness example, and the example is what makes the portfolio sell. Moreover, a harness that only evaluates one specific RAG has no value for any client who has their own RAG.

The real constraint is twofold: the example must survive RPG Master's evolution, and the harness must work for any RAG, not just the example one.

## Decision

We define the target through a domain interface, `RagTarget`, and access any concrete RAG through an adapter that implements that interface. The first concrete adapter speaks the OpenAI-compat protocol over REST, which is the protocol RPG Master already exposes. The harness depends on the interface, never on the RAG's internals.

Swapping the evaluated RAG means changing configuration and, at most, choosing a different adapter. No changes to the evaluation core are required.

## Consequences

**Upsides:**
- RPG Master can evolve internally without breaking the harness as long as it maintains the REST contract.
- The harness evaluates any RAG that speaks OpenAI-compat, making it sellable to clients with their own RAG.
- The dependency direction is explicit and verifiable: implementations depend on the domain, not the other way around.

**Downsides / trade-offs:**
- A RAG that does not speak OpenAI-compat requires writing a new adapter. The cost is isolated to the adapter, but it exists.
- The interface hides target-specific capabilities. A RAG's peculiar feature does not surface through the generic interface without deliberate extension.

**Neutral / to watch:**
- The quality of the abstraction is only proven when the second adapter is written. If the second adapter forces a change to the interface, the abstraction was wrong and we revisit this ADR.

## Alternatives considered

| Alternative | Why it was rejected |
|---|---|
| Couple directly to RPG Master AI | Every change to RPG Master would break the harness, and the harness would not serve any other RAG. |
| Support only a fixed protocol with no adapter layer | Would make it impossible to evaluate RAGs with different protocols without rewriting the core. |
