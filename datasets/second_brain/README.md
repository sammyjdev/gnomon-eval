# Second-brain evaluation dataset (real cases)

`cases.json` here is the REAL dataset behind the published AXON numbers.
It must contain 15-20 cases (CI width scales ~1/sqrt(N); 5 is marginal,
15+ is defensible). Written by the owner from the actual vault - the
number is only as good as this set.

Each case follows gnomon's `EvalCase` (src/gnomon/domain/models.py):

```json
[
  {
    "id": "sb-001",
    "question": "A real question you would ask your second brain",
    "expected_answer": "The factually correct answer, written by you",
    "expected_contexts": [
      "The vault snippet(s) a perfect retrieval would surface"
    ]
  }
]
```

Rules for good cases:
- Questions you actually asked (or would ask) - not synthetic trivia.
- expected_answer must be verifiable against the vault, not from memory.
- expected_contexts: the minimal snippet(s) that ground the answer.
- Cover different areas of the vault (decisions, projects, references),
  and different difficulty (direct lookup vs multi-note synthesis).
- No case whose answer changed recently (stale ground truth = judge noise).

Validate the file parses before running:
    python -c "from gnomon.dataset.loader import load_dataset; \
    print(len(load_dataset('datasets/second_brain/cases.json')), 'cases')"
