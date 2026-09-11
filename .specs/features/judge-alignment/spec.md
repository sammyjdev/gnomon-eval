# Judge alignment: measure whether the judges are right, not whether they agree

Blueprint pass: `forge blueprint`, 2026-09-10, base `master` @ `3798968`.
Revised the same day after cross-review rounds 1 and 2 (GLM-5.3, see "Cross-review").
Classification: **public/backlog**, **Medium** (5 tasks, no separate design doc).

## Problem

Every judge validation in this repo is agreement-based: inter-judge Pearson
(`metrics/disagreement.py`), correlation to consensus (METRON
`judge-calibration/REPORT.md`, which itself says "agreement is not accuracy"),
or judge vs `AnchorScorer`. No judge verdict has ever been compared with an
owner label. `docs/panel/initial-run.md` shows the cost: on the same responses,
faithfulness is Llama 0.749 vs GLM-4.6 0.382, pairwise Pearson 0.30-0.48,
per-case deltas 0.8-1.0 on about a third of cases, and nobody can say which
judge is right. Its follow-up "per-case review of GLM-4.6 harsh verdicts" never
ran, and cannot run on that draw (see below).

Verified in the code during this pass (ore) and during review verification:

- `run_eval` and `run_panel_eval` receive a `RagResponse` per case and drop
  `answer`/`contexts`; `to_dict` and `panel_to_dict` emit only
  `per_case[{case_id, total_tokens, latency_ms}]`. The committed run JSONs
  (`docs/panel/runs/2026-07-22-*.json`) are `panel_to_dict` output wrapped with
  `arm`/`n_cases`/`gate` by a driver outside this repo (METRON runners call
  `run_panel_eval`/`panel_to_dict`; commit `610d249` touches only docs).
- `gnomon.cli` has no panel command. `screen_candidate` has no caller in `src/`
  or `scripts/`: B4 model calls were made by an out-of-repo script, and B4
  screens raw completion text for JSON/schema only.
- B4 probes only `expected_answer` scored against `expected_contexts` (the pass
  class), and never checks the score. An always-pass judge passes B4 (`phi-4`
  returned 1.0 on 30/30 cases of one METRON arm), and so does an always-fail
  judge. Neither TNR nor TPR is ever tested.
- `tests/unit/test_panel_reporting.py:67` pins `per_case` by exact equality;
  `tests/unit/test_screening.py:96` and `:122` pin the current B4 bar and the
  exact evidence dict. No test pins the whole report dict. The clean probe
  fixture scores 0.8 on every metric.
- `disagreement._pearson` returns `0.0` on degenerate input. Alignment code must
  not copy that: an undefined statistic is reported as undefined, never as 0.0.
- ADR-0008 reserves Wilson for a binarized judge. This feature binarizes only
  inside the alignment report, through a declared threshold; the gate and the
  bootstrap CI are untouched, so ADR-0008 does not change.
- `OpenAICompatJudge` defaults `temperature=0.0` and `cli.build_judge` does not
  override it, so extra `judge_runs` are copies (ADR-008). Whether DeepInfra is
  actually deterministic at temperature 0 has never been measured.
- AXON picks its completion model per request through its router tier unless
  `AXON_COMPLETION_MODEL` is pinned (`axon/router/engine.py:118`), so the
  answer generator is not recorded and may vary within a run.
- Dataset (`datasets/second_brain/cases.json`, N=34): 23 expected answers
  contain a digit, 4 a backticked identifier, 11 no digit. In 21 of the 23
  digit-bearing cases every digit run of `expected_answer` appears in
  `expected_contexts`; `sb-028` and `sb-035` do not. Contexts mostly ground the
  answer, but not always.
- OFF-arm answers are not easy negatives for the judges: with empty contexts
  Llama still scored OFF faithfulness 0.535 [0.441, 0.621], Mistral 0.044.
  The OFF arm is where judge leniency shows.

External method adopted: Hamel Husain "LLM judge" (binary pass/fail with a
critique by the domain expert, TPR and TNR reported separately, never raw
agreement, error analysis by root cause), Eugene Yan "Evaluating
LLM-evaluators" (human baseline, classification metrics, Cohen's kappa, judges
miss perturbed answers), Shankar et al. 2404.12272 EvalGen (criteria drift:
criteria are defined while grading; coverage = bad outputs caught = TNR; false
failure rate = good outputs failed = 1 - TPR).

## Goal

Make judge verdicts auditable after the fact, stop B4 admitting an always-pass
or always-fail judge, and give the owner the tooling and a pre-registered
protocol to measure, per judge, discrimination (threshold-free) and
calibration (at a declared threshold) against owner labels, with uncertainty
and per-case attribution, so the faithfulness_v2 decision is made on numbers.

## Requirements (traceable IDs)

| ID | Requirement | Task |
|---|---|---|
| JA-01 | `to_dict(EvalReport)` and `panel_to_dict(PanelReport)` gain a top-level `responses` key: a list of `{case_id, answer, contexts}` in case order, one per case, taken from the `RagResponse` the runner already received. Populated by `run_eval` and `run_panel_eval`. | Task 1 |
| JA-02 | Backward compatible: every existing key keeps its name, shape and value; `per_case` is unchanged; text reports are unchanged; a report model built without responses still constructs and serializes (`responses: []`). | Task 1 |
| JA-03 | `docs/GNOMON_GRAPHRAG_CONTRACT.md` documents `responses` (RNF-05). | Task 1 |
| JA-04 | A deterministic known-fail perturbation generator: for an `EvalCase` it returns zero or more `(kind, answer)` pairs, each unsupported by `expected_contexts` by construction. Kinds: `number_swap` (first digit run replaced by a digit run absent from every context), `identifier_swap` (first backticked span replaced by a fabricated identifier absent from every context), `unsupported_claim` (one fixed fabricated sentence appended). A kind that cannot apply emits nothing; no emitted answer equals the original; no randomness. | Task 2 |
| JA-05 | B4 screening takes the existing pass-class probes, known-fail probe responses, a declared `grounded_threshold` and a declared `pass_floor`, both required and validated in [0, 1]. Every probe goes through the existing JSON/schema check; faithfulness is then parsed with `parse_v1_judge_response`. **TNR floor:** a known-fail probe scoring `>= grounded_threshold` counts as grounded and fails the candidate; no known-fail probe supplied fails the candidate (fail closed). **Pass floor:** the candidate fails if no pass-class probe scores `>= pass_floor` (the always-fail signature). Evidence JSON records both parameters, known-fail count, TNR, and the count of pass probes at or above the floor. | Task 2 |
| JA-06 | Tests prove B4 rejects a stub judge answering 1.0 on every metric for every probe, and a stub answering 0.0 on every metric for every probe. | Task 2 |
| JA-07 | ADR-0012 gains an amendment note: B4 now includes a known-fail TNR floor and a pass floor; B4 has no in-repo caller, so the floors bind only when a screening driver passes the new probes; the three pinned members' evidence predates both floors, and membership is not changed by this note. `docs/panel/selection.md` links the note. | Task 2 |
| JA-08 | Labeled-verdict file format: a JSON array of items `{case_id, arm, answer, contexts, verdict, critique, rubric_version}` plus optional `question` (display only). `verdict` is `"pass"` or `"fail"`; `critique` and `rubric_version` are non-empty strings; `contexts` may be empty (OFF arm); unknown keys are rejected. Arm classes: `perturbation:<kind>` is construction-labeled (`verdict: "fail"`, `rubric_version: "construction"`); `negative:<name>` is an owner-authored hard negative (`verdict: "fail"`); any other arm is a real-response arm. Uniqueness: `(case_id, arm)` for real and perturbation arms, `(case_id, arm, answer)` for negative arms (several negatives per case are allowed). | Task 3 |
| JA-09 | Loader takes one or more files and fails closed with a named error pointing at the file and the offending item: missing file, invalid JSON, empty array, non-array document, non-object item, missing or invalid field, `verdict` null or outside pass/fail, empty `rubric_version`, a uniqueness violation within or across files, a negative or perturbation item whose verdict is not `fail`, and more than one `rubric_version` across real-arm items (mixed first-pass and frozen-rubric labels cannot produce a report). A half-labeled file cannot produce a report. | Task 3 |
| JA-10 | Pure alignment computation: inputs are labeled items, one faithfulness float per judge per item, a declared threshold in [0, 1] (score >= threshold means pass, validated before use), a confidence level and a seed. Strata: each arm on its own, plus `real` (the union of real-response arms). There is no stratum pooling perturbation or negative arms with real arms. Output per judge per stratum: pass-label count, fail-label count; **discrimination:** ROC AUC of the raw score against the owner verdict (ties count 0.5) with a seeded bootstrap interval; **calibration at the threshold:** TPR with Wilson interval, TNR with Wilson interval, Cohen's kappa with a seeded bootstrap interval. Bootstraps resample within each owner-label class (stratified, class counts preserved). Output echoes threshold, confidence level, seed and the rubric versions present. | Task 3 |
| JA-11 | No bare agreement: the output has no field reporting an accuracy, an agreement rate or a raw match rate. The ban is on rates, not on the word: the JA-16 list is not a rate and may be named `disagreements`. A statistic with an empty denominator (a label class absent from the stratum, or kappa with expected agreement 1) is `null` with a reason string, never `0.0` and never an exception that drops the other strata. Every bootstrap interval in this feature (AUC, kappa, self-agreement kappa) is `null` with a reason when either label class has fewer than 5 items: a class resampled with its count preserved at 1-4 items contributes almost no variance and yields an artificially narrow interval. Counts, point estimates and Wilson intervals still report. | Task 3 |
| JA-16 | Disagreement list: for each judge, every real-arm item where the thresholded judge verdict differs from the owner verdict, as `{case_id, arm, judge_score, judge_verdict, owner_verdict, owner_critique}`, sorted by `(arm, case_id)`. This is the raw material for per-case attribution; the tool does not code causes. | Task 3 |
| JA-17 | Owner self-agreement: a pure function over two labeled sets that joins real-arm items on `(case_id, arm)`, fails closed if a joined pair has different `answer` or `contexts` or if fewer than 2 pairs join, and returns the 2x2 verdict count table plus Cohen's kappa with a seeded bootstrap interval (no agreement rate, JA-11). | Task 3 |
| JA-12 | `gnomon align` command: reads a `RunConfig` with a `[panel]` (members built with the existing `build_judge`), `--labels PATH` (repeatable), required `--threshold`, `--json`. Resolves each item's `EvalCase` from the config's `dataset_path` (unknown `case_id` fails closed; a present `question` that differs from the dataset fails closed), scores `RagResponse(answer, contexts)` with every member, per-item score = mean over `eval.judge_runs`, then prints the JA-10 report, the JA-16 list and, under `--json`, a `scores` list of `{item, case_id, arm, judge_id, score}` (`item` = position in the loaded order, files in CLI order) so two runs can be byte-compared. Seed and confidence level come from `eval.seed` and `eval.confidence_level`; a null `eval.seed` fails closed before any judge call. Any judge error aborts with no partial report. | Task 4 |
| JA-13 | Declared cost (RNF-06): the command makes exactly `items x members x judge_runs` judge calls and prints that number before the first call. | Task 4 |
| JA-14 | Template export: `gnomon align --export OUT_DIR` takes one or more `ARM=REPORT_PATH` pairs plus the config's dataset and writes two files. `labels.todo.json`: one item per `responses` entry with `verdict: null`, `critique: ""`, `rubric_version: ""`, `question` filled from the dataset. `perturbations.json`: one item per JA-04 perturbation per case, with `answer` = the perturbed `expected_answer`, `contexts` = the case's `expected_contexts`, `question` from the dataset, `verdict: "fail"`, `critique` naming the kind, `rubric_version: "construction"`. Construction labels never enter the owner's file. A report with no `responses` key or an empty one fails closed naming the file; an existing file in `OUT_DIR` is never overwritten (fails closed). No judge score is written to either file (labeler blinding). | Task 4 |
| JA-18 | `gnomon align --self-agreement FIRST SECOND` prints the JA-17 result and exits non-zero on any JA-17 failure. | Task 4 |
| JA-15 | Owner-gated measurement under the pre-registered protocol below; results in `docs/panel/alignment.md`. | Task 5 |
| NFR-01 | No change to existing metric definitions, the v1 judge prompt, gate semantics, panel membership, `config/panel.toml` members, or the bootstrap CI (ADR-0008). | All |
| NFR-02 | RNF-03 holds in the new surface: no alignment number without an interval, except counts. | Tasks 3, 4 |
| NFR-03 | Determinism (RNF-01): the generator has no randomness; every bootstrap is seeded from config; same inputs give a byte-identical JSON report. | Tasks 2, 3, 4 |
| NFR-04 | No existing test assertion is edited or deleted, with exactly two authorized exceptions listed under Assumptions (A2). Any other needed edit is a STOP for a human round-trip (RULES.md). | All |
| NFR-05 | New JSON-array loaders carry tests for `[]` and for a non-array document (RULES.md, proposed lesson from issue #9). | Task 3 |

## Measurement protocol (JA-15, pre-registered)

Steps 1-3 are written into `docs/panel/alignment.md` **before any label is
made**; changing them afterwards is recorded as a deviation, not edited in
place.

1. **Pre-register:** calibration threshold `0.75` (mirrors the gate value; the
   gate applies it to `ci_low` of the mean, here it is a per-item cut, stated
   as such); strata per JA-10; cause codes below; seed and confidence level;
   the primary statistic per claim (table below) and the conclusion rule in
   step 10; "inconclusive" as a valid outcome for any
   stratum; labels are **test-only** and are never used to iterate a judge
   prompt (a faithfulness_v2 dev set must come from a different response draw).
2. **Pin the generator:** set `AXON_COMPLETION_MODEL` for both arms and record
   the model. Any panel member of the same vendor family as the generator is
   flagged in the interpretation (self-preference bias).
3. **Draw:** fresh ON and OFF panel runs on `datasets/second_brain` whose JSON
   carries `responses`; export with JA-14. The owner does not open the run
   JSONs' scores before labeling is complete.
4. **Grading-first pass (criteria drift):** the owner labels 15 real items,
   verdict plus critique, starting from the draft rubric v1: 5 drawn at random
   with the seed, and the 10 with the largest cross-judge faithfulness spread,
   read from `disagreement[metric="faithfulness"].case_deltas` of the ON and
   OFF run JSONs (an existing `panel_to_dict` field: per-case max minus min
   across judges, no per-judge score). The agent selects; the owner sees the
   items, never the spread, the scores or which judge scored what.
5. **Freeze the rubric:** the owner revises the rubric from what the first pass
   surfaced, records the changes and the reason in `alignment.md`, and names
   the result `v2`.
6. **Label:** the owner labels every real item under `v2`, re-labeling the 15
   first-pass items. Every real item carries `rubric_version: "v2"` (JA-09
   rejects a mix).
7. **Hard negatives:** the owner authors 15-20 plausible answers for
   `second_brain` cases, each carrying at least one claim unsupported by that
   case's contexts, in the style of a subtle real failure (not an appended
   sentence), as arm `negative:owner`. Each item carries `contexts` = that
   case's `expected_contexts`, `question` from the dataset, `verdict: "fail"`,
   `rubric_version: "v2"`, and a critique naming the unsupported claim.
8. **Owner self-agreement, before any `gnomon align` run:** at least 3 days
   after step 6, the agent copies the filled v2 file keeping 20 real items
   drawn with `eval.seed`, and sets their `verdict` to null and `critique` to
   `""` (answer, contexts and `rubric_version` untouched, so the JA-17 join
   matches). The owner re-labels them blind to the first labels;
   `--self-agreement` gives the ceiling judge-vs-owner kappa is read against.
   No judge score exists for these items yet, so nothing can leak.
9. **Run twice (determinism):** the agent runs the step-10 `gnomon align
   --json` command (pinned panel, threshold 0.75, all label files) twice and
   byte-compares the outputs, `scores` included. If they differ, the per-item
   differences are reported and verdicts within 0.05 of the threshold are
   treated as unstable in the interpretation.
10. **Record:** `alignment.md` records per judge per stratum AUC and
    TPR/TNR/kappa with intervals, label counts, owner self-kappa, generator
    model, the determinism result, and the reproducing commands. Every JA-16
    disagreement is coded with one cause code; counts per judge per cause are
    reported. **Conclusion rule:** a claim is concluded only from its
    pre-registered primary statistic (table below), and only where the two
    judges' intervals on that statistic do not overlap; a `null` interval
    concludes nothing; everything else in the report is descriptive.

### Primary statistic per claim (pre-registered)

| Claim | Primary statistic | Stratum |
|---|---|---|
| The judge ranks faithfulness like the owner | AUC | `on` (`real` is reported, not primary: the ON/OFF contrast dominates it) |
| The judge's verdict at the gate value matches the owner | TPR and TNR at 0.75 | `on` |
| The judge catches subtle unsupported claims | TNR at 0.75 | `negative:owner` |
| The GLM-4.6 harsh verdicts are judge error or rubric strictness | Cause-code counts on GLM-4.6's false fails | real arms |

### Draft labeling rubric v1 (starting point for step 4, not the frozen rubric)

- **pass**: every factual claim in ANSWER is supported by CONTEXTS. An answer
  that makes no factual claim (abstains, says it does not know) passes.
- **fail**: at least one factual claim in ANSWER is not supported by CONTEXTS,
  including a claim that is true in the world but absent from CONTEXTS.
- The critique names the unsupported claim (fail) or states what grounds the
  answer (pass), in one or two sentences.

This is the binary reading of the v1 prompt's own anchor ("1.0 = every claim
supported"). The known ambiguities step 4 exists to resolve: values derived or
computed from contexts, paraphrase granularity, partial abstention.

### Cause codes (pre-registered)

| Code | Meaning |
|---|---|
| `derived_claim` | The disputed claim is computed or inferred from contexts, not stated in them. |
| `true_but_ungrounded` | The claim is true (in the vault or the world) but absent from the contexts. |
| `paraphrase_as_support` | A context paraphrases or partially supports the claim. |
| `abstention` | The answer abstains fully or partially and the verdict hinges on that. |
| `other` | None of the above; the critique states what it is. |

## Assumptions (signed)

- **A1**: Panel runs are produced by out-of-repo drivers (METRON runners) that
  serialize with `panel_to_dict`, so adding `responses` there reaches them with
  no driver change. Evidence: the committed run JSON's `panel` object is
  exactly `panel_to_dict`'s shape.
- **A2 (AUTHORIZED by the owner directly, in session, 2026-09-10)**: making
  known-fail probes mandatory in B4 (JA-05) is the recommended fail-closed
  design, and it requires exactly two existing-test edits in
  `tests/unit/test_screening.py`: `test_candidate_passes_when_all_probes_are_clean`
  (call gains known-fail probes scored below threshold and the two new
  parameters; `passed is True` stays, and the 0.8 fixture already clears a
  0.5 pass floor) and `test_write_screening_evidence_round_trips_all_probe_fields`
  (expected dict gains the JA-05 evidence keys). The pass floor adds no further
  edit. The alternative, known-fail optional, needs no test edit but leaves B4
  open whenever a caller omits the probes, which is how an always-pass judge
  gets in today.
- **A3**: The 2026-07-22 responses are unrecoverable (not persisted, target is
  a live RAG), so JA-15 labels a new response draw. The GLM-4.6 "harsh verdict"
  question is answered on that draw, not the original.
- **A4**: Alignment v1 covers faithfulness only. `context_precision` has an
  answer key and a deterministic path already (`AnchorScorer`, issue #68).
- **A5**: `question` is an optional display field in the item format (the owner
  needs it to label). Scoring always takes the question from the dataset, so a
  stale copy cannot change a verdict, only fail the run.
- **A6**: `unsupported_claim` uses one fixed pt-BR sentence as a module
  constant, because `second_brain` (pt-BR) is the only screening corpus.
  Parameterize it when a corpus in another language is screened.
- **A7**: `identifier_swap` covers the "entity" case in the brief. Only 4 of 34
  answers have a backticked span; free-text entity swap needs NER or a hand
  list, and is deferred behind the owner-authored hard negatives (step 7),
  which cover the subtle case better.
- **A8**: Construction labels are trusted and never re-labeled by the owner.
  They are blatant negatives, reported only as their own strata. Whether
  judges catch them is an open question, not a given: Yan's survey reports
  judges failing to penalize perturbed answers more than half the time, and
  Llama credited empty-context OFF answers at 0.535. The subtle-failure
  estimate is the `negative:owner` stratum and the ON arm.
- **A9**: B4's floors are smoke checks against the two degenerate judges
  (always-pass, always-fail), not alignment estimates. The TNR floor is strict
  (any grounded known-fail probe fails) because the probes are blatant. The
  pass floor is deliberately weak (at least one pass probe at or above
  `pass_floor`) because `expected_contexts` do not always fully ground
  `expected_answer` (`sb-028`, `sb-035`), so a strict pass rule would reject a
  correct strict judge.
- **A10**: With about 34 ON items the ON-arm fail-label count may be small and
  its intervals wide. "Inconclusive" is a pre-registered outcome; no claim that
  one judge is right is made unless intervals separate.
- **A11**: Single labeler. Judge-vs-owner kappa is read against the owner's own
  self-agreement (step 9), not against 1.0. Relative judge comparisons on
  shared labels survive label noise better than absolute claims.
- **A12**: Determinism at temperature 0 is measured once (step 9), not
  assumed; `judge_runs` stays 1 per ADR-008 unless step 9 finds variance.

## Cross-review

Round 1, GLM-5.3 (Z.ai, 2026-09-10), methodological review against the three
sources. Round 2 (same day, the bounded final round) reviewed the diff and
judged every round-1 finding resolved (finding 10 partially, residual
accepted), then raised N1-N7; its verdict was to open the issues once N1-N3
are folded in. Every finding in both rounds was checked against the code
before disposition.

| # | Finding (severity as given) | Disposition | Applied in |
|---|---|---|---|
| 1 | Rubric frozen before grading contradicts criteria drift (BLOCKING) | Accepted | Protocol steps 4-6, JA-08/09 `rubric_version` |
| 2 | One threshold over differently calibrated judges conflates calibration with discrimination (BLOCKING) | Problem accepted; proposed fix (owner-prevalence-matched quantile) rejected because it chooses the cut from the labels; replaced by threshold-free AUC plus a pre-registered fixed threshold | JA-10, protocol step 1 |
| 3 | Fail class is easy, informative stratum nearly empty (BLOCKING) | Accepted in part: owner hard negatives and "inconclusive" adopted; "OFF is easy" and "perturbations will read 0.9+" rejected (Llama OFF 0.535; Yan's perturbation finding) | Protocol step 7, A8, A10 |
| 4 | Deliverable needs error analysis no requirement performs (BLOCKING) | Accepted | JA-16, cause codes, step 10 |
| 5 | Single labeler without a reliability ceiling | Accepted | JA-17, JA-18, step 9, A11 |
| 6 | B4 floor asymmetric and dormant | Confirmed (`screen_candidate` has no caller); proposed strict pass rule replaced by a weak pass floor (`sb-028`/`sb-035` contexts do not ground every digit) | JA-05, JA-06, JA-07, A9 |
| 7 | `overall` stratum pools construction negatives | Accepted | JA-10 strata |
| 8 | Instrument noise: pin `judge_runs >= 3` | Rejected: temperature 0 is pinned, runs are copies (ADR-008); replaced by a one-off determinism probe | Step 8, A12 |
| 9 | Generator model unrecorded (self-preference) | Confirmed (AXON router picks per tier) | Step 2 |
| 10 | Checksum over answer+contexts in the labels file | Rejected (YAGNI: the owner's own file); perturbation item fields pinned | JA-14 |
| - | Declare labels test-only; keep construction labels out of the owner's file | Accepted | Step 1, JA-14 |
| R2-N1 | Step 4 spread selection reads data the run JSON lacks (BLOCKING) | Refuted: `panel_to_dict` already emits `disagreement[].case_deltas`, the per-case cross-judge spread; step 4 now names the field | Step 4 |
| R2-N2 | Determinism probe not executable, no per-item scores exposed (BLOCKING) | Accepted: `--json` carries `scores`; the probe is the step-10 command run twice and byte-compared; the 10-item file is gone | JA-12, step 9 |
| R2-N3 | Stratified bootstrap with 1-4 items in a class gives artificially narrow intervals (BLOCKING) | Accepted: bootstrap intervals `null` below 5 per class | JA-11 |
| R2-N4 | Determinism step exposed scores before the blind re-label | Accepted: re-label moved before any align run | Steps 8-9 |
| R2-N5 | `negative:owner` item fields unpinned | Accepted | Step 7 |
| R2-N6 | Conclusion rule does not name its statistic (multiplicity) | Accepted | Primary statistic table, step 10 |
| R2-N7 | Re-label file production and seed source unnamed | Accepted | Step 8, JA-12 |
| R2-cut | `label_use` echo is policy inside a pure function | Accepted, removed; the policy lives in step 1 | JA-10 |

## Rejected / deferred

| Item | Status | Why |
|---|---|---|
| `faithfulness_v2` (claim-level binary verdicts with a short critique, new metric name) | Deferred, needs an ADR | Waits on JA-15 numbers: the labels decide whether the v1 prompt is actually misaligned. |
| Train/dev/test split of the labeled set | Deferred to faithfulness_v2 | Nothing iterates against these labels; they are declared test-only (step 1). |
| Committed B4 screening driver / re-screening the pinned members | Deferred, owner call | B4 model calls live outside the repo today; JA-07 states the floors are dormant until a driver passes the probes. |
| `gnomon panel` CLI command | Deferred | Runs are driven from METRON; JA-01 reaches them through the serializer. |
| Threshold sweep in one report | Deferred | AUC covers the threshold-free question; a second threshold is one more command. |
| Owner-prevalence-matched threshold | Rejected | Chooses the cut from the labels being measured against. |
| `judge_runs >= 3` in the measurement run | Rejected | Temperature 0 is pinned; runs are copies (ADR-008). Step 9 measures it instead. |
| Checksum over labeled answer/contexts | Rejected | YAGNI; the file is the owner's own, and scoring takes the question from the dataset. |
| Free-text entity swap perturbation | Deferred | Needs NER or a curated list (A7); owner hard negatives cover the subtle case. |
| Construction-labeled pass items for alignment | Rejected | `expected_contexts` do not always fully ground `expected_answer` (`sb-028`, `sb-035`); auto-labeling them pass would inject label noise. Used only as the weak B4 pass floor (A9). |
| Case dimension tags | Out of this blueprint | Stated optional in the brief. |

## Out of scope

| Item | Why |
|---|---|
| Any change to `faithfulness` / `context_precision` definitions or the v1 prompt | NFR-01; the alignment numbers decide that later. |
| Gate semantics, majority rule, `ci_low` comparison | NFR-01. |
| Panel membership or `config/panel.toml` members | NFR-01; JA-07 is a note, not an eviction. |
| Bootstrap CI method for metrics (ADR-0008) | NFR-01; Wilson and the stratified bootstrap are used only inside the alignment report. |
| ChatEval (`chat_runner`) and session reports | They do not produce `RagResponse`; ChatEval already has `--save-generations`. |
| Rewriting `docs/panel/runs/2026-07-22-*.json` | Historical evidence stays as committed (A3). |
| The owner's labeling itself | Owner-gated (Task 5, `agent:blocked`). |
