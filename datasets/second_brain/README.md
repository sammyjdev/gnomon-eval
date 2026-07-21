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

## Draft review outcome (2026-07-21, issue #6)

The 13 drafts (`sb-018`..`sb-030`) were validated against the real vault
(delegated review, recorded in issue #6). Outcome:

- **Promoted to `cases.json` (4)** - `sb-018`, `sb-023`, `sb-026`, `sb-028`,
  each rewritten to the scope the vault actually supports and with
  `expected_contexts` replaced by verbatim snippets from the source notes
  (afya-prep-3-pilares.md, daily/2026-07-13.md, forge-closed-agentic-loop/
  CONTEXT.md, AXON/Decisions/dec-032.md + the 2026-05-28 session note).
  `sb-018`/`sb-026`/`sb-028` were narrowed: exact counts/dates and claims
  present only in session memories (119/34 counts, 2026-06-29 reverification,
  "~/code/forge retired", the Grafana/Micrometer contrast) were dropped.
- **Rejected (9)** - `sb-019`..`sb-022`, `sb-024`, `sb-025`, `sb-027`,
  `sb-029`, `sb-030`: zero vault grounding (the knowledge lives only in
  Claude session memories / machine-local state). Promoting them would make
  the eval measure "does the vault contain X" instead of retrieval quality.
  If any of that knowledge deserves vault status, write the vault note first,
  then redraft the case. `cases.draft.json` was removed with this review.

Current N = 21 owner-validated cases. The N>=30 target of issue #6 remains
open - it now requires either new vault-grounded drafts or new vault notes.
