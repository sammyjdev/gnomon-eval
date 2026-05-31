# ADR-005: Retrieved contexts in an OpenAI-compat extension field

**Date:** 2026-05-30
**Status:** Accepted

## Context

The OpenAI chat/completions protocol has no standard field for contexts retrieved by a RAG. RF-03 requires the eval to collect contexts alongside the response in order to compute faithfulness and relevance metrics. Without an explicit field for contexts, the adapter has no way to separate the generated response from the retrieved material.

## Decision

The OpenAI-compat adapter reads contexts from a configurable top-level JSON extension field (`contexts_field`, default `"contexts"`). An absent field is not treated as an empty list — it results in `IncompleteResponseError` (VAL-03). Never a silent empty list.

## Consequences

**Upsides:**
- The fail-closed policy keeps the metric honest: no result without contexts is counted as a valid evaluation.
- The field name is configurable, which allows adapting to targets that already use a different name without modifying the core adapter.
- The semantics are explicit: the operator knows the target must return contexts in that field.

**Downsides / trade-offs:**
- The target RAG must return contexts in that extension field. Targets that do not will require a dedicated adapter or a modification to the server response.
- There is no automatic fallback: if the field is absent, execution fails with an error, not with silent degradation.

**Neutral / to watch:**
- Targets that return contexts embedded in the response text or in nested fields need a dedicated adapter — this adapter assumes a top-level extension field.

## Alternatives considered

| Alternative | Why it was rejected |
|---|---|
| Empty list when the field is absent | Would produce faithfulness metrics computed over empty context, which are useless or misleading; metric honesty requires explicit failure. |
| Fixed, non-configurable field name | Existing targets use varied names; configurability avoids forcing a change on the target server. |
| Extract contexts from response text by heuristic | Fragile and not generalizable; would depend on the output format of each model. |
