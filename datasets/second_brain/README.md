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

## Draft candidates (owner review required, issue #6)

`cases.draft.json` holds 13 candidate cases (`sb-018`..`sb-030`) drafted by an
agent to close the RF-09 gate near-miss by growing N from 17 to ~30
(ADR-0006, ADR-0011). It is a SEPARATE file from `cases.json` on purpose: no
config points at it, so it cannot leak into a gate run or a published number
by accident.

**These are drafts, not verified cases.** The agent has no access to the
actual vault, so `expected_contexts` here are paraphrased from session-memory
summaries of real past decisions, not exact vault snippets. Before any case
is promoted into `cases.json`:
- the owner must verify `expected_answer` and `expected_contexts` against the
  real vault content (same provenance discipline as the rest of this file);
- `expected_contexts` must be replaced with the actual verbatim snippet(s);
- only then does the case count toward a published N>=30 measurement.

Do not run the A/B gate against a merged `cases.json` + `cases.draft.json`
count without this review — the "N>=30 owner-validated" acceptance criterion
of issue #6 is not met until it happens.
