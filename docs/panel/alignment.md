# Judge alignment: pre-registration and record (issue #75)

Spec: `.specs/features/judge-alignment/spec.md` ("Measurement protocol (JA-15,
pre-registered)"). Tooling: `gnomon align` (issues #71-#74, master `cde823a`).

**Status: PRE-REGISTRATION.** Sections 1-2 were committed before the first
label was made. They are not edited afterwards; any change is appended to
section 6 as a deviation, with its date and reason.

## 1. Analysis plan (protocol step 1)

- **Metric under test:** `faithfulness` only (spec A4).
- **Calibration threshold:** `0.75`, applied per item (judge score >= 0.75
  means pass). The CI gate uses the same value on `ci_low` of the mean; that
  is a different use of the number, stated here so the two are not confused.
- **Strata:** each arm on its own (`on`, `off`,
  `perturbation:number_swap`, `perturbation:identifier_swap`,
  `perturbation:unsupported_claim`, `negative:owner`), plus `real` = `on` and
  `off` together. No stratum pools construction or owner-authored negatives
  with real responses.
- **Statistics, per judge per stratum:** label counts; ROC AUC of the raw
  score with a stratified seeded bootstrap interval; TPR and TNR at the
  threshold with Wilson intervals; Cohen's kappa with a stratified seeded
  bootstrap interval. Bootstrap intervals are `null` when a label class has
  fewer than 5 items.
- **Seed and confidence:** `eval.seed = 42`, `confidence_level = 0.95`.
- **Labels are test-only.** They are never used to iterate a judge prompt; a
  faithfulness_v2 dev set must come from a different response draw.
- **"Inconclusive" is a valid outcome** for any claim and any stratum.
- **Determinism:** the final `gnomon align --json` command runs twice and
  the outputs are byte-compared, `scores` included. If they differ, verdicts
  within 0.05 of the threshold are treated as unstable.

### Primary statistic per claim

| Claim | Primary statistic | Stratum |
|---|---|---|
| The judge ranks faithfulness like the owner | AUC | `on` (`real` is reported, not primary: the ON/OFF contrast dominates it) |
| The judge's verdict at the gate value matches the owner | TPR and TNR at 0.75 | `on` |
| The judge catches subtle unsupported claims | TNR at 0.75 | `negative:owner` |
| The GLM-4.6 harsh verdicts are judge error or rubric strictness | Cause-code counts on GLM-4.6's false fails | real arms |

**Conclusion rule:** a claim is concluded only from its primary statistic, and
only where the two judges' intervals on that statistic do not overlap. A
`null` interval concludes nothing. Everything else in the report is
descriptive.

### Cause codes

| Code | Meaning |
|---|---|
| `derived_claim` | The disputed claim is computed or inferred from contexts, not stated in them. |
| `true_but_ungrounded` | The claim is true (in the vault or the world) but absent from the contexts. |
| `paraphrase_as_support` | A context paraphrases or partially supports the claim. |
| `abstention` | The answer abstains fully or partially and the verdict hinges on that. |
| `other` | None of the above; the critique states what it is. |

## 2. Generator and panel (protocol step 2)

- **Generator:** `AXON_COMPLETION_MODEL=deepinfra/deepseek-ai/DeepSeek-V4-Flash`
  (DeepSeek family). Without the pin, AXON's router picks a model per request,
  and its DeepInfra profile defaults to Meta Llama, the same family as a panel
  judge.
- **Why this model (owner decision, 2026-09-11):** one grounded pt-BR probe
  per candidate on DeepInfra. DeepSeek-V4-Flash, Qwen3-235B-A22B-Instruct-2507
  and gemma-4-31B-it all answered from the contexts and abstained on the part
  the contexts did not cover. Qwen3.6-35B-A3B was rejected: empty `content`,
  its whole budget spent on reasoning. DeepSeek-V4-Flash gave the longest
  answers (66 completion tokens against about 36), which makes real ON-arm
  failures more likely; the ON fail class is the one spec A10 expects to be
  small. One probe per model shows the model works, not that it is better.
- **Panel** (`config/panel.toml`; `judge_id` in the `gnomon align` output is
  the family):

| `judge_id` | Model |
|---|---|
| `meta` | `meta-llama/Meta-Llama-3.1-8B-Instruct` |
| `zhipu` | `zai-org/GLM-4.6` |
| `mistral` | `mistralai/Mistral-Nemo-Instruct-2407` |

- **Same-family flag:** none. The generator's family is not in the panel.

## 3. Draw (protocol step 3)

**Storage rule:** this repository is public, and run JSONs with `responses`,
exported templates and label files carry text retrieved from the owner's
private vault. They live outside the repository
(`~/dev/tools/gnomon-eval-private/alignment-2026-09-11/`, owner-only). This
document records their SHA-256 digests and the commands that produced them,
never their content; aggregate statistics and cause-code counts are published
here.

Commands (driver `scripts/run_panel_arm.py`, configs `config/alignment-{on,off}.toml`):

    python scripts/run_panel_arm.py -c config/alignment-on.toml  --arm on  --out $PRIVATE/run-on.json
    python scripts/run_panel_arm.py -c config/alignment-off.toml --arm off --out $PRIVATE/run-off.json

Draw executed 2026-09-11, AXON `c7bf107`, gnomon `cde823a`, generator pinned
(AXON log: `router decision ... source=pinned model=deepinfra/deepseek-ai/DeepSeek-V4-Flash`).

| Arm | Started (UTC) | Cases | Responses | Empty / `[LLM unavailable` | Contexts per case | SHA-256 |
|---|---|---|---|---|---|---|
| `on` | 15:37:49 | 34 | 34 | 0 / 0 | 5-8 | `0ad353e002bcba0a3ee67c30dd6c3b0690c47899fb20a3e5099a09fcb95a6bf5` |
| `off` | 15:50:24 | 34 | 34 | 0 / 0 | 0 | `73d7d3c45fbdcccceb34a56fc8f3372e2dc897d02f8ea65ec6007c6ece457de7` |

Both arms finished 16:04:39 UTC.

Export (2026-09-11):

    gnomon align -c config/alignment-on.toml --export $PRIVATE/export on=$PRIVATE/run-on.json off=$PRIVATE/run-off.json

| File | Items | SHA-256 |
|---|---|---|
| `labels.todo.json` | 68 (34 `on`, 34 `off`), every verdict null, no score field | `08eb86ebb1e7301b750a4c7400ef352498205cdc1ca074b5f28b527183e50491` |
| `perturbations.json` | 61 (23 `number_swap`, 4 `identifier_swap`, 34 `unsupported_claim`) | `f4c8614a837800328f507be68a41588b16782f2aa6cb27acd8e812da98d46c0b` |

## 4. Rubric history (protocol steps 4-5)

Draft rubric v1 is the one in the spec.

**First-pass selection (deviation D1, see section 6):** 5 real items drawn with
`random.Random(42).sample` over the 68 real items sorted by `(arm, case_id)`,
plus the 10 largest `faithfulness` `case_deltas` **within the `on` arm**, ties
by `case_id`. The 15 items are presented to the owner in a seeded shuffled
order, with no arm label beyond what the contexts show, no spread and no
score.

To be recorded: the owner's rubric notes, the changes, and the frozen `v2`.

## 5. Results (protocol steps 6-10)

To be recorded after labeling, hard negatives, the delayed self-agreement
re-label and the double run.

## 6. Execution log and deviations

Append-only.

- 2026-09-11: pre-registration written; generator pinned as in section 2.
- 2026-09-11: the draw started at 15:37:49 UTC, 29 seconds before the
  pre-registration commit (`cc1f7db`, 15:38:18 UTC). The document was written
  before the draw started, and the protocol requires pre-registration before
  the first label, not before the draw. Recorded for completeness.
- 2026-09-11, **deviation D1 (owner decision):** spec protocol step 4 selects
  the 10 largest cross-judge spreads across both arms. On this draw that
  selection was 10 of 10 `off` items (the largest spreads all sit in the
  empty-context arm; 15 `off` items tie at the maximum), and 4 of the 5 random
  items were also `off`, so the first pass would have held 14 answers with no
  contexts. The pass exists to surface grounding ambiguities (derived claims,
  paraphrase, partial abstention), which need contexts. The spread selection was
  restricted to the `on` arm; the 5 random items are unchanged. The first pass
  does not enter any statistic (every real item is labeled again under `v2`),
  so D1 changes which ambiguities inform the rubric, not the analysis.
