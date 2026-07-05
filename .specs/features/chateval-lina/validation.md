## Validation: issue #8 — PASS
Spec-anchored check: 3/3 ACs matched (CR-01 in spec.md: ChatCase rejects empty conversation -> ValidationError asserted; ChatCase.criteria defaults to None -> value asserted; ChatResult.tool_called defaults to None on text-only reply -> value asserted). No spec-precision gaps.
Mutation sensor: 1 injected (Common tier: conversation Field min_length=1 -> min_length=0, primary happy path), 1 killed, 0 survived.
Report: .specs/features/chateval-lina/validation.md
