# GNOMON AI Engineering Gap Review

This review uses the study map lens to inspect GNOMON as an AI engineering
system. The goal is to make the evaluation story easier to explain and harder
to misread.

## What GNOMON already does well

- Evaluates through an adapter-based target contract.
- Treats judge variance explicitly instead of pretending it does not exist.
- Reports confidence intervals rather than bare means.
- Gates on the lower confidence bound.
- Keeps cost and latency in the reported result.
- Supports offline execution and reproducibility.

## Concept gaps worth addressing

| Concept | Current state | Gap | Why it matters |
| --- | --- | --- | --- |
| Failure taxonomy | Present implicitly in the architecture | No single vocabulary for target, judge, dataset, metric, and gate failures | Faster debugging and clearer run reports |
| Comparison story | Good gate and metrics docs exist | No short one-page explanation of what makes a run pass or fail | Helps humans interpret the output correctly |
| Control discipline | Present in the architecture | Could be stated more explicitly in the docs as a first-class rule | Makes treatment comparisons easier to trust |
| Budget visibility | Included in reports | Not always framed as part of the main evaluation decision | Cost and latency should read like core metrics |
| Study index | Many good docs exist | No single map that ties concepts to the docs that prove them | Easier to teach and reuse |

## Improvements that seem worth considering

1. Add a GNOMON concept index.
   Link each concept to the document that proves it and the metric that
   measures it.

2. Add a failure taxonomy section.
   The run report should say what kind of failure happened, not just that the
   gate failed.

3. Add a short control-versus-treatment note.
   Make the experimental discipline visible to readers, not only to the author.

4. Make budget and latency more prominent in the report.
   They are already measured, so they should be easier to read.

5. Keep the offline-first/reproducibility story explicit.
   That is part of why GNOMON is useful as a harness.

## What not to change

- Do not weaken the gate to make the report look nicer.
- Do not hide confidence intervals behind a simpler mean-only summary.
- Do not add a heavier analysis layer before the current gate story is clearer.

## Most likely next move

The next useful improvement is probably a compact study index that cross-links
the adapter, judge, metrics, reporting, and gate docs to the claims they prove.
