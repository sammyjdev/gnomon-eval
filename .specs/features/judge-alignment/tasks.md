# Tasks: judge alignment

Spec: `.specs/features/judge-alignment/spec.md`. One task = one `forge task`
pass (issue, worktree, red test first, gate, quench, PR). Task 5 is
owner-gated and opens as `agent:blocked`.

- [ ] **Task 1: Persist per-case answer and contexts in run and panel report JSON**
  - Issue: #71
  - Depends on: none
  - Requirements: JA-01, JA-02, JA-03, NFR-01, NFR-04
  - Acceptance: a `run_eval` report and a `run_panel_eval` report serialized with `to_dict` / `panel_to_dict` carry `responses: [{case_id, answer, contexts}]` matching what the target returned, in case order; every pre-existing key and the text reports are byte-identical to before; a report built without responses serializes `responses: []`; the contract doc names the key; no existing test file assertion changed.

- [ ] **Task 2: Known-fail perturbation probes, TNR floor and pass floor in B4 screening**
  - Issue: #72
  - Depends on: none
  - Requirements: JA-04, JA-05, JA-06, JA-07, NFR-03, NFR-04 (A2 exceptions only)
  - Acceptance: the generator is a pure deterministic function covering `number_swap`, `identifier_swap`, `unsupported_claim`, with tests that a non-applicable kind emits nothing, that no output equals the original, and that swapped tokens are absent from every context; B4 rejects a stub always-1.0 judge and a stub always-0.0 judge, rejects a candidate with no known-fail probes, rejects a candidate that scores any known-fail probe at or above `grounded_threshold`, rejects a candidate with no pass probe at or above `pass_floor`, and records both parameters, known-fail count, TNR and the pass-floor count in evidence; either parameter missing or outside [0, 1] is rejected; ADR-0012 amendment note (both floors, dormant until a driver passes probes) and the `docs/panel/selection.md` link are committed; only the two A2-authorized test edits exist.

- [ ] **Task 3: Labeled-verdict format, fail-closed loader, alignment metrics, disagreement list and self-agreement**
  - Issue: #73
  - Depends on: none
  - Requirements: JA-08, JA-09, JA-10, JA-11, JA-16, JA-17, NFR-02, NFR-03, NFR-05
  - Acceptance: the loader takes one or more files and raises a named error naming the file and item for every JA-09 case, including `[]`, a non-array document, a null verdict, an empty `rubric_version`, a cross-file uniqueness violation, a non-fail negative or perturbation item, and mixed `rubric_version` across real arms; `negative:` arms accept several items per case with different answers; the alignment function returns per judge for each arm and for `real` the label counts, AUC with a stratified seeded bootstrap interval, TPR and TNR with Wilson intervals, and kappa with a stratified seeded bootstrap interval, and never a stratum pooling perturbation or negative arms with real arms; hand-computed fixtures pin AUC (including ties), TPR, TNR, Wilson bounds and kappa; a missing label class yields `null` plus a reason for the statistics that need it while the other strata still compute; the output echoes the rubric versions; every bootstrap interval is `null` with a reason when a label class has fewer than 5 items, while counts, point estimates and Wilson intervals still report; the disagreement list holds exactly the real-arm items whose thresholded verdict differs from the owner's, sorted by `(arm, case_id)`; self-agreement returns the 2x2 counts and kappa with interval, and fails closed on mismatched answer/contexts or fewer than 2 joined pairs; no output key is an accuracy or agreement rate; same inputs and seed give identical output.

- [ ] **Task 4: gnomon align command, labeling-template export and self-agreement CLI**
  - Issue: #74
  - Depends on: Task 1, Task 2, Task 3
  - Requirements: JA-12, JA-13, JA-14, JA-18, NFR-02, NFR-03
  - Acceptance: with a `stub` panel, `gnomon align -c <cfg> --labels <a> --labels <b> --threshold 0.75 --json` prints the Task 3 report, the disagreement list and the per-item `scores` list, and the declared call count `items x members x judge_runs` before any judge call, and a spy judge confirms exactly that many calls; an unknown `case_id`, a mismatched `question`, a missing `--threshold` or a judge error exits non-zero with no report; a null `eval.seed` exits non-zero before any judge call; two runs over the same inputs give byte-identical `--json` output, `scores` included; `--export OUT_DIR` over a Task 1 report writes `labels.todo.json` (one unlabeled item per response, no judge scores) and `perturbations.json` (construction items with the perturbed expected answer and the case's expected contexts), fails closed naming the file when `responses` is absent or empty, and refuses to overwrite an existing file in `OUT_DIR`; `labels.todo.json` with every verdict, critique and `rubric_version` filled loads with the Task 3 loader together with `perturbations.json`; `--self-agreement FIRST SECOND` prints the JA-17 result and exits non-zero on its failures.

- [ ] **Task 5: Owner runs the pre-registered alignment protocol and records the numbers**
  - Issue: #75
  - Depends on: Task 4
  - Requirements: JA-15
  - Blocked on: owner labeling (about 34 ON + 34 OFF real items, 15 first-pass items re-labeled, 15-20 hard negatives, 20 delayed re-labels), live AXON `serve-http` target with `AXON_COMPLETION_MODEL` pinned, `DEEPINFRA_API_KEY`
  - Acceptance: `docs/panel/alignment.md` holds the pre-registration (spec protocol step 1) committed before the first label; the generator model is recorded and same-family judges flagged; fresh ON and OFF run JSONs carry `responses`; the first-pass rubric changes and the frozen `v2` are recorded; every real item is labeled under `v2` with a critique; hard negatives exist as `negative:owner`; the owner self-agreement re-label happened before any `gnomon align` run and its kappa is recorded; the double-run byte comparison is recorded; per judge per stratum AUC and TPR/TNR/kappa with intervals and label counts are recorded with the reproducing commands (RNF-05); every disagreement carries one cause code and counts per judge per cause are reported; conclusions come only from the pre-registered primary statistic per claim with non-overlapping intervals, `null` or overlapping intervals are reported as inconclusive, and the GLM-4.6 question is answered from cause codes on its false fails; any deviation from the pre-registration is recorded as a deviation.
