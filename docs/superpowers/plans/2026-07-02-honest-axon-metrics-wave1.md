# Honest AXON Metrics — Wave 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce one real, reproducible A/B number — "AXON recall lifts faithfulness A→B (95% CI, N cases) at a cost of +E input tokens/turn" — measured with real provider token usage, never the `len//4` estimate.

**Architecture:** Two repos. In `~/dev/axon`: expose the provider's real usage from the router (`complete_with_usage`), add an `include_context` toggle to the OpenAI-compatible endpoint, and log per-request recall telemetry to JSONL. In `~/dev/gnomon-eval`: pass the toggle through `OpenAICompatTarget`, add recall-on/recall-off configs, and add a compare module that turns two `--json` reports (plus the AXON telemetry) into the final claim.

**Tech Stack:** Python 3.12, FastAPI, litellm, pydantic v2, pytest (+pytest-asyncio in axon), tomllib.

## Global Constraints

- TDD on every code task: write the failing test, run it RED, implement, run GREEN, commit. No production code before a red test.
- Two repos, two branches: `~/dev/axon` → branch `feat/honest-usage-wave1`; `~/dev/gnomon-eval` → branch `feat/ab-recall-compare`. Create each with `git checkout -b <name>` before that repo's first task.
- Run axon tests from `~/dev/axon`, gnomon tests from `~/dev/gnomon-eval`, always with `python -m pytest <path> -v`.
- Never break the existing gnomon contract: `contexts` (top-level list) and `usage.total_tokens` must always be present in the AXON endpoint response (see `axon/http/app.py` module docstring).
- Code, comments, commit messages in English. No em/en dashes in docs — plain `-` only.
- Wave 2 (multi-turn token-savings harness) is explicitly OUT of this plan. Wave 1 claims quality lift + recall cost, never "savings".

**Owner actions outside this plan (do them now, they don't wait for code):**
1. Soften/label the current LinkedIn 52.3% number as "deterministic model projection" or pull it. Wave 1 cannot back a savings claim.
2. Task 8 (dataset cases) is owner hand-labor; agents only scaffold.

---

## Design decisions locked by this plan

1. **Router change is required for linchpin 1.** `complete()` (`axon/src/axon/router/engine.py:227-292`) returns only `response.choices[0].message.content`; litellm's `response.usage` is discarded. Smallest root-cause fix: refactor the body into `complete_with_usage() -> tuple[str, CompletionUsage | None]` and keep `complete()` as a one-line wrapper. Both existing callers (`http/app.py:139`, `validation/judge.py:38`) keep working unchanged.
2. **Honest fallback is labeled, not silent.** When the provider reports no usage, or the LLM call fails (the endpoint's existing degraded path), the endpoint falls back to the char estimate but marks `"source": "estimate"` in `usage` and in telemetry. An eval run is only valid if every record says `provider`.
3. **Recall-off skips retrieval entirely** (raw query, `contexts: []`). Gnomon's VAL-03 accepts an empty list (it only rejects `None`, `openai_compat.py:83-89`).
4. **`context_precision` is meaningless for the off run** (no contexts to score). The off config ships an empty `[gate]` (baseline run, never gated) and the compare module prints on-only metrics as "no off-run baseline".
5. **The "+E input tokens/turn" claim comes from AXON telemetry, not gnomon reports.** Gnomon's `RagResponse`/`CaseCost` only carry `total_tokens`; the prompt/completion split lives in the new recall JSONL. The compare module reads both.

---

### Task 1: AXON — `complete_with_usage()` surfaces provider usage

**Files:**
- Modify: `~/dev/axon/src/axon/router/engine.py` (refactor `complete`, lines 227-292)
- Test: `~/dev/axon/tests/router/test_complete_usage.py` (new)

**Interfaces:**
- Consumes: existing `route()`, `TaskRequest`, litellm pipeline in `engine.py` (unchanged).
- Produces: `CompletionUsage` frozen dataclass with fields `model: str`, `prompt_tokens: int`, `completion_tokens: int`, `total_tokens: int`; `async def complete_with_usage(task: TaskRequest, messages: list[dict]) -> tuple[str, CompletionUsage | None]`; `complete()` keeps its exact current signature `async def complete(task, messages) -> str`.

- [ ] **Step 1: Write the failing test**

Create `tests/router/test_complete_usage.py` (mock scaffold copied from the working pattern in `tests/router/test_budget_guardrails.py`):

```python
"""complete_with_usage() must surface the provider's real token usage.

The litellm response carries `usage` (prompt/completion/total). The router
previously discarded it; these tests pin the new contract: content + typed
usage out, None usage when the provider reports none, and complete() stays
a string-returning wrapper.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from axon.router.classifier import TaskType
from axon.router.engine import (
    CompletionUsage,
    TaskRequest,
    complete,
    complete_with_usage,
)


class _FakeBreaker:
    def allow_call(self, _key: str) -> bool:
        return True

    def record_success(self, _key: str) -> None:
        return None

    def record_failure(self, _key: str) -> None:
        return None


def _patch_pipeline(monkeypatch, fake_acompletion) -> None:
    monkeypatch.setattr(
        "axon.router.engine.classify_task_with_source",
        lambda content, ctx=None: (TaskType.CODE_ANALYSIS, "local"),
    )
    monkeypatch.setattr("axon.router.engine.daily_cost", lambda: 0.0)
    monkeypatch.setattr("axon.router.engine.provider_for_model", lambda _m: "anthropic")
    monkeypatch.setattr(
        "axon.router.engine.validate_anthropic_cache_control", lambda _msgs: None
    )
    monkeypatch.setattr(
        "axon.router.engine.count_tokens_for_provider", lambda _p, _m: 100
    )
    monkeypatch.setattr("axon.router.engine._BREAKER", _FakeBreaker())
    monkeypatch.setattr("axon.router.engine.litellm.acompletion", fake_acompletion)


@pytest.mark.asyncio
async def test_complete_with_usage_returns_provider_usage(monkeypatch) -> None:
    async def fake_acompletion(**_kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(
                prompt_tokens=321, completion_tokens=45, total_tokens=366
            ),
        )

    _patch_pipeline(monkeypatch, fake_acompletion)

    content, usage = await complete_with_usage(
        TaskRequest(content="explain recall", ctx="knowledge"), messages=[]
    )

    assert content == "ok"
    assert isinstance(usage, CompletionUsage)
    assert usage.prompt_tokens == 321
    assert usage.completion_tokens == 45
    assert usage.total_tokens == 366
    assert usage.model  # the routed model name, never empty


@pytest.mark.asyncio
async def test_complete_with_usage_none_when_provider_omits_usage(monkeypatch) -> None:
    async def fake_acompletion(**_kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )

    _patch_pipeline(monkeypatch, fake_acompletion)

    content, usage = await complete_with_usage(
        TaskRequest(content="q", ctx="knowledge"), messages=[]
    )

    assert content == "ok"
    assert usage is None


@pytest.mark.asyncio
async def test_complete_still_returns_plain_string(monkeypatch) -> None:
    async def fake_acompletion(**_kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(
                prompt_tokens=1, completion_tokens=1, total_tokens=2
            ),
        )

    _patch_pipeline(monkeypatch, fake_acompletion)

    response = await complete(
        TaskRequest(content="q", ctx="knowledge"), messages=[]
    )

    assert response == "ok"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/dev/axon && python -m pytest tests/router/test_complete_usage.py -v`
Expected: FAIL/ERROR with `ImportError: cannot import name 'CompletionUsage'`.

- [ ] **Step 3: Implement in `engine.py`**

Add near the top of `engine.py` (after existing imports; `dataclasses` may already be imported for `TaskRequest` — reuse):

```python
@dataclass(frozen=True)
class CompletionUsage:
    """Real token usage reported by the provider for one completion."""

    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
```

Rename the existing `complete()` to `complete_with_usage()` with the new return type; the only body change is at the end (current line 292):

```python
async def complete_with_usage(
    task: TaskRequest, messages: list[dict]
) -> tuple[str, CompletionUsage | None]:
    """Roteia e executa a completion, retornando o usage real do provider."""
    # ... entire existing body of complete() unchanged up to the litellm call ...
    try:
        response = await litellm.acompletion(**completion_kwargs)
        _BREAKER.record_success(breaker_key)
    except Exception:
        _BREAKER.record_failure(breaker_key)
        raise
    content = response.choices[0].message.content
    raw_usage = getattr(response, "usage", None)
    usage: CompletionUsage | None = None
    if raw_usage is not None:
        usage = CompletionUsage(
            model=result.model,
            prompt_tokens=int(getattr(raw_usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(raw_usage, "completion_tokens", 0) or 0),
            total_tokens=int(getattr(raw_usage, "total_tokens", 0) or 0),
        )
    return content, usage


async def complete(task: TaskRequest, messages: list[dict]) -> str:
    """Roteia e executa a completion (compat wrapper, discards usage)."""
    content, _usage = await complete_with_usage(task, messages)
    return content
```

- [ ] **Step 4: Run the new tests and the full router suite**

Run: `cd ~/dev/axon && python -m pytest tests/router/ -v`
Expected: all PASS (existing `test_budget_guardrails.py` exercises the wrapper path: its fake acompletion has no `usage` attribute, which is exactly the None branch).

- [ ] **Step 5: Commit**

```bash
cd ~/dev/axon
git add src/axon/router/engine.py tests/router/test_complete_usage.py
git commit -m "feat: complete_with_usage surfaces real provider token usage"
```

---

### Task 2: AXON — endpoint reports real usage (kills `len//4` on the response path)

**Files:**
- Modify: `~/dev/axon/src/axon/http/app.py` (lines 107-146, 160)
- Modify: `~/dev/axon/tests/http/test_chat_completions.py` (mock + usage tests)

**Interfaces:**
- Consumes: `complete_with_usage`, `CompletionUsage` from Task 1.
- Produces: response `usage` block `{"prompt_tokens": int, "completion_tokens": int, "total_tokens": int, "source": "provider"|"estimate"}`. `total_tokens` stays present (gnomon contract). Handler-local variables `prompt_tokens`, `completion_tokens`, `total_tokens`, `model_used`, `usage_source` (Task 4 telemetry reads them).

- [ ] **Step 1: Update the test mocks and write the failing tests**

In `tests/http/test_chat_completions.py`, replace the complete mock (lines 63-77) — the handler now calls `complete_with_usage`:

```python
from axon.router.engine import CompletionUsage

_FAKE_ANSWER = "AXON uses exponential-decay recency scoring for recall ranking."
_FAKE_USAGE = CompletionUsage(
    model="ollama/qwen2.5:7b", prompt_tokens=512, completion_tokens=64, total_tokens=576
)

_PATCH_RETRIEVE = "axon.mcp.server._retrieve_context"
_PATCH_COMPLETE = "axon.router.engine.complete_with_usage"


def _make_complete_mock() -> AsyncMock:
    """Return an AsyncMock for complete_with_usage: (answer, usage)."""
    return AsyncMock(return_value=(_FAKE_ANSWER, _FAKE_USAGE))
```

Add the new contract tests at the end of the "response shape" section:

```python
def test_usage_matches_provider_usage(client: TestClient) -> None:
    """usage must be the provider's real numbers, not a char estimate."""
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "explain recall"}]},
    )
    usage = resp.json()["usage"]
    assert usage["prompt_tokens"] == _FAKE_USAGE.prompt_tokens
    assert usage["completion_tokens"] == _FAKE_USAGE.completion_tokens
    assert usage["total_tokens"] == _FAKE_USAGE.total_tokens
    assert usage["source"] == "provider"


def test_usage_falls_back_to_estimate_when_provider_omits_usage() -> None:
    with (
        patch(_PATCH_RETRIEVE, new=_make_retrieve_mock()),
        patch(_PATCH_COMPLETE, new=AsyncMock(return_value=(_FAKE_ANSWER, None))),
    ):
        with TestClient(app) as c:
            resp = c.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "x"}]},
            )
    usage = resp.json()["usage"]
    assert usage["source"] == "estimate"
    assert usage["total_tokens"] > 0
```

Also update `test_llm_error_still_returns_contexts` (line 244): the failing mock patches `_PATCH_COMPLETE` (now `complete_with_usage`) — the assertions already hold; add one line at the end:

```python
    assert body["usage"]["source"] == "estimate"
```

- [ ] **Step 2: Run to verify RED**

Run: `cd ~/dev/axon && python -m pytest tests/http/test_chat_completions.py -v`
Expected: new tests FAIL (`KeyError: 'prompt_tokens'` / `'source'`); old ones may fail on the changed mock — that's fine, GREEN comes next.

- [ ] **Step 3: Rewrite the LLM-call + usage section of the handler**

In `app.py`, replace lines 107-108 (imports) and 136-146 (LLM call + usage accounting):

```python
    from axon.mcp.server import _retrieve_context  # noqa: PLC0415
    from axon.router.engine import TaskRequest, complete_with_usage  # noqa: PLC0415
```

```python
    # --- LLM completion --------------------------------------------------
    task = TaskRequest(content=augmented_query)
    try:
        answer, usage = await complete_with_usage(task, messages=[])
    except Exception as exc:
        # Surface retrieval context even when the LLM call fails so the
        # evaluator can still score recall from ``contexts``.
        answer = f"[LLM unavailable: {exc}]\n\nContext:\n{context_block}"
        usage = None

    # --- usage accounting -------------------------------------------------
    # Provider-reported numbers when available; a labeled estimate otherwise.
    # An eval run is only honest if every request reports source="provider".
    if usage is not None:
        usage_source = "provider"
        prompt_tokens = usage.prompt_tokens
        completion_tokens = usage.completion_tokens
        total_tokens = usage.total_tokens
        model_used = usage.model
    else:
        usage_source = "estimate"
        prompt_tokens = _estimate_tokens(augmented_query)
        completion_tokens = _estimate_tokens(answer)
        total_tokens = prompt_tokens + completion_tokens
        model_used = request.model
```

And the response body's usage entry (line 160) becomes:

```python
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "source": usage_source,
        },
```

- [ ] **Step 4: Run the HTTP suite GREEN**

Run: `cd ~/dev/axon && python -m pytest tests/http/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/dev/axon
git add src/axon/http/app.py tests/http/test_chat_completions.py
git commit -m "feat: chat-completions usage reports real provider tokens with labeled fallback"
```

---

### Task 3: AXON — `include_context` recall toggle

**Files:**
- Modify: `~/dev/axon/src/axon/http/app.py` (request model line 69, retrieval block lines 114-134)
- Modify: `~/dev/axon/tests/http/test_chat_completions.py` (new section)

**Interfaces:**
- Consumes: handler structure from Task 2.
- Produces: `ChatCompletionRequest.include_context: bool = True`. When `false`: no retrieval call, `contexts: []`, the LLM receives the raw query.

- [ ] **Step 1: Write the failing tests**

Append a new section to `tests/http/test_chat_completions.py`:

```python
# ---------------------------------------------------------------------------
# Tests — include_context toggle (recall on/off for A/B evals)
# ---------------------------------------------------------------------------


def test_include_context_false_skips_retrieval() -> None:
    mock_retrieve = _make_retrieve_mock()
    mock_complete = _make_complete_mock()
    with (
        patch(_PATCH_RETRIEVE, new=mock_retrieve),
        patch(_PATCH_COMPLETE, new=mock_complete),
    ):
        with TestClient(app) as c:
            resp = c.post(
                "/v1/chat/completions",
                json={
                    "include_context": False,
                    "messages": [{"role": "user", "content": "explain recall"}],
                },
            )
    assert resp.status_code == 200
    mock_retrieve.assert_not_called()
    assert resp.json()["contexts"] == []
    # The LLM must receive the raw query, not an augmented prompt.
    task_sent = mock_complete.call_args.args[0]
    assert task_sent.content == "explain recall"


def test_include_context_defaults_to_true(client: TestClient) -> None:
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "explain recall"}]},
    )
    assert resp.json()["contexts"] == list(_FAKE_SEGMENTS)
```

- [ ] **Step 2: Run to verify RED**

Run: `cd ~/dev/axon && python -m pytest tests/http/test_chat_completions.py -k include_context -v`
Expected: `test_include_context_false_skips_retrieval` FAILS (retrieval still called / contexts non-empty).

- [ ] **Step 3: Implement**

Request model:

```python
class ChatCompletionRequest(BaseModel):
    model: str = "axon"
    messages: list[_Message]
    include_context: bool = True
```

Wrap the retrieval block (current lines 114-134) in the branch:

```python
    # --- retrieval -------------------------------------------------------
    if request.include_context:
        try:
            _raw_context, pack, _hits = await _retrieve_context(
                query=query,
                ctx=None,
                language=None,
                max_depth=2,
                max_nodes=25,
                max_tokens=4000,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Retrieval error: {exc}") from exc

        # Surface individual segment strings (not the combined formatted text).
        context_segments: list[str] = list(pack.segments)
        context_block = (
            "\n\n".join(context_segments) if context_segments else "(no context retrieved)"
        )
        augmented_query = (
            f"Context retrieved from AXON:\n{context_block}\n\nQuestion: {query}"
        )
    else:
        # Recall disabled (A/B baseline): raw query, no retrieval cost.
        context_segments = []
        context_block = "(recall disabled)"
        augmented_query = query
```

- [ ] **Step 4: Run the HTTP suite GREEN**

Run: `cd ~/dev/axon && python -m pytest tests/http/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/dev/axon
git add src/axon/http/app.py tests/http/test_chat_completions.py
git commit -m "feat: include_context toggle on chat-completions for recall A/B"
```

---

### Task 4: AXON — per-request recall telemetry (JSONL)

**Files:**
- Create: `~/dev/axon/src/axon/observability/recall_telemetry.py`
- Modify: `~/dev/axon/src/axon/http/app.py` (append a record before building the response body)
- Test: `~/dev/axon/tests/observability/test_recall_telemetry.py` (new)
- Modify: `~/dev/axon/tests/http/test_chat_completions.py` (one endpoint test)

**Interfaces:**
- Consumes: handler locals from Tasks 2-3 (`prompt_tokens`, `completion_tokens`, `total_tokens`, `model_used`, `usage_source`, `request.include_context`).
- Produces: `RecallRecord` (pydantic, frozen) with fields `ts: str`, `caller: str`, `include_context: bool`, `model: str`, `prompt_tokens: int`, `completion_tokens: int`, `total_tokens: int`, `usage_source: Literal["provider", "estimate"]`; `RecallTelemetryStore` with `.append(record)`, `.load_all()`, `.stats_file` writing `<data_root>/recall/requests.jsonl`. This JSONL is Plan B's living-document data source and Task 7's `--telemetry` input.

- [ ] **Step 1: Write the failing store test**

Create `tests/observability/test_recall_telemetry.py` (pattern mirrors `tests/observability/test_compression_telemetry.py:27-29`):

```python
"""RecallTelemetryStore: one JSONL record per chat-completions request."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from axon.observability.recall_telemetry import RecallRecord, RecallTelemetryStore


def _make_store(tmp_path: Path) -> RecallTelemetryStore:
    runtime = SimpleNamespace(data_root=tmp_path)
    return RecallTelemetryStore(runtime=runtime)  # type: ignore[arg-type]


def _record(**overrides) -> RecallRecord:
    base = dict(
        ts="2026-07-02T00:00:00+00:00",
        caller="http",
        include_context=True,
        model="ollama/qwen2.5:7b",
        prompt_tokens=512,
        completion_tokens=64,
        total_tokens=576,
        usage_source="provider",
    )
    base.update(overrides)
    return RecallRecord(**base)


def test_append_then_load_roundtrip(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.append(_record())
    store.append(_record(include_context=False, prompt_tokens=40, total_tokens=104))

    records = store.load_all()

    assert len(records) == 2
    assert records[0].prompt_tokens == 512
    assert records[0].usage_source == "provider"
    assert records[1].include_context is False


def test_load_all_empty_when_file_missing(tmp_path: Path) -> None:
    assert _make_store(tmp_path).load_all() == []


def test_stats_file_lives_under_recall_dir(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    assert store.stats_file == tmp_path / "recall" / "requests.jsonl"
```

- [ ] **Step 2: Run to verify RED**

Run: `cd ~/dev/axon && python -m pytest tests/observability/test_recall_telemetry.py -v`
Expected: ERROR `ModuleNotFoundError: axon.observability.recall_telemetry`.

- [ ] **Step 3: Implement the store**

Create `src/axon/observability/recall_telemetry.py` (mirror of `compression_telemetry.py:12-52`, no summary needed yet):

```python
"""Per-request recall telemetry for the OpenAI-compatible endpoint.

One JSONL record per /v1/chat/completions request, with the provider's real
token usage and the include_context flag. This is the evidence source for
the recall-cost claim ("+E input tokens/turn") and for the living metrics
page: gnomon-eval reads it via the compare module's --telemetry option.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from axon.config.runtime import RuntimeConfig, load_runtime_config


class RecallRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    ts: str
    caller: str  # "http" today; other transports may write here later
    include_context: bool
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    # "provider" = real usage from the LLM provider; "estimate" = len//4
    # fallback (LLM failure or provider without usage). Eval runs are only
    # valid when every record in the window says "provider".
    usage_source: Literal["provider", "estimate"]


class RecallTelemetryStore:
    def __init__(self, runtime: RuntimeConfig | None = None) -> None:
        self._runtime = runtime or load_runtime_config()
        self._file = self._runtime.data_root / "recall" / "requests.jsonl"

    @property
    def stats_file(self) -> Path:
        return self._file

    def append(self, record: RecallRecord) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        with self._file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.model_dump(), sort_keys=True) + "\n")

    def load_all(self) -> list[RecallRecord]:
        if not self._file.exists():
            return []
        records = []
        with self._file.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(RecallRecord(**json.loads(line)))
        return records
```

- [ ] **Step 4: Run store tests GREEN**

Run: `cd ~/dev/axon && python -m pytest tests/observability/test_recall_telemetry.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Write the failing endpoint test (one request writes one record)**

Append to `tests/http/test_chat_completions.py`:

```python
def test_request_appends_recall_telemetry_record() -> None:
    with (
        patch(_PATCH_RETRIEVE, new=_make_retrieve_mock()),
        patch(_PATCH_COMPLETE, new=_make_complete_mock()),
        patch(
            "axon.observability.recall_telemetry.RecallTelemetryStore.append"
        ) as mock_append,
    ):
        with TestClient(app) as c:
            c.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "explain recall"}]},
            )
    mock_append.assert_called_once()
    record = mock_append.call_args.args[0]
    assert record.include_context is True
    assert record.prompt_tokens == _FAKE_USAGE.prompt_tokens
    assert record.total_tokens == _FAKE_USAGE.total_tokens
    assert record.usage_source == "provider"
    assert record.caller == "http"
```

Run: `cd ~/dev/axon && python -m pytest tests/http/test_chat_completions.py::test_request_appends_recall_telemetry_record -v`
Expected: FAIL (`append` never called).

- [ ] **Step 6: Wire the endpoint**

In `app.py`, right after the usage-accounting block and before `response_id = ...`:

```python
    # --- telemetry ---------------------------------------------------------
    from axon.observability.recall_telemetry import (  # noqa: PLC0415
        RecallRecord,
        RecallTelemetryStore,
    )

    record = RecallRecord(
        ts=datetime.now(timezone.utc).isoformat(),
        caller="http",
        include_context=request.include_context,
        model=model_used,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        usage_source=usage_source,
    )
    try:
        RecallTelemetryStore().append(record)
    except OSError:
        logger.warning("recall telemetry append failed", exc_info=True)
```

Add at module top of `app.py`:

```python
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
```

- [ ] **Step 7: Full axon suite GREEN**

Run: `cd ~/dev/axon && python -m pytest tests/http/ tests/observability/ tests/router/ -v`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
cd ~/dev/axon
git add src/axon/observability/recall_telemetry.py src/axon/http/app.py \
        tests/observability/test_recall_telemetry.py tests/http/test_chat_completions.py
git commit -m "feat: per-request recall telemetry JSONL with real provider usage"
```

---

### Task 5: GNOMON — `include_context` passthrough in the target

**Files:**
- Modify: `~/dev/gnomon-eval/src/gnomon/config/run_config.py` (`TargetConfig`, lines 19-26)
- Modify: `~/dev/gnomon-eval/src/gnomon/targets/openai_compat.py` (`__init__` + `query`, lines 40-65)
- Modify: `~/dev/gnomon-eval/src/gnomon/cli.py` (`build_target`, lines 36-42)
- Test: `~/dev/gnomon-eval/tests/unit/test_openai_compat_target.py`, `~/dev/gnomon-eval/tests/unit/test_run_config.py`

**Interfaces:**
- Consumes: existing `FakeTransport` test helper (`test_openai_compat_target.py:12-21`).
- Produces: `TargetConfig.include_context: bool | None = None`; `OpenAICompatTarget(include_context: bool | None = None)`; when not None the request payload carries `"include_context": <bool>`; when None the payload is byte-identical to today (backward compatible with any OpenAI-compatible server).

- [ ] **Step 1: Write the failing target tests**

Append to `tests/unit/test_openai_compat_target.py`:

```python
def test_include_context_flag_sent_in_payload():
    transport = FakeTransport(body=_ok_body())
    target = OpenAICompatTarget(
        base_url="http://localhost:8000/v1",
        model="axon",
        transport=transport,
        include_context=False,
    )
    target.query("q")
    _url, payload = transport.calls[0]
    assert payload["include_context"] is False


def test_include_context_omitted_by_default():
    transport = FakeTransport(body=_ok_body())
    _target(transport).query("q")
    _url, payload = transport.calls[0]
    assert "include_context" not in payload
```

- [ ] **Step 2: Run to verify RED**

Run: `cd ~/dev/gnomon-eval && python -m pytest tests/unit/test_openai_compat_target.py -k include_context -v`
Expected: FAIL (`unexpected keyword argument 'include_context'`).

- [ ] **Step 3: Implement**

`openai_compat.py` — add the parameter and payload line:

```python
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        transport: HttpTransport | None = None,
        api_key: str | None = None,
        timeout_s: float = 30.0,
        contexts_field: str = "contexts",
        include_context: bool | None = None,
    ) -> None:
        ...
        self._include_context = include_context
```

In `query()`, after building `payload`:

```python
        if self._include_context is not None:
            payload["include_context"] = self._include_context
```

`run_config.py` — add to `TargetConfig`:

```python
    include_context: bool | None = None
```

`cli.py` — pass it through in `build_target`:

```python
    return OpenAICompatTarget(
        base_url=cfg.base_url,
        model=cfg.model,
        api_key=api_key,
        timeout_s=cfg.timeout_s,
        contexts_field=cfg.contexts_field,
        include_context=cfg.include_context,
    )
```

- [ ] **Step 4: Add a config-parse test and run everything GREEN**

Append to `tests/unit/test_run_config.py` (follow the file's existing TOML-string fixture style):

```python
def test_target_include_context_parses(tmp_path):
    toml = (
        'dataset_path = "d.json"\n'
        "[eval]\nreproducible = true\nseed = 1\njudge_runs = 2\nconfidence_level = 0.95\n"
        '[target]\nkind = "openai_compat"\nbase_url = "http://x/v1"\n'
        'model = "axon"\ninclude_context = false\n'
        '[judge]\nprovider = "stub"\n'
        "[gate]\n"
    )
    path = tmp_path / "cfg.toml"
    path.write_text(toml)
    cfg = RunConfig.from_file(path)
    assert cfg.target.include_context is False
```

(If `EvalConfig` requires different field names, copy the `[eval]` block from an existing passing test in this file.)

Run: `cd ~/dev/gnomon-eval && python -m pytest tests/unit/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/dev/gnomon-eval
git add src/gnomon/targets/openai_compat.py src/gnomon/config/run_config.py src/gnomon/cli.py \
        tests/unit/test_openai_compat_target.py tests/unit/test_run_config.py
git commit -m "feat: include_context passthrough for recall A/B targets"
```

---

### Task 6: GNOMON — recall-on / recall-off configs

**Files:**
- Create: `~/dev/gnomon-eval/config/axon-recall-on.toml`
- Create: `~/dev/gnomon-eval/config/axon-recall-off.toml`
- Test: `~/dev/gnomon-eval/tests/unit/test_ab_configs.py` (new)

**Interfaces:**
- Consumes: `RunConfig.from_file`, `TargetConfig.include_context` (Task 5).
- Produces: the two config files Task 10's runbook invokes. `dataset_path` points at `datasets/second_brain/cases.json` (Task 8, owner-written).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ab_configs.py`:

```python
"""The shipped A/B configs must parse and differ only in the recall flag."""
from pathlib import Path

from gnomon.config.run_config import RunConfig

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def test_recall_on_config_parses_with_flag_true():
    cfg = RunConfig.from_file(_CONFIG_DIR / "axon-recall-on.toml")
    assert cfg.target.include_context is True
    assert cfg.target.kind == "openai_compat"


def test_recall_off_config_parses_with_flag_false_and_no_gate():
    cfg = RunConfig.from_file(_CONFIG_DIR / "axon-recall-off.toml")
    assert cfg.target.include_context is False
    # Baseline run is never gated: context metrics are meaningless without recall.
    assert cfg.gate.thresholds == {}


def test_ab_configs_share_dataset_and_judge():
    on = RunConfig.from_file(_CONFIG_DIR / "axon-recall-on.toml")
    off = RunConfig.from_file(_CONFIG_DIR / "axon-recall-off.toml")
    assert on.dataset_path == off.dataset_path
    assert on.eval == off.eval
    assert on.judge == off.judge
```

Run: `cd ~/dev/gnomon-eval && python -m pytest tests/unit/test_ab_configs.py -v`
Expected: FAIL (files missing).

- [ ] **Step 2: Create the two configs**

`config/axon-recall-on.toml`:

```toml
# AXON A/B evaluation - recall ON arm.
# Same dataset, judge and eval settings as axon-recall-off.toml; the only
# difference is target.include_context. Compare with:
#   python -m gnomon.reporting.compare on.json off.json

dataset_path = "datasets/second_brain/cases.json"

[eval]
reproducible = true
seed = 42
judge_runs = 8
confidence_level = 0.95

[target]
kind = "openai_compat"
base_url = "http://localhost:8765/v1"
model = "axon"
contexts_field = "contexts"
timeout_s = 30.0
include_context = true

[judge]
provider = "ollama"
model = "llama3"
base_url = "http://localhost:11434"
timeout_s = 60.0

[gate]
faithfulness = 0.75
context_precision = 0.70
```

`config/axon-recall-off.toml`: identical except:

```toml
# AXON A/B evaluation - recall OFF arm (baseline: raw query, no retrieval).
# No [gate] thresholds: this arm is a measurement baseline, never a CI gate,
# and context metrics are meaningless without retrieved contexts.
```

with `include_context = false` and an empty `[gate]` section (header present, no keys).

- [ ] **Step 3: Run GREEN**

Run: `cd ~/dev/gnomon-eval && python -m pytest tests/unit/test_ab_configs.py -v`
Expected: 3 PASS.

- [ ] **Step 4: Commit**

```bash
cd ~/dev/gnomon-eval
git add config/axon-recall-on.toml config/axon-recall-off.toml tests/unit/test_ab_configs.py
git commit -m "feat: recall on/off A/B run configs"
```

---

### Task 7: GNOMON — compare module (A/B report diff + recall cost)

**Files:**
- Create: `~/dev/gnomon-eval/src/gnomon/reporting/compare.py`
- Test: `~/dev/gnomon-eval/tests/unit/test_compare.py` (new)

**Interfaces:**
- Consumes: the `to_dict` report shape (`reporting/report.py:10-36`: `metrics[]` with `metric/mean/ci_low/ci_high/n/confidence_level`, `cost.total_tokens`, `per_case[]` with `case_id/total_tokens`); optionally AXON's recall JSONL (Task 4 field names).
- Produces: `compare(on: dict, off: dict) -> str` and `telemetry_cost_line(records: list[dict]) -> str`; CLI `python -m gnomon.reporting.compare on.json off.json [--telemetry path/to/requests.jsonl]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_compare.py`:

```python
"""compare(): quality deltas from two report dicts + recall token cost."""
from gnomon.reporting.compare import compare, telemetry_cost_line


def _metric(name, mean, lo, hi, n=15):
    return {
        "metric": name, "mean": mean, "ci_low": lo, "ci_high": hi,
        "n": n, "confidence_level": 0.95,
    }


def _report(metrics, per_case):
    return {
        "metrics": metrics,
        "cost": {
            "total_tokens": sum(c["total_tokens"] for c in per_case),
            "mean_latency_ms": 100.0,
        },
        "per_case": per_case,
    }


_ON = _report(
    [_metric("faithfulness", 0.85, 0.80, 0.90),
     _metric("context_precision", 0.78, 0.70, 0.86)],
    [{"case_id": "c1", "total_tokens": 900, "latency_ms": 100.0},
     {"case_id": "c2", "total_tokens": 1100, "latency_ms": 100.0}],
)
_OFF = _report(
    [_metric("faithfulness", 0.60, 0.52, 0.68)],
    [{"case_id": "c1", "total_tokens": 300, "latency_ms": 80.0},
     {"case_id": "c2", "total_tokens": 500, "latency_ms": 80.0}],
)


def test_metric_delta_reported():
    out = compare(_ON, _OFF)
    assert "faithfulness" in out
    assert "+0.250" in out  # 0.85 - 0.60
    assert "[0.800, 0.900]" in out and "[0.520, 0.680]" in out


def test_on_only_metric_flagged_as_no_baseline():
    out = compare(_ON, _OFF)
    assert "context_precision" in out
    assert "no off-run baseline" in out


def test_per_case_token_delta():
    out = compare(_ON, _OFF)
    # mean per-case delta: ((900-300) + (1100-500)) / 2 = 600
    assert "+600" in out


def test_telemetry_cost_line_mean_prompt_delta():
    records = [
        {"include_context": True, "prompt_tokens": 800, "usage_source": "provider"},
        {"include_context": True, "prompt_tokens": 1000, "usage_source": "provider"},
        {"include_context": False, "prompt_tokens": 100, "usage_source": "provider"},
        {"include_context": False, "prompt_tokens": 300, "usage_source": "provider"},
    ]
    line = telemetry_cost_line(records)
    assert "+700" in line  # mean on (900) - mean off (200)


def test_telemetry_cost_line_flags_estimates():
    records = [
        {"include_context": True, "prompt_tokens": 800, "usage_source": "estimate"},
        {"include_context": False, "prompt_tokens": 100, "usage_source": "provider"},
    ]
    line = telemetry_cost_line(records)
    assert "WARNING" in line and "estimate" in line
```

Run: `cd ~/dev/gnomon-eval && python -m pytest tests/unit/test_compare.py -v`
Expected: ERROR `ModuleNotFoundError`.

- [ ] **Step 2: Implement**

Create `src/gnomon/reporting/compare.py`:

```python
"""Compare two eval reports (recall on vs off) and state the honest claim.

Quality deltas come from the two --json reports. The input-token cost of
recall ("+E input tokens/turn") comes from AXON's recall telemetry JSONL,
because gnomon reports only carry total_tokens (no prompt/completion split).

Single-turn A/B measures QUALITY lift and recall COST - never token savings
(that is a multi-turn phenomenon; see docs/adr/0009).

Usage:
    python -m gnomon.reporting.compare on.json off.json \
        [--telemetry ~/.../recall/requests.jsonl]
"""
import argparse
import json
from pathlib import Path


def _fmt_metric(m: dict) -> str:
    return (
        f"mean={m['mean']:.3f} [{m['ci_low']:.3f}, {m['ci_high']:.3f}] "
        f"({int(m['confidence_level'] * 100)}% CI, N={m['n']})"
    )


def compare(on: dict, off: dict) -> str:
    lines = ["A/B comparison: recall ON vs OFF", "=" * 34, "", "Quality:"]
    off_metrics = {m["metric"]: m for m in off["metrics"]}
    for m in on["metrics"]:
        base = off_metrics.get(m["metric"])
        if base is None:
            lines.append(
                f"  {m['metric']}: on {_fmt_metric(m)} (no off-run baseline)"
            )
        else:
            delta = m["mean"] - base["mean"]
            lines.append(
                f"  {m['metric']}: {delta:+.3f} "
                f"(on {_fmt_metric(m)} vs off {_fmt_metric(base)})"
            )

    on_by_case = {c["case_id"]: c["total_tokens"] for c in on["per_case"]}
    off_by_case = {c["case_id"]: c["total_tokens"] for c in off["per_case"]}
    shared = sorted(on_by_case.keys() & off_by_case.keys())
    deltas = [on_by_case[c] - off_by_case[c] for c in shared]
    mean_delta = sum(deltas) / len(deltas) if deltas else 0.0
    lines += [
        "",
        "Cost (total tokens, from gnomon reports):",
        f"  on={on['cost']['total_tokens']} off={off['cost']['total_tokens']} "
        f"mean per-case delta={mean_delta:+.0f}",
    ]
    missing = (on_by_case.keys() | off_by_case.keys()) - set(shared)
    if missing:
        lines.append(f"  WARNING: cases missing from one run: {sorted(missing)}")
    return "\n".join(lines)


def telemetry_cost_line(records: list[dict]) -> str:
    """Mean prompt-token delta (recall on - off) from AXON telemetry records."""
    estimates = [r for r in records if r.get("usage_source") != "provider"]
    on = [r["prompt_tokens"] for r in records if r["include_context"]]
    off = [r["prompt_tokens"] for r in records if not r["include_context"]]
    if not on or not off:
        return "Recall input cost: insufficient telemetry (need both arms)."
    delta = sum(on) / len(on) - sum(off) / len(off)
    line = (
        f"Recall input cost: {delta:+.0f} prompt tokens/turn "
        f"(mean over {len(on)} on / {len(off)} off requests)"
    )
    if estimates:
        line += (
            f"\nWARNING: {len(estimates)} record(s) have usage_source=estimate; "
            "the run is not provider-grade evidence."
        )
    return line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gnomon-compare")
    parser.add_argument("on_report")
    parser.add_argument("off_report")
    parser.add_argument("--telemetry", help="AXON recall requests.jsonl")
    args = parser.parse_args(argv)

    on = json.loads(Path(args.on_report).read_text(encoding="utf-8"))
    off = json.loads(Path(args.off_report).read_text(encoding="utf-8"))
    print(compare(on, off))
    if args.telemetry:
        lines = Path(args.telemetry).read_text(encoding="utf-8").splitlines()
        records = [json.loads(ln) for ln in lines if ln.strip()]
        print()
        print(telemetry_cost_line(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run GREEN**

Run: `cd ~/dev/gnomon-eval && python -m pytest tests/unit/test_compare.py -v`
Expected: 5 PASS.

- [ ] **Step 4: Commit**

```bash
cd ~/dev/gnomon-eval
git add src/gnomon/reporting/compare.py tests/unit/test_compare.py
git commit -m "feat: A/B compare module - quality deltas plus recall input cost"
```

---

### Task 8: GNOMON — dataset scaffold (OWNER-BLOCKING for Task 10)

**Files:**
- Create: `~/dev/gnomon-eval/datasets/second_brain/README.md`

**Interfaces:**
- Consumes: `EvalCase` shape (`domain/models.py:14-22`) and the loader's validation.
- Produces: `datasets/second_brain/cases.json` — WRITTEN BY THE OWNER, 15-20 real vault cases. The agent only ships the README. Task 10 cannot run until this file exists.

- [ ] **Step 1: Create the README**

`datasets/second_brain/README.md`:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
cd ~/dev/gnomon-eval
git add datasets/second_brain/README.md
git commit -m "docs: scaffold real second-brain dataset with case-writing rules"
```

- [ ] **Step 3: Hand off to owner**

Notify the owner: Task 10 is blocked until `datasets/second_brain/cases.json` exists with 15+ cases and passes the loader check above.

---

### Task 9: GNOMON — ADR 0009: token savings requires multi-turn measurement

**Files:**
- Create: `~/dev/gnomon-eval/docs/adr/0009-token-savings-requires-multiturn.md`

**Interfaces:**
- Consumes: numbering convention of `docs/adr/0001-...` through `0008-...`.
- Produces: the documented decision that prevents re-making the wrong-metric mistake.

- [ ] **Step 1: Write the ADR** (follow the style of `docs/adr/0008-case-level-bootstrap-ci.md`; explicit Relations block per GLYPH conventions):

```markdown
# ADR 0009: Token savings is validated by real multi-turn measurement

## Status
Accepted (2026-07-02)

## Context
AXON recall PREPENDS retrieved context to the query
(axon http/app.py: augmented_query). In a single-turn eval, recall
therefore INCREASES input tokens per request. GNOMON is single-turn:
it measures quality lift (faithfulness, context_precision) and the
input-token COST of recall. A previously published 52.3% savings figure
came from a deterministic model, not measurement.

## Decision
ADR 0009 requires that any "AXON saves tokens" claim be backed by a real
multi-turn measurement: an N-turn session runner comparing WITH AXON
(fixed recall budget per turn) against WITHOUT AXON (re-sending the full
growing context each turn), counting real provider tokens per turn.

ADR 0009 requires that single-turn A/B results (gnomon
config/axon-recall-on.toml vs axon-recall-off.toml) be framed as quality
lift plus recall cost, never as savings.

## Rationale
- Single-turn: recall adds prompt tokens; "savings" is structurally
  impossible to observe.
- Multi-turn: the baseline's context grows linearly with turns while the
  recall arm's stays bounded; only there can savings exist and be measured.
- A deterministic model is a projection, not evidence; it cannot survive
  a skeptical reviewer.

## Relations
- Relates to: ADR 0004 (cost and latency are first-class in EvalReport).
- Relates to: ADR 0005 (openai_compat contexts contract used by the A/B).
- Requires: AXON recall telemetry (axon observability/recall_telemetry.py)
  as the source of the prompt/completion split.
```

- [ ] **Step 2: Commit**

```bash
cd ~/dev/gnomon-eval
git add docs/adr/0009-token-savings-requires-multiturn.md
git commit -m "docs: ADR 0009 - savings claims require multi-turn measurement"
```

---

### Task 10: A/B runbook + stability verification (owner executes, needs live stack)

**Files:**
- Create: `~/dev/gnomon-eval/docs/RUNBOOK-ab-recall.md`

**Interfaces:**
- Consumes: everything above + owner's `cases.json` (Task 8) + live Ollama/providers.
- Produces: `on.json`, `off.json`, the compare output — the ONE validated number that propagates to LP/LinkedIn/README (Plan B consumes it).

- [ ] **Step 1: Write the runbook**

`docs/RUNBOOK-ab-recall.md`:

```markdown
# Runbook: AXON recall A/B (the honest number)

Prereqs: datasets/second_brain/cases.json (15+ cases, see datasets/
second_brain/README.md), AXON stack up (postgres/pgvector), Ollama up
(judge model llama3 pulled), and a completion model reachable by AXON.

1. Start the endpoint (axon repo):
       axon serve-http --port 8765
2. Optional but recommended - archive old telemetry so this run's
   records are isolated:
       mv "$(python -c 'from axon.observability.recall_telemetry import \
       RecallTelemetryStore; print(RecallTelemetryStore().stats_file)')" \
       /tmp/recall-backup.jsonl 2>/dev/null || true
3. Run both arms (gnomon-eval repo):
       gnomon -c config/axon-recall-on.toml  --json > on.json
       gnomon -c config/axon-recall-off.toml --json > off.json
4. Compare (telemetry path printed by the python one-liner above):
       python -m gnomon.reporting.compare on.json off.json \
           --telemetry <recall/requests.jsonl>
5. Validity checks - the number is only publishable if ALL hold:
   - compare output has NO "usage_source=estimate" warning;
   - no answer in on.json/off.json contains "[LLM unavailable";
   - stability: repeat step 3-4 into on2.json/off2.json; metric means
     must agree within their CIs across the two runs.
6. Record the final claim exactly as:
   "AXON recall lifts faithfulness A->B (95% CI, N cases) at a cost of
   +E input tokens/turn. Reproduce: gnomon -c config/axon-recall-on.toml."
   Never phrase Wave 1 as token savings (ADR 0009).
```

- [ ] **Step 2: Commit and hand off**

```bash
cd ~/dev/gnomon-eval
git add docs/RUNBOOK-ab-recall.md
git commit -m "docs: A/B recall runbook with validity and stability checks"
```

Owner executes the runbook; agents stop here (live stack + judgment required).

---

## Execution order and dependencies

```
axon:   Task 1 -> 2 -> 3 -> 4          (branch feat/honest-usage-wave1)
gnomon: Task 5 -> 6 -> 7 ; 8, 9 anytime (branch feat/ab-recall-compare)
Task 10 (owner): needs 1-9 merged + cases.json + live stack
```

Tasks 5-9 have no dependency on axon tasks (the flag is just a passthrough field); the two branches can proceed in parallel.

## Out of scope (deliberate)

- Wave 2 multi-turn savings harness (`benchmarks/model.py` replacement) — separate plan after Wave 1 ships.
- Propagation edits to LP/LinkedIn/README — Plan B consumes the number.
- Any change to gnomon's `RagResponse`/`CaseCost` domain (prompt/completion split lives in AXON telemetry instead — smaller diff, frozen contract untouched).
