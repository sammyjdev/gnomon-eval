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

To evaluate AXON with these cases:

```bash
gnomon -c config/axon.toml
```

The evaluation will measure:
- **Faithfulness**: Does AXON's answer align with the expected answer?
- **Context Precision**: Are the contexts AXON retrieved actually relevant?
- **Cost**: How many tokens were used per query?
- **Latency**: How fast is AXON responding?
