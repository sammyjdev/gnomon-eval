# Session Token-Savings Harness — Wave 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the retired deterministic "52.3%" projection with a measured savings-vs-turn-count curve: N-turn sessions run twice (AXON arm: zero history + fixed 2000-token recall budget; baseline arm: re-send full growing transcript, no retrieval), counting real provider prompt tokens per turn, with a final-turn faithfulness gate so a quality collapse invalidates the savings claim (ADR-009).

**Architecture:** The harness lives in gnomon-eval as a session layer parallel to the single-turn runner, reusing HttpTransport, the Ollama judge plumbing, bootstrap-CI (`aggregate_metric`), and the CLI. AXON's endpoint gains two backward-compatible request fields (`forward_history`, `recall_max_tokens`) so one endpoint serves both arms. `benchmarks/model.py` is kept but labeled RETIRED.

**Tech Stack:** Python 3.11/3.12, FastAPI (axon), pydantic v2, pytest (+pytest-asyncio in axon), tomllib.

## Global Constraints

- TDD on every code task: failing test first (RED), minimal implementation (GREEN), then commit. No production code before a red test.
- Branches STACK on the open Wave 1 PRs: axon → branch `feat/session-savings-wave2` off `feat/honest-usage-wave1`; gnomon → branch `feat/session-savings-harness` off `feat/ab-recall-compare`. Note the dependency in each PR description.
- Backward compatibility is inviolable: with the new request fields at their defaults (`forward_history=false`, `recall_max_tokens=null`), the axon endpoint behavior and the gnomon single-turn contract are byte-identical to Wave 1. `gnomon -c <cfg>` (no subcommand) keeps working unchanged (RNF-04).
- Arms are fixed by design (owner-ratified): AXON arm = zero conversation history, `include_context=true`, `recall_max_tokens=2000`; baseline arm = full growing transcript, `include_context=false`, `forward_history=true`.
- Headline metric = prompt tokens (input side); completion tokens reported but excluded from the headline. Savings at turn k = `1 - axon_prompt_k / baseline_prompt_k`, CI over sessions via `aggregate_metric` (savings may be NEGATIVE early — the crossover is part of the claim).
- Judge cost is declared upfront (RNF-06): generation calls = `sessions x turns x 2`; judge calls = `sessions x 2 x judge_runs` (final turn only).
- No judge metric without mean+CI+N (RNF-03). MetricResult does not bound values to [0,1], so negative savings aggregate fine; do NOT route savings through MetricScores (which enforces [0,1]).
- Code, comments, commit messages in English. No em/en dashes in docs — plain "-" only.
- Run axon tests from `~/dev/axon` (`python3 -m pytest`, pyenv env "clock" via `~/.pyenv/versions/clock/bin` for the server), gnomon tests from `~/dev/gnomon-eval` (`.venv/bin/python -m pytest tests/unit/ -q`).

## Design decisions locked by this plan (architect + owner)

1. **Harness in gnomon-eval** (owns transport/judge/CI/CLI and ADR-009); axon `benchmarks/` is the artifact being retired, not extended.
2. **Two new endpoint fields** on `ChatCompletionRequest`: `forward_history: bool = False` (forward `messages[:-1]` as conversation history to the router — today `app.py` passes `messages=[]`), `recall_max_tokens: int | None = None` (per-request retrieval budget; `None` → the current hardcoded 4000). Defaults reproduce Wave 1 behavior exactly.
3. **AXON arm sends zero history** — recall is its only memory. Honest test of "recall replaces history" and comparable with the retired model's assumption (same `recall_budget=2000`).
4. **Sessions are LLM-drafted, vault-grounded, owner-reviewed** (owner choice, deviating from the architect's hand-written recommendation): an agent drafts 10 sessions x 10 turns anchored to indexed vault topics; the owner approves/edits rather than authors. The claim states this provenance.
5. **Quality gate: final-turn faithfulness per arm**, `judge_runs` samples, CI over sessions. Judged against what the arm ACTUALLY saw: retrieved contexts (AXON arm) or the forwarded transcript (baseline arm). If the AXON arm's final-turn faithfulness CI falls entirely below the baseline's CI, the savings number is NOT publishable.
6. **Token source = `response.usage` per call** (Wave 1 plumbing, `source` must be `provider`). RecallRecord JSONL is not used for the curve (no session/turn correlation).
7. **`AXON_MAX_PRE_SEND_TOKENS`** (engine.py:39, default 8000) would truncate the growing baseline transcript: the runbook sets `AXON_MAX_PRE_SEND_TOKENS=32000` for harness runs. No code change.
8. **The existing `OllamaJudge` cannot judge sessions** (its prompt requires `EvalCase.expected_answer`/`expected_contexts`); a faithfulness-only session prompt reuses the same HTTP/JSON/cache/seed machinery.
9. **`benchmarks/model.py` kept, labeled RETIRED** with pointer to the measured harness; README badge/METRICS swap happens only after a valid measured run (propagation, owner-gated).

---

### Task 1: AXON — `forward_history` + `recall_max_tokens` request fields

**Files:**
- Modify: `~/dev/axon/src/axon/http/app.py` (request model ~line 81-85, retrieval call ~line 129-137, LLM call ~line 155-159, module docstring)
- Modify: `~/dev/axon/tests/http/test_chat_completions.py` (new section)

**Interfaces:**
- Consumes: Wave 1 handler (`include_context`, `complete_with_usage(task, messages)` — the router already accepts a history list, `engine.py:238`).
- Produces: `ChatCompletionRequest.forward_history: bool = False`, `ChatCompletionRequest.recall_max_tokens: int | None = None`. When `forward_history=true`, the router receives `[m.model_dump() for m in request.messages[:-1]]`; retrieval uses `max_tokens=request.recall_max_tokens or 4000`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/http/test_chat_completions.py`:

```python
# ---------------------------------------------------------------------------
# Tests — forward_history + recall_max_tokens (Wave 2 session harness)
# ---------------------------------------------------------------------------


def test_forward_history_passes_prior_messages_to_router() -> None:
    mock_complete = _make_complete_mock()
    with (
        patch(_PATCH_RETRIEVE, new=_make_retrieve_mock()),
        patch(_PATCH_COMPLETE, new=mock_complete),
    ):
        with TestClient(app) as c:
            c.post(
                "/v1/chat/completions",
                json={
                    "forward_history": True,
                    "include_context": False,
                    "messages": [
                        {"role": "user", "content": "first question"},
                        {"role": "assistant", "content": "first answer"},
                        {"role": "user", "content": "second question"},
                    ],
                },
            )
    history = mock_complete.call_args.kwargs["messages"]
    assert history == [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
    ]
    # The current turn goes through the TaskRequest, not the history.
    assert mock_complete.call_args.args[0].content == "second question"


def test_history_not_forwarded_by_default() -> None:
    mock_complete = _make_complete_mock()
    with (
        patch(_PATCH_RETRIEVE, new=_make_retrieve_mock()),
        patch(_PATCH_COMPLETE, new=mock_complete),
    ):
        with TestClient(app) as c:
            c.post(
                "/v1/chat/completions",
                json={
                    "messages": [
                        {"role": "user", "content": "first"},
                        {"role": "assistant", "content": "answer"},
                        {"role": "user", "content": "second"},
                    ]
                },
            )
    assert mock_complete.call_args.kwargs["messages"] == []


def test_recall_max_tokens_overrides_retrieval_budget() -> None:
    mock_retrieve = _make_retrieve_mock()
    with (
        patch(_PATCH_RETRIEVE, new=mock_retrieve),
        patch(_PATCH_COMPLETE, new=_make_complete_mock()),
    ):
        with TestClient(app) as c:
            c.post(
                "/v1/chat/completions",
                json={
                    "recall_max_tokens": 2000,
                    "messages": [{"role": "user", "content": "q"}],
                },
            )
    assert mock_retrieve.call_args.kwargs["max_tokens"] == 2000


def test_recall_budget_defaults_to_4000() -> None:
    mock_retrieve = _make_retrieve_mock()
    with (
        patch(_PATCH_RETRIEVE, new=mock_retrieve),
        patch(_PATCH_COMPLETE, new=_make_complete_mock()),
    ):
        with TestClient(app) as c:
            c.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "q"}]},
            )
    assert mock_retrieve.call_args.kwargs["max_tokens"] == 4000
```

- [ ] **Step 2: Run to verify RED**

Run: `cd ~/dev/axon && python3 -m pytest tests/http/test_chat_completions.py -k "forward_history or recall_max_tokens or recall_budget" -v`
Expected: `test_forward_history_passes_prior_messages_to_router` FAILS (history is `[]`); `test_recall_max_tokens_overrides_retrieval_budget` FAILS (max_tokens is 4000). The two default-pinning tests pass from birth (regression pins).

- [ ] **Step 3: Implement**

Request model:

```python
class ChatCompletionRequest(BaseModel):
    model: str = "axon"
    messages: list[_Message]
    include_context: bool = True
    forward_history: bool = False
    recall_max_tokens: int | None = None
```

Retrieval call (`max_tokens=4000` line):

```python
                max_tokens=request.recall_max_tokens or 4000,
```

LLM call:

```python
    # Conversation history for the baseline arm of multi-turn evals
    # (ADR-009 in gnomon-eval). Default [] preserves Wave 1 behavior.
    history: list[dict] = (
        [m.model_dump() for m in request.messages[:-1]] if request.forward_history else []
    )
    task = TaskRequest(content=augmented_query)
    try:
        answer, usage = await complete_with_usage(task, messages=history)
    except Exception as exc:
        ...
```

Update the module docstring's request-fields section with the two new fields (one line each).

- [ ] **Step 4: Run GREEN + full suites**

Run: `cd ~/dev/axon && python3 -m pytest tests/http/ -q` (all pass, 4 new) then `python3 -m pytest tests/router/ tests/observability/ -q` (no regressions).

- [ ] **Step 5: Commit**

```bash
cd ~/dev/axon
git add src/axon/http/app.py tests/http/test_chat_completions.py
git commit -m "feat: forward_history and recall_max_tokens request fields for multi-turn evals"
```

---

### Task 2: AXON — label the deterministic model RETIRED

**Files:**
- Modify: `~/dev/axon/benchmarks/model.py` (module docstring)
- Modify: `~/dev/axon/docs/METRICS.md` (the 52.3% row)

**Interfaces:** none (documentation-only; README badge swap is deliberately NOT here — it happens in the propagation step after a valid measured run).

- [ ] **Step 1: Prepend to `benchmarks/model.py`'s module docstring**

```
RETIRED (2026-07-02): this deterministic projection (the "52.3%" figure) is
superseded by the measured multi-turn harness in gnomon-eval
(`gnomon session -c config/axon-session.toml`; see gnomon-eval ADR-0010).
Kept for provenance: the projection-vs-measurement delta is part of the
published story. Do not cite this model's output as a measurement.
```

- [ ] **Step 2: In `docs/METRICS.md`, annotate the 52.3% row** with `(RETIRED: deterministic projection; superseded by the measured session harness, gnomon-eval ADR-0010)`.

- [ ] **Step 3: Commit**

```bash
cd ~/dev/axon
git add benchmarks/model.py docs/METRICS.md
git commit -m "docs: retire the deterministic 52.3% projection (superseded by measured harness)"
```

---

### Task 3: GNOMON — session domain models + loader

**Files:**
- Create: `~/dev/gnomon-eval/src/gnomon/domain/session.py`
- Create: `~/dev/gnomon-eval/src/gnomon/dataset/session_loader.py`
- Test: `~/dev/gnomon-eval/tests/unit/test_session_models.py`

**Interfaces:**
- Consumes: pydantic v2, `ConfigDict(frozen=True)` house style (see `domain/models.py`).
- Produces:

```python
Arm = Literal["axon", "baseline"]

class Session(BaseModel):          # frozen
    id: str            # min_length=1
    topic: str         # min_length=1
    turns: list[str]   # min_length=2, each turn min_length=1 (validator)

class TurnCost(BaseModel):         # frozen
    session_id: str
    turn: int                      # ge=0 (0-indexed)
    arm: Arm
    prompt_tokens: int             # ge=0
    completion_tokens: int         # ge=0
    total_tokens: int              # ge=0
    latency_ms: float              # ge=0.0
    usage_source: str              # "provider" | "estimate" — validity flag

def load_sessions(path: str | Path) -> list[Session]   # session_loader.py
```

`load_sessions` mirrors `dataset/loader.py`'s style: read JSON array, construct `Session` per element, propagate ValidationError (fail closed), reject duplicate ids.

- [ ] **Step 1: Write the failing tests** — construct-and-assert for both models (frozen: assigning raises), a turns-min-2 rejection, an empty-turn-string rejection, loader roundtrip via `tmp_path` JSON file, duplicate-id rejection. Follow `tests/unit/test_domain.py` and `test_dataset.py` patterns.
- [ ] **Step 2: RED** — `ModuleNotFoundError`.
- [ ] **Step 3: Implement both files.** Empty-turn validation as a `@model_validator(mode="after")` on `Session`.
- [ ] **Step 4: GREEN** — `.venv/bin/python -m pytest tests/unit/test_session_models.py -v`, then full `tests/unit/ -q`.
- [ ] **Step 5: Commit** — `feat: session domain models and loader for multi-turn harness`.

---

### Task 4: GNOMON — SessionTarget (per-turn HTTP calls, both arms)

**Files:**
- Create: `~/dev/gnomon-eval/src/gnomon/targets/session_target.py`
- Test: `~/dev/gnomon-eval/tests/unit/test_session_target.py`

**Interfaces:**
- Consumes: `HttpTransport`/`UrllibTransport` (`gnomon/http.py`), error taxonomy pattern from `targets/openai_compat.py` (TargetConfigError / TargetRuntimeError / IncompleteResponseError).
- Produces:

```python
class TurnResult(BaseModel):       # frozen
    answer: str
    contexts: list[str]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    usage_source: str

class SessionTarget:
    def __init__(self, *, base_url, model, transport=None, api_key=None,
                 timeout_s=60.0, recall_max_tokens=2000): ...
    def run_turn(self, history: list[dict], question: str, *, arm: Arm) -> TurnResult
```

Payload per arm (the load-bearing logic):

```python
        if arm == "axon":
            payload = {
                "model": self._model,
                "messages": [{"role": "user", "content": question}],
                "include_context": True,
                "forward_history": False,
                "recall_max_tokens": self._recall_max_tokens,
            }
        else:  # baseline
            payload = {
                "model": self._model,
                "messages": [*history, {"role": "user", "content": question}],
                "include_context": False,
                "forward_history": True,
            }
```

Response handling: require `usage.prompt_tokens`, `usage.completion_tokens`, `usage.total_tokens` AND `usage.source` — missing any → `IncompleteResponseError` (VAL-03 spirit: never coerce to zero). `contexts` may be `[]` (baseline). Reuse `time.perf_counter()` latency pattern.

- [ ] **Step 1: Failing tests** with a `FakeTransport` (copy the pattern from `tests/unit/test_openai_compat_target.py:12-21`): axon-arm payload shape (single message, flags, budget), baseline-arm payload shape (history + current question, flags, NO recall_max_tokens key), usage mapped into TurnResult, missing `usage.prompt_tokens` → IncompleteResponseError, non-200 → TargetRuntimeError.
- [ ] **Step 2: RED.** **Step 3: Implement.** **Step 4: GREEN + full suite.**
- [ ] **Step 5: Commit** — `feat: SessionTarget - per-turn arm-aware calls with real usage`.

---

### Task 5: GNOMON — session faithfulness judge (no ground truth required)

**Files:**
- Create: `~/dev/gnomon-eval/src/gnomon/judge/session_prompts.py`
- Create: `~/dev/gnomon-eval/src/gnomon/judge/session_judge.py`
- Test: `~/dev/gnomon-eval/tests/unit/test_session_judge.py`

**Interfaces:**
- Consumes: the Ollama call/JSON/seed/cache machinery in `judge/ollama.py` (same request shape: `options.seed = seed + run`, JSON-object answer, JudgeCache keyed by content hash), `JudgeError` taxonomy.
- Produces:

```python
def build_session_prompt(question: str, answer: str, contexts: list[str]) -> str
    # Faithfulness-only rubric: "score 0..1 how fully the ANSWER is grounded
    # in the CONTEXT below; contexts are the ONLY admissible evidence."
    # Returns strict-JSON instruction: {"faithfulness": <float>}

class SessionOllamaJudge:
    def __init__(self, *, model, base_url, cache, transport=None, timeout_s=60.0)
    def score_faithfulness(self, question, answer, contexts, *, seed: int, run: int) -> float
```

Implementation mirrors `OllamaJudge.score` (one model call, JSON parse, named errors on off-protocol, cache lookup first) but with the session prompt and a single metric. Why not reuse `OllamaJudge` directly: `build_prompt(case, response)` requires `EvalCase.expected_answer`/`expected_contexts` (ground truth), which scripted sessions do not have.

- [ ] **Step 1: Failing tests** with a fake transport returning `{"message": {"content": "{\"faithfulness\": 0.8}"}}`-shaped body (mirror `tests/unit/test_ollama_judge.py`'s fake): happy path returns 0.8; out-of-range value raises; non-JSON answer raises `JudgeProtocolError`; cache hit avoids a second transport call; `options.seed == seed + run` asserted on the sent payload.
- [ ] **Step 2: RED.** **Step 3: Implement.** **Step 4: GREEN + full suite.**
- [ ] **Step 5: Commit** — `feat: faithfulness-only session judge (no ground-truth requirement)`.

---

### Task 6: GNOMON — session runner

**Files:**
- Create: `~/dev/gnomon-eval/src/gnomon/runner/session_runner.py`
- Test: `~/dev/gnomon-eval/tests/unit/test_session_runner.py`

**Interfaces:**
- Consumes: `Session`, `TurnCost`, `SessionTarget.run_turn`, `SessionOllamaJudge.score_faithfulness`.
- Produces:

```python
class SessionRunReport(BaseModel):  # frozen
    turn_costs: list[TurnCost]                       # every session x turn x arm
    final_faithfulness: dict[str, MetricResult]      # arm -> MetricResult (CI over sessions)

def run_sessions(sessions, target, judge, *, judge_runs: int, seed: int,
                 confidence_level: float = 0.95) -> SessionRunReport
```

Core loop (the plan's contract — implementer writes exactly this behavior):
- For each session, for each arm: replay turns in order. History accumulates from the arm's OWN answers: after each turn append `{"role":"user",...}` + `{"role":"assistant","content": result.answer}` to that arm's history list. The axon arm still ACCUMULATES history locally (the runner tracks it) but never sends it — `run_turn` receives it only for the baseline payload; keep the accumulation in the runner so both arms share identical question sequences.
- Collect one `TurnCost` per turn per arm.
- After the last turn of each arm: judge the final answer `judge_runs` times against what the arm saw — axon arm: the final turn's retrieved `contexts`; baseline arm: the transcript it forwarded (serialize history to strings). Per-session score = mean of runs (ADR-008 denoising); `aggregate_metric("final_faithfulness_<arm>", per_session_scores, ...)` for the CI.
- Judge-call accounting: exactly `len(sessions) x 2 x judge_runs` calls (RNF-06) — assert this in a test with counting fakes.

- [ ] **Step 1: Failing tests** with fake target (scripted answers + fixed usage per call, counting calls) and fake judge (returns per-arm constants, counting calls): turn_costs has `sessions x turns x 2` entries with right arms/turns; baseline history grows (assert the fake target saw history length 2k at turn k); axon arm always sends empty history; judge called exactly `sessions x 2 x judge_runs` times; MetricResult n == len(sessions).
- [ ] **Step 2: RED.** **Step 3: Implement.** **Step 4: GREEN + full suite.**
- [ ] **Step 5: Commit** — `feat: session runner - dual-arm replay with per-turn cost and final-turn judging`.

---

### Task 7: GNOMON — savings curve reporting

**Files:**
- Create: `~/dev/gnomon-eval/src/gnomon/reporting/savings.py`
- Test: `~/dev/gnomon-eval/tests/unit/test_savings_report.py`

**Interfaces:**
- Consumes: `SessionRunReport`, `aggregate_metric(metric, values, *, confidence_level, seed)` (`metrics/confidence.py:31` — values need NOT be in [0,1]; negative savings are legal).
- Produces:

```python
def savings_report(report: SessionRunReport, *, seed: int, confidence_level=0.95) -> dict
# {
#   "per_turn": [{"turn": k, "savings_mean": ..., "ci_low": ..., "ci_high": ..., "n": S}],
#   "cumulative": {"savings_mean": ..., "ci_low": ..., "ci_high": ..., "n": S},   # headline
#   "crossover_turn": <first k where per-turn ci_low > 0, or null>,
#   "final_faithfulness": {"axon": {...}, "baseline": {...}},
#   "quality_gate": "pass" | "fail",     # fail = axon ci_high < baseline ci_low
#   "validity": {"non_provider_records": <int>},                                  # must be 0
#   "completion_tokens": {"axon_total": ..., "baseline_total": ...},              # reported, not headline
# }
def to_text(report_dict: dict) -> str   # human-readable: curve table + headline + gate verdicts
```

Math (per session s, turn k): `savings_k_s = 1 - axon_prompt(s,k) / baseline_prompt(s,k)`; cumulative per session: `1 - sum_k axon_prompt / sum_k baseline_prompt`; both aggregated across sessions with `aggregate_metric`. Baseline prompt of 0 for any turn → raise (never divide by zero silently).

- [ ] **Step 1: Failing tests** with synthetic TurnCosts (2 sessions x 3 turns, hand-computed expectations): per-turn means exact; cumulative exact; early negative savings preserved (turn 0 where axon costs more); crossover detection; quality_gate fail when axon ci_high < baseline ci_low; non-provider record counted; zero baseline prompt raises.
- [ ] **Step 2: RED.** **Step 3: Implement.** **Step 4: GREEN + full suite.**
- [ ] **Step 5: Commit** — `feat: savings-vs-turn curve report with CI, crossover and quality gate`.

---

### Task 8: GNOMON — [session] config + CLI subcommand + run configs

**Files:**
- Modify: `~/dev/gnomon-eval/src/gnomon/config/run_config.py` (add `SessionConfig`, `SessionRunConfig`)
- Modify: `~/dev/gnomon-eval/src/gnomon/cli.py` (add `session` subcommand; plain `gnomon -c` unchanged)
- Create: `~/dev/gnomon-eval/config/axon-session.toml`, `~/dev/gnomon-eval/config/axon-session-smoke.toml`
- Test: `~/dev/gnomon-eval/tests/unit/test_session_config.py` (+ config-parse tests for both TOMLs)

**Interfaces:**
- Produces: `SessionRunConfig.from_file(path)` with sections: `sessions_path` (str), `[eval]`-like `{seed, judge_runs, confidence_level}`, `[target]` (reuse `TargetConfig` + `recall_max_tokens: int = 2000`), `[judge]` (reuse `JudgeConfig`). CLI: `gnomon session -c config/axon-session.toml --json > session.json`; exit code 0 unless the quality gate fails (gate=exit 1, mirroring RF-09).
- CLI backward compat: `main(argv)` inspects `argv[0] == "session"` and routes to a session subparser; otherwise the existing parser runs untouched (existing CLI tests must keep passing unmodified).

`config/axon-session.toml` (full run):

```toml
# Wave 2 multi-turn savings measurement (ADR-0010).
# Generation calls = sessions x turns x 2; judge calls = sessions x 2 x judge_runs.
sessions_path = "datasets/sessions/sessions.json"

[eval]
seed = 42
judge_runs = 6
confidence_level = 0.95

[target]
kind = "openai_compat"
base_url = "http://localhost:8765/v1"
model = "axon"
timeout_s = 120.0
recall_max_tokens = 2000

[judge]
provider = "ollama"
model = "llama3.1:8b"
base_url = "http://100.78.123.92:11434"
timeout_s = 60.0
```

Smoke variant: `sessions_path = "datasets/sessions/smoke.json"`, `judge_runs = 2`.

- [ ] **Step 1: Failing tests** — SessionRunConfig parses a TOML string (tmp_path); both shipped TOMLs parse with the right recall budget; `gnomon session -c <smoke toml> --json` wiring test with monkeypatched runner returning a canned report (assert JSON on stdout, exit code from gate); plain `gnomon -c` path untouched (run one existing CLI test unchanged).
- [ ] **Step 2: RED.** **Step 3: Implement.** **Step 4: GREEN + full suite.**
- [ ] **Step 5: Commit** — `feat: session subcommand, config section and run configs`.

---

### Task 9: GNOMON — session dataset (LLM-drafted, vault-grounded, OWNER-GATED)

**Files:**
- Create: `~/dev/gnomon-eval/datasets/sessions/README.md`
- Create: `~/dev/gnomon-eval/datasets/sessions/sessions.json` (10 sessions x 10 turns) and `smoke.json` (3 x 5) — DRAFTED BY AGENT, APPROVED BY OWNER before commit.

**Process (this task is executed by the controller with a generation agent, not a code implementer):**
1. Generation agent receives: the topics and source notes of Wave 1's 17 validated cases (datasets/second_brain/cases.json + the provenance table), plus the rule that every turn must be answerable from indexed vault content (personal/career/knowledge contexts; never `work/`).
2. Each session = one coherent topic thread (e.g. "AXON ADR pipeline decisions", "rpg-master-ai RAG tuning history"), 10 user turns that a real owner would ask in sequence, including 2-3 referential turns ("e por que essa escolha?") — these stress the zero-history arm BY DESIGN and stay in.
3. Sessions validate against `load_sessions` (Task 3). Language: match the vault's language per topic (PT-BR/EN mixed is authentic).
4. OWNER GATE: the owner reviews the drafted sessions (are these questions I would ask? any topic to remove?) before commit. The claim's provenance line: "sessions LLM-drafted from vault topics, owner-reviewed".
5. Commit: `feat: vault-grounded session dataset (LLM-drafted, owner-reviewed)`.

README content: schema, generation provenance, the zero-history arm caveat, regeneration instructions.

---

### Task 10: GNOMON — ADR-0010 + session runbook

**Files:**
- Create: `~/dev/gnomon-eval/docs/adr/0010-multiturn-savings-measurement.md` (house format: `# ADR-010:` title, `**Date:**`/`**Status:**`, Context / Decision / Consequences (Upsides/Downsides/Neutral) / Alternatives considered table / Relations)
- Create: `~/dev/gnomon-eval/docs/RUNBOOK-session-savings.md`

**ADR-010 required content:** measurement design (arms, zero-history, budget 2000, prompt-token headline, CI over sessions, final-turn quality gate); session provenance (LLM-drafted, owner-reviewed); the retirement of `benchmarks/model.py`; Relations: Requires ADR-009; Relates to ADR-004, ADR-008; Requires axon `forward_history`/`recall_max_tokens` fields.

**Runbook required content:**
1. Env: `AXON_MAX_PRE_SEND_TOKENS=32000 AXON_COMPLETION_MODEL="ollama/llama3.1:8b" AXON_PROVIDER_OLLAMA=1 OLLAMA_BASE_URL="http://100.78.123.92:11434" ~/.pyenv/versions/clock/bin/axon serve-http --port 8765`
2. Smoke first: `gnomon session -c config/axon-session-smoke.toml --json` — verify every turn `usage_source=provider` and the curve JSON is sane BEFORE the full run.
3. Full run + stability replicate (2x full run; cumulative-savings means mutually within CIs).
4. Validity checklist: zero non-provider records; quality gate pass; stability pass; crossover turn reported alongside the headline (never publish the headline without the curve).
5. Propagation checklist (owner): axon README badge + docs/METRICS.md swap to the measured claim template: "AXON's fixed-recall arm uses X% fewer input tokens over N-turn sessions (95% CI over M sessions, llama3.1:8b), with final-turn faithfulness held at parity; savings cross zero at turn K. Projection retired: 52.3% (deterministic model)."
6. Session assumptions block (copied from this plan's design decision 3 + the architect's stated-assumptions list) — published verbatim with the number.

**Commit:** `docs: ADR-010 and session-savings runbook`.

---

## Execution order and dependencies

```
axon:   Task 1 -> 2                       (branch feat/session-savings-wave2, stacked on Wave 1)
gnomon: Task 3 -> 4 -> 5 -> 6 -> 7 -> 8   (branch feat/session-savings-harness, stacked on Wave 1)
        Task 9 (dataset, owner-gated) after 3; Task 10 anytime after 8
Measured run (runbook): needs 1-10 + live stack; then propagation (owner)
```

Tasks 3-8 do not depend on axon Tasks 1-2 at build time (SessionTarget is contract-driven and unit-tested against FakeTransport); the live smoke is the integration point.

## Out of scope (deliberate)

- Recent-window AXON arm variant (owner deferred; revisit after v1 numbers).
- Retrieval-query enrichment for referential turns (risk 3 accepted and stated; a future "query = last turn + recall of thread" experiment).
- README/LinkedIn propagation edits (owner-gated, after a valid measured run).
- Any change to gnomon's single-turn domain contract (`RagResponse`/`EvalCase`/`EvalReport` untouched).
