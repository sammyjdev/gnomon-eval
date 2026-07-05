# ChatEval tasks (adopted from the hand-written implementation plan)

Source of truth for full code, test bodies, and exact commands: `docs/superpowers/plans/2026-07-05-chateval.md`.
This file reformats that plan's task list into forge's one-issue-per-task
convention and states dependency order; it does not restate the code.

Task 1 (bootstrap `.claude/loop.yaml`) is already done (merged at `master`,
commit `7c24c89`) and is not reopened here.

| # | Task | Depends on | Files (create unless noted) | GitHub issue |
|---|---|---|---|---|
| 2 | ChatEval domain models (`ChatCase`, `ChatResult`) | - | `src/gnomon/domain/chat.py`, `tests/unit/test_chat_models.py` | opened this pass |
| 3 | Chat dataset loader + 17-case golden dataset | 2 | `src/gnomon/dataset/chat_loader.py`, `datasets/lina_chateval/cases.json`, `tests/unit/test_chat_loader.py` | opened this pass |
| 4 | DeepEval-backed `ChatJudge` (NIM primary, Ollama fallback) | 2 | `src/gnomon/judge/chat_judge.py`, `tests/unit/test_chat_judge.py`, modify `pyproject.toml` (add `deepeval`) | opened this pass |
| 5 | `ChatTarget` (subprocess into `lina-mvp`'s adapter script) | 2 | `src/gnomon/targets/chat_target.py`, `tests/unit/test_chat_target.py` | opened this pass |
| 6 | Chat runner (orchestrates cases into an `EvalReport`) | 2, 4, 5 | `src/gnomon/runner/chat_runner.py`, `tests/unit/test_chat_runner.py` | opened this pass |
| 7 | `gnomon chat` CLI, config, judge provider wiring | 3, 4, 5, 6 | `src/gnomon/config/chat_config.py`, `config/chat.toml`, modify `src/gnomon/cli.py`, `tests/unit/test_chat_config.py`, modify `pyproject.toml` (add `litellm`) | opened this pass |
| 8 | Pilot validation run (manual, spends real API budget) | 7, **and `lina-mvp`'s own adapter-script task (cross-repo, separate plan)** | none (operational step) | opened this pass, labeled `agent:blocked` (cross-repo dependency not yet satisfied) |

## Notes carried from the plan's own self-review

- Spec coverage, placeholder scan, and type consistency were already
  self-reviewed in the source plan (see its "Self-review" section) and
  independently spot-checked against the live codebase during this
  blueprint's `ore` phase (see `spec.md`'s "Verification performed" section)
  -- `aggregate_metric`, `evaluate_gate`, `EvalReport`, and the `cli.py`
  dispatch pattern all match what the plan's code assumes.
- Each task's full RED test, implementation code, and exact shell commands
  are written out in full in `docs/superpowers/plans/2026-07-05-chateval.md`
  under the matching `### Task N` heading -- `forge task` should read that
  section directly rather than re-deriving the approach.
