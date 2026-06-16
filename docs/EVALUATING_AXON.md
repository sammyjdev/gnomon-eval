# Evaluating AXON with GNOMON

This guide explains how to evaluate AXON (a personal second-brain recall system) using GNOMON, a framework for measuring RAG system quality offline.

## Overview

- **AXON**: A personal knowledge retrieval system you are building.
- **GNOMON**: An offline evaluation harness that measures answer faithfulness and context precision.
- **Judge**: Ollama (local, free) running llama3—no external API calls, no costs.

## AXON Target Contract

AXON must expose a **REST endpoint compatible with OpenAI's chat completions API**. Specifically:

### Endpoint
```
POST http://localhost:8765/v1/chat/completions
```

### Request Format
Standard OpenAI Chat Completions format:
```json
{
  "model": "axon",
  "messages": [
    {
      "role": "user",
      "content": "What did I decide about the authentication refactor?"
    }
  ]
}
```

### Response Format
```json
{
  "choices": [
    {
      "message": {
        "content": "<your answer to the user's question>"
      }
    }
  ],
  "usage": {
    "total_tokens": <integer: total tokens used in this request>
  },
  "contexts": [
    "<context snippet 1>",
    "<context snippet 2>",
    "..."
  ]
}
```

### Required Fields

1. **`choices[0].message.content`** (string): The answer AXON generates in response to the user's question. This is measured for faithfulness against expected answers.

2. **`usage.total_tokens`** (integer): The total token count for the request. Used to measure cost efficiency (lower is better).

3. **`contexts`** (list of strings, top-level): The context snippets AXON retrieved to generate the answer. Used to measure context_precision (what fraction of retrieved contexts are actually relevant to the question).

### Example Flow

1. User asks: "Which projects relate to the semantic search infrastructure?"
2. AXON retrieves relevant notes/documents
3. AXON returns:
   ```json
   {
     "choices": [{
       "message": {
         "content": "AXON and the vector embedding service use semantic search. AXON consumes embeddings from the centralized vector store."
       }
     }],
     "usage": {"total_tokens": 150},
     "contexts": [
       "AXON integrates with vector embedding service for semantic search",
       "Vector embedding service provides centralized search infrastructure"
     ]
   }
   ```

## Running the Evaluation

### Prerequisites

1. **AXON running**: AXON must be listening on `http://localhost:8765/v1/chat/completions`.

2. **Ollama running**: Ollama must be running locally with llama3 available.
   ```bash
   ollama run llama3
   ```

3. **GNOMON installed**: From the gnomon-eval directory:
   ```bash
   pip install -e .
   ```

### Execute the Evaluation

```bash
gnomon -c config/axon.toml
```

This will:
- Load `datasets/second_brain_example/cases.json` (5 example test cases)
- Send each question to AXON's `/chat/completions` endpoint
- Judge each response with Ollama (llama3) 8 times to build confidence
- Measure:
  - **Faithfulness**: Does AXON's answer match the expected answer in meaning?
  - **Context Precision**: What fraction of AXON's retrieved contexts are relevant?
  - **Cost**: Total tokens used across all queries
  - **Latency**: Response time per query

### Output

The evaluation produces a report including:
- Mean scores with 95% confidence intervals for each metric
- Per-case costs and latency
- Summary judgment of pass/fail against gate thresholds

Example:
```
Faithfulness:      0.82 [0.71, 0.91] (N=5, runs=8)
Context Precision: 0.76 [0.64, 0.88] (N=5, runs=8)
Total Tokens:      1247
Mean Latency:      42.3ms

Gate Status:
  faithfulness (threshold 0.75):      PASS (0.82 >= 0.75)
  context_precision (threshold 0.70): PASS (0.76 >= 0.70)
```

## Configuration

The evaluation is controlled by `config/axon.toml`:

```toml
[target]
kind = "openai_compat"          # AXON implements OpenAI-compat interface
base_url = "http://localhost:8765/v1"
model = "axon"                  # Model name to send in requests
contexts_field = "contexts"     # Top-level JSON field containing context list

[judge]
provider = "ollama"             # Local judge, no API key needed
model = "llama3"                # Which Ollama model to use

[gate]
faithfulness = 0.75             # Must achieve 75%+ faithfulness to pass
context_precision = 0.70        # Must achieve 70%+ context precision to pass

[eval]
judge_runs = 8                  # Run judge 8 times per case for confidence
seed = 42                        # Fixed seed for reproducibility
```

### Adjusting Thresholds

- Raise `gate.faithfulness` to require higher answer accuracy.
- Raise `gate.context_precision` to require fewer irrelevant retrievals.
- Increase `eval.judge_runs` for tighter confidence intervals (more expensive in compute time).

## Cost and Privacy

- **$0 cost**: Ollama runs locally; no external API calls.
- **Fully offline**: All evaluation happens on your machine.
- **Private**: AXON answers and contexts never leave your system.

## Authoring New Test Cases

Add cases to `datasets/second_brain_example/cases.json` following the schema in `datasets/second_brain_example/README.md`.

Each case should:
- Ask a question a user would actually pose to their second brain
- Provide a ground-truth answer
- List the expected context snippets that should support that answer

Example:
```json
{
  "id": "axon-006",
  "question": "What infrastructure decisions affect the latency SLO?",
  "expected_answer": "Caching decisions and database indexing strategy are critical to meeting the 100ms p95 latency target.",
  "expected_contexts": [
    "Caching strategy: Redis L1, DynamoDB L2, with 5m TTL",
    "Database indexes on user_id and context_id for 10ms query time"
  ]
}
```

## Troubleshooting

### AXON connection refused
- Ensure AXON is running and listening on `http://localhost:8765`.
- Check that the OpenAI-compat endpoint is `/v1/chat/completions`.

### Ollama connection refused
- Start Ollama: `ollama serve` (or equivalent for your OS).
- Ensure llama3 is downloaded: `ollama pull llama3`.

### Missing contexts field in response
- AXON must include a top-level `"contexts"` field with a list of strings.
- This is separate from `choices[0].message.content` (the answer).

### Low faithfulness scores
- Review your expected answers in the test cases.
- Ensure AXON's answer generation is semantically aligned with the expected answer.
- Consider adding more judge runs for better signal.

## See Also

- `config/example.toml`: Example with a mock target (no external system needed).
- `src/gnomon/domain/models.py`: Definition of EvalCase and other core types.
- `src/gnomon/targets/openai_compat.py`: Implementation of OpenAI-compat target handler.
