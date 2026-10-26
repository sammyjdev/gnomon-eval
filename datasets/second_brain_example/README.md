# Second Brain Evaluation Cases

This dataset contains example evaluation cases for testing GNOMON with a personal second-brain recall system (AXON).

## Case Structure

Each case in `cases.json` follows the `EvalCase` schema:

```json
{
  "id": "axon-NNN",
  "question": "What is the user asking?",
  "expected_answer": "The ideal/ground-truth answer to the question",
  "expected_contexts": [
    "Context snippet 1 that supports the answer",
    "Context snippet 2 that is relevant to the answer"
  ]
}
```

### Field Guidelines

- **`id`** (string, non-empty): Unique identifier for the case. Use a prefix (e.g., `axon-`) followed by a numeric ID.
  
- **`question`** (string, non-empty): The user's natural question to the recall system. Phrase it as something the user would actually ask their second brain:
  - "What did I decide about X?"
  - "Which projects relate to Y?"
  - "What were the performance targets for Z?"

- **`expected_answer`** (string, non-empty): The ground-truth answer. This should be what the ideal recall system would return. It's the signal against which the judge measures faithfulness (does the target's answer match this meaning?).

- **`expected_contexts`** (list of strings, at least 1): The relevant context snippets that should support the answer. These are used to measure context_precision (what fraction of the target's returned contexts are actually relevant) and other relevance metrics.

## Authoring Best Practices

1. **Ground truth first**: Start with what you know is true (the answer), then extract the contexts that support it.

2. **Multi-context cases**: Use 2-3 expected contexts when the answer draws from multiple sources or topics. This tests whether the recall system can stitch knowledge together.

3. **Realistic questions**: Avoid trivia-style questions. Instead, ask about decisions, relationships, and reasoning:
   - ✓ "What integration decision did I make about..."
   - ✓ "Which components interact with..."
   - ✓ "What did I note about the structure of..."
   - ✗ "What is X?" (too generic)

4. **Consistent contexts**: Each context in `expected_contexts` should be a single, coherent snippet (1-2 sentences). Avoid lists or highly structured formats that won't appear naturally in a recall system's output.

5. **Sufficient coverage**: Aim for 5-10 cases per dataset. They should collectively exercise the system's:
   - Semantic understanding (not keyword matching)
   - Multi-hop reasoning (connecting related concepts)
   - Precision (avoiding irrelevant results)

## Testing with GNOMON

These cases were the toy dataset for the retired AXON chat config
(`archive/axon-chat/axon.toml`), which called `POST /v1/chat/completions` on
`localhost:8765`. That endpoint has been dead since AXON dec-138. The file is
history, not a live AXON eval. The planned AXON evaluation is brief-eval
(`AxonBriefTarget` / brief@budget); see the repository README.

The harness still measures, for any target you point it at:
- **Faithfulness**: Does the answer align with the expected answer?
- **Context Precision**: Are the retrieved contexts relevant?
- **Cost**: How many tokens were used per query?
- **Latency**: How fast is the response?
