## Validation: issue #33 — PASS

Spec-anchored check: no spec.md for this issue (entered `task` directly); fallback used — assertion exists and covers the criterion. All acceptance criteria verified via shell command, matching the config-only, non-code nature of this change:
- AC1 "S enforced, repo clean": `ruff check src tests` exits 0; `ruff check --select S src tests` exits 0.
- AC2 "S actually blocks new S findings in src": verified via mutation battery (DROP_SIDE_EFFECT below).
- AC3 "S101 ignored in tests, doesn't regress existing 456 asserts": verified via mutation battery (NEGATE_CONDITIONAL below).
- AC4 "redundant non-blocking CI step removed, no other CI changes": `grep -c "Security lint" .github/workflows/ci.yml` = 0; `grep -c "ruff check src tests" .github/workflows/ci.yml` = 1; ci.yml still parses as valid YAML.

### Mutation battery detail

- NEGATE_CONDITIONAL mutation: removed `"S101"` from the `tests/**` per-file-ignore in `ruff.toml` (flipping the ignore condition). `ruff check src tests` went from exit 0 to exit 1 with 456 errors (the existing test asserts). Reverted; exit 0 restored. KILLED.
- DROP_SIDE_EFFECT mutation: reverted `select` to omit `"S"` (dropping the new enforcement side effect). An injected S310 violation (`urllib.request.urlopen` on an unvalidated URL, in a scratch file never committed) then passed `ruff check src tests` silently. Restoring `"S"` in `select` caught the same violation. KILLED.
- Extra 1 (S311 insecure-random): injected `random.randint` use in a scratch file; `ruff check --select S` caught it with the fix in place. KILLED.
- Extra 2 (S603 subprocess call): injected an unchecked `subprocess.call` in a scratch file; `ruff check --select S` caught it with the fix in place. KILLED.
- Extra 3 (existing noqa regression check): confirmed `ruff check --select S src` is clean (0 findings) under the full `S` select — broadening from the narrow S310/S311/S603 subset to full `S` surfaced no new findings. KILLED (no regression). Correction from code-quality review (gpt-5.6-sol): the S310 (http.py) and S311 (confidence.py, judge/stub.py) noqa comments are genuinely active suppressions; the pre-existing S603 `noqa` on `chat_target.py:43` (`self._run(...)`) is actually inert — ruff's S603 check does not recognize a call through an instance attribute as a subprocess call, so it never fired there in the first place (confirmed via `RUF100`, "unused noqa directive"). This does not weaken or regress this issue's gate (`RUF` is not in `select`, so `RUF100` is not enforced, and the file has zero S findings either way) but the "still suppress correctly" claim above overstated it for that one line; it is a pre-existing PR #41 artifact, out of this issue's scope to fix.
- Extra 4 (CI YAML validity): after removing the redundant CI step, `.github/workflows/ci.yml` still parses as valid YAML (`yaml.safe_load` succeeds). KILLED (no structural breakage).

All scratch mutations were made to untracked scratch files or reverted `ruff.toml` edits inside the worktree, confirmed removed/restored by `git diff --stat` showing only the original 2-file, 6-line diff before and after each mutation.

Mutation sensor (mandatory): EMPTY_RETURN=N/A: config-only deliverable with no function return value, IDENTITY_RETURN=N/A: config-only deliverable with no transformation function, NEGATE_CONDITIONAL=KILLED, DROP_SIDE_EFFECT=KILLED
Mutation sensor (extras): 4 injected 4 killed: S311-insecure-random KILLED S603-subprocess-call KILLED existing-noqa-no-regression KILLED ci-yaml-still-valid KILLED
Report: .specs/features/issue-33-ruff-s-blocking/validation.md
