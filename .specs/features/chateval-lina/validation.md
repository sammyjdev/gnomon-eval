## Validation: issue #8 — PASS
Spec-anchored check: 3/3 ACs matched (CR-01 in spec.md: ChatCase rejects empty conversation -> ValidationError asserted; ChatCase.criteria defaults to None -> value asserted; ChatResult.tool_called defaults to None on text-only reply -> value asserted). No spec-precision gaps.
Mutation sensor: 1 injected (Common tier: conversation Field min_length=1 -> min_length=0, primary happy path), 1 killed, 0 survived.
Report: .specs/features/chateval-lina/validation.md

## Validation: issue #11 — PASS
Spec-anchored check: 5/5 ACs matched (CR-04 in spec.md: ChatTarget subprocess call, JSON stdin/stdout contract, no lina-mvp import, error naming mirrors openai_compat.TargetRuntimeError, tests use injected fake runner only. spec.md cross-references plan Task 5's verbatim code/tests rather than defining separate precise values, so no gap between spec and test assertions).
Mutation sensor: 1 injected (Common tier, primary happy path: flipped `completed.returncode != 0` to `== 0` in chat_target.py, applied only in scratch/restored immediately), 1 killed, 0 survived.
Reviewer: independent Haiku 4.5 pass, spec-compliance only, PASS, no blocking findings, no scope creep (exactly 2 new files).
Report: .specs/features/chateval-lina/validation.md
