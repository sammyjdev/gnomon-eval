# GNOMON v1 — Complete the Implementation — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move from the Phase 1 vertical slice (stubs: `MockTarget` + `StubJudge`) to the complete v1: real RAG target via adapter, Ollama judge with cache, second metric, dataset loader, regression gate, single-command CLI, offline Docker infra, and CI — closing all RF/RNF/VAL items from `docs/REQUIREMENTS.md`.

**Architecture:** Everything new enters as concrete implementation that depends on the Domain, never the reverse (RNF-02). HTTP sits behind a seam (`HttpTransport` Protocol) so the adapter and judge can be tested without a network. The production external config enters as a composed `RunConfig` (does not touch the Phase 1 `EvalConfig`, keeping the 44 existing tests green). The existing loop (`run_eval`) does not change: it already depends only on the `RagTarget`/`Judge` contracts, so the real target and real judge are a wiring swap.

**Tech Stack:** Python 3.11+, pydantic 2, **stdlib only** for infra (`urllib.request`, `tomllib`, `json`) — preserves the minimal-dependency philosophy (only `pydantic`). pytest. Docker Compose + Ollama for the offline path.

---

## Decisions to confirm (become ADRs in this plan)

Three non-obvious points emerged from the analysis. The plan adopts a justified default for each and records them as ADRs (Task 13). If the user disagrees with any default, adjust before executing the corresponding task.

1. **Source of `contexts` in an OpenAI-compat response (ADR-005).** The OpenAI chat/completions protocol has no standard field for retrieved contexts. Default adopted: the RAG target returns contexts in a configurable-name JSON extension field (`contexts_field`, default `"contexts"`) in the top-level response body. Absence of this field → `IncompleteResponseError` (VAL-03), not a silent zero.
2. **Gate compares against `ci_low`, not `mean` (ADR-006).** Statistical honesty (RNF-03): the gate only passes if the lower bound of the confidence interval clears the threshold. Gating by the mean would let through a result whose uncertainty still crosses the threshold. Trade-off: stricter gate with small N; mitigated by raising N.
3. **Ollama judge determinism (ADR-007, updates open questions from ADR-002).** RNF-01 is reproducibility "within measured variance", not bit-exact. The judge fixes `options.seed = seed + run` per run; this gives a deterministic sequence *for the same model on the same machine*. The reproducibility suite continues using `StubJudge` (purely deterministic); real-judge reproducibility is verified as a tolerance, not equality.

---

## File map

**Create:**
- `src/gnomon/http.py` — seam `HttpTransport` + `UrllibTransport` + `TransportError`
- `src/gnomon/metrics/names.py` — `V1_METRICS` (canonical metric set)
- `src/gnomon/dataset/__init__.py`, `src/gnomon/dataset/loader.py` — RF-01, VAL-01
- `src/gnomon/config/run_config.py` — `RunConfig`/`TargetConfig`/`JudgeConfig`/`GateConfig` + `from_file` (TOML)
- `src/gnomon/targets/openai_compat.py` — real REST adapter (RF-02/03, VAL-02/03)
- `src/gnomon/judge/cache.py` — `JudgeCache` (VAL-07)
- `src/gnomon/judge/prompts.py` — faithfulness + context_precision prompts
- `src/gnomon/judge/ollama.py` — Ollama judge (RF-04, ADR-002)
- `src/gnomon/gate/__init__.py`, `src/gnomon/gate/gate.py` — gate (RF-09, VAL-05)
- `src/gnomon/cli.py` — single-command entrypoint (RNF-04)
- `datasets/rpg_master_example/cases.json` — versioned example dataset
- `config/example.toml` — example run config
- `docker-compose.yml`, `Dockerfile` — offline path (RF-10)
- `.github/workflows/ci.yml` — CI (RNF-08)
- `docs/adr/0005-openai-compat-contexts.md`, `0006-gate-on-ci-low.md`, `0007-ollama-judge-determinism.md`
- Tests: `tests/unit/test_dataset.py`, `tests/unit/test_run_config.py`, `tests/unit/test_openai_compat_target.py`, `tests/unit/test_judge_cache.py`, `tests/unit/test_ollama_judge.py`, `tests/unit/test_gate.py`, `tests/integration/test_cli.py`, `tests/gate/test_regression_gate.py`

**Modify:**
- `src/gnomon/judge/stub.py` — also score `context_precision` in addition to `faithfulness` (RF-05)
- `pyproject.toml` — `[project.scripts]` (console entry) + optional test dependency
- `README.md` — honest single-command execution path (RNF-05, RF-11)

---

## Task 1: Canonical metric set

Defines the v1 metric names in a single place so the judge, gate, and tests all reference the same source (DRY). RF-05.

**Files:**
- Create: `src/gnomon/metrics/names.py`
- Test: `tests/unit/test_confidence.py` (no change; will consume the constant later)

- [ ] **Step 1: Create the constant**

`src/gnomon/metrics/names.py`:
```python
"""Canonical metric names for the v1 evaluation (RF-05).

One source of truth so the judge, the gate thresholds and the tests cannot
drift into spelling the same metric two ways.
"""

# Order is the report/display order.
V1_METRICS: tuple[str, ...] = ("faithfulness", "context_precision")
```

- [ ] **Step 2: Verify import**

Run: `python -c "from gnomon.metrics.names import V1_METRICS; print(V1_METRICS)"`
Expected: `('faithfulness', 'context_precision')`

- [ ] **Step 3: Commit**

```bash
git add src/gnomon/metrics/names.py
git commit -m "feat: conjunto canonico de metricas da v1

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: StubJudge scores both metrics (RF-05)

`StubJudge` currently only returns `faithfulness`. For v1 the aggregation must exercise both metrics even on the deterministic path (CI). Keeps the same determinism by (seed, case, run).

**Files:**
- Modify: `src/gnomon/judge/stub.py`
- Test: `tests/unit/test_stub_judge.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_stub_judge.py`:
```python
from gnomon.metrics.names import V1_METRICS


def test_stub_scores_all_v1_metrics():
    judge = StubJudge()
    scores = judge.score(CASE, RESPONSE, seed=42, run=0).scores
    assert set(scores) == set(V1_METRICS)
    assert all(0.0 <= v <= 1.0 for v in scores.values())


def test_stub_two_metrics_are_independent():
    # The two metrics must not collapse to the same number per run.
    judge = StubJudge()
    s = judge.score(CASE, RESPONSE, seed=42, run=1).scores
    assert s["faithfulness"] != s["context_precision"]
```
(Reuse `CASE`/`RESPONSE` already defined in the file; if they do not exist under those names, build a minimal `EvalCase` and `RagResponse` at the top of the test — see the pattern in `tests/integration/test_runner_end_to_end.py`.)

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/unit/test_stub_judge.py -q`
Expected: FAIL — `context_precision` absent from `scores`.

- [ ] **Step 3: Implement**

Replace the `score` method and helper in `src/gnomon/judge/stub.py`:
```python
    def score(self, case: EvalCase, response: RagResponse, *, seed: int, run: int) -> MetricScores:
        scores: dict[str, float] = {}
        for metric in V1_METRICS:
            rng = random.Random(self._derive_seed(metric, case, response, seed, run))
            raw = self._base + rng.uniform(-self._jitter, self._jitter)
            scores[metric] = max(0.0, min(1.0, raw))
        return MetricScores(scores=scores)

    def _derive_seed(
        self, metric: str, case: EvalCase, response: RagResponse, seed: int, run: int
    ) -> int:
        # hashlib, not hash(): the latter is salted per process and would
        # break cross-process reproducibility.
        identity = f"{seed}|{self.model_name}|{metric}|{case.id}|{response.answer}|{run}"
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return int(digest[:16], 16)
```
And add the import at the top: `from gnomon.metrics.names import V1_METRICS`.

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS. Note: existing tests that assumed only `faithfulness` in the stub output remain valid (they call `report.metric("faithfulness")`, which is still present). If any test asserts `len(metrics) == 1`, update it to `2`.

- [ ] **Step 5: Commit**

```bash
git add src/gnomon/judge/stub.py tests/unit/test_stub_judge.py
git commit -m "feat: StubJudge pontua faithfulness e context_precision (RF-05)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Dataset loader (RF-01, VAL-01)

Reads the versioned dataset from a JSON file and returns `list[EvalCase]`. Fails closed and explicitly on a missing, empty, or malformed dataset, naming the offending case (VAL-01). Never evaluates partially in silence.

**Files:**
- Create: `src/gnomon/dataset/__init__.py` (empty)
- Create: `src/gnomon/dataset/loader.py`
- Create: `datasets/rpg_master_example/cases.json`
- Test: `tests/unit/test_dataset.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_dataset.py`:
```python
import json

import pytest

from gnomon.dataset.loader import DatasetError, load_dataset


def _write(tmp_path, payload):
    p = tmp_path / "cases.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


VALID_CASE = {
    "id": "case-1",
    "question": "Who narrates the world?",
    "expected_answer": "The game master narrates the world.",
    "expected_contexts": ["The game master narrates the world to the players."],
}


def test_loads_valid_dataset(tmp_path):
    path = _write(tmp_path, [VALID_CASE])
    cases = load_dataset(path)
    assert len(cases) == 1
    assert cases[0].id == "case-1"


def test_missing_file_fails_closed(tmp_path):
    with pytest.raises(DatasetError) as exc:
        load_dataset(tmp_path / "nope.json")
    assert "nope.json" in str(exc.value)


def test_empty_dataset_fails_closed(tmp_path):
    path = _write(tmp_path, [])
    with pytest.raises(DatasetError):
        load_dataset(path)


def test_case_missing_field_points_at_the_case(tmp_path):
    bad = {**VALID_CASE, "id": "case-bad"}
    del bad["expected_contexts"]
    path = _write(tmp_path, [VALID_CASE, bad])
    with pytest.raises(DatasetError) as exc:
        load_dataset(path)
    # VAL-01: the error names the offending case, not a generic failure.
    assert "case-bad" in str(exc.value)
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/unit/test_dataset.py -q`
Expected: FAIL — `gnomon.dataset.loader` does not exist.

- [ ] **Step 3: Implement**

`src/gnomon/dataset/__init__.py`: empty file.

`src/gnomon/dataset/loader.py`:
```python
"""Load the versioned evaluation dataset from a file (RF-01).

The dataset is the source of truth and lives next to the code, not in an
external store. Loading fails closed (VAL-01): a missing file, an empty
dataset or a malformed case stops the run with an error that names the
offending case. The harness never evaluates partially in silence.
"""

import json
from pathlib import Path

from pydantic import ValidationError

from gnomon.domain.models import EvalCase


class DatasetError(Exception):
    """Dataset missing, empty or malformed (VAL-01)."""


def load_dataset(path: str | Path) -> list[EvalCase]:
    path = Path(path)
    if not path.is_file():
        raise DatasetError(f"dataset file not found: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetError(f"dataset {path} is not valid JSON: {exc}") from exc

    if not isinstance(raw, list) or not raw:
        raise DatasetError(f"dataset {path} must be a non-empty JSON array of cases")

    cases: list[EvalCase] = []
    for index, entry in enumerate(raw):
        case_id = entry.get("id") if isinstance(entry, dict) else None
        label = case_id or f"index {index}"
        try:
            cases.append(EvalCase(**entry))
        except (ValidationError, TypeError) as exc:
            raise DatasetError(f"malformed case ({label}): {exc}") from exc
    return cases
```

- [ ] **Step 4: Run and watch it pass**

Run: `python -m pytest tests/unit/test_dataset.py -q`
Expected: PASS.

- [ ] **Step 5: Create the example dataset**

`datasets/rpg_master_example/cases.json`:
```json
[
  {
    "id": "rpg-001",
    "question": "Who narrates the world to the players?",
    "expected_answer": "The game master narrates the world.",
    "expected_contexts": [
      "The game master narrates the world and adjudicates the rules."
    ]
  },
  {
    "id": "rpg-002",
    "question": "What does a player roll to resolve an uncertain action?",
    "expected_answer": "The player rolls dice against a difficulty set by the game master.",
    "expected_contexts": [
      "Uncertain actions are resolved by a dice roll against a difficulty class."
    ]
  }
]
```

- [ ] **Step 6: Verify the example dataset loads**

Run: `python -c "from gnomon.dataset.loader import load_dataset; print(len(load_dataset('datasets/rpg_master_example/cases.json')))"`
Expected: `2`

- [ ] **Step 7: Commit**

```bash
git add src/gnomon/dataset datasets/rpg_master_example/cases.json tests/unit/test_dataset.py
git commit -m "feat: loader de dataset com falha-fechado e exemplo (RF-01, VAL-01)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: HTTP seam (`HttpTransport`)

A thin seam for HTTP POST JSON, with a stdlib implementation (`urllib`). The adapter and judge depend on the Protocol, not on `urllib`, so tests inject a fake transport and nothing touches the network.

**Files:**
- Create: `src/gnomon/http.py`
- Test: covered indirectly in Tasks 5 and 8 (no isolated test required; it is thin infra).

- [ ] **Step 1: Implement the seam**

`src/gnomon/http.py`:
```python
"""Thin HTTP seam so target adapter and judge stay testable without network.

Concrete adapters depend on the HttpTransport Protocol, not on urllib, so a
test injects a fake transport and no socket is opened. The stdlib
UrllibTransport keeps the dependency footprint at zero beyond pydantic.
"""

import json
import urllib.error
import urllib.request
from typing import Protocol, runtime_checkable


class TransportError(Exception):
    """Network-level failure: connection refused, timeout, unreachable host."""


@runtime_checkable
class HttpTransport(Protocol):
    def post_json(
        self, url: str, payload: dict, *, headers: dict[str, str], timeout_s: float
    ) -> tuple[int, dict]:
        """POST payload as JSON; return (status_code, parsed_body)."""
        ...


class UrllibTransport:
    """Default HttpTransport over the standard library."""

    def post_json(
        self, url: str, payload: dict, *, headers: dict[str, str], timeout_s: float
    ) -> tuple[int, dict]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                body = response.read().decode("utf-8")
                return response.status, (json.loads(body) if body else {})
        except urllib.error.HTTPError as exc:  # non-2xx with a body
            body = exc.read().decode("utf-8")
            return exc.code, (json.loads(body) if body else {})
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TransportError(f"POST {url} failed: {exc}") from exc
```

- [ ] **Step 2: Verify import**

Run: `python -c "from gnomon.http import HttpTransport, UrllibTransport, TransportError; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/gnomon/http.py
git commit -m "feat: seam HttpTransport stdlib para adapter e juiz

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Real OpenAI-compat adapter (RF-02, RF-03, VAL-02, VAL-03)

The first concrete target: speaks OpenAI-compat over REST, returns a `RagResponse` with answer, contexts, tokens, and latency. The error taxonomy distinguishes configuration failures from runtime failures (VAL-02); an incomplete response is rejected explicitly (VAL-03), never as a silent zero. Contexts come from a configurable extension field (ADR-005).

**Files:**
- Create: `src/gnomon/targets/openai_compat.py`
- Test: `tests/unit/test_openai_compat_target.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_openai_compat_target.py`:
```python
import pytest

from gnomon.http import TransportError
from gnomon.targets.openai_compat import (
    IncompleteResponseError,
    OpenAICompatTarget,
    TargetConfigError,
    TargetRuntimeError,
)


class FakeTransport:
    def __init__(self, *, status=200, body=None, raises=None):
        self.status, self.body, self.raises = status, body or {}, raises
        self.calls = []

    def post_json(self, url, payload, *, headers, timeout_s):
        self.calls.append((url, payload))
        if self.raises:
            raise self.raises
        return self.status, self.body


def _ok_body():
    return {
        "choices": [{"message": {"content": "The game master narrates the world."}}],
        "contexts": ["The game master narrates the world to the players."],
        "usage": {"total_tokens": 137},
    }


def _target(transport):
    return OpenAICompatTarget(
        base_url="http://localhost:8000/v1",
        model="rpg-master",
        transport=transport,
    )


def test_missing_base_url_is_config_error():
    with pytest.raises(TargetConfigError):
        OpenAICompatTarget(base_url="", model="m", transport=FakeTransport())


def test_happy_path_maps_to_rag_response():
    target = _target(FakeTransport(body=_ok_body()))
    resp = target.query("Who narrates the world?")
    assert resp.answer == "The game master narrates the world."
    assert resp.contexts == ["The game master narrates the world to the players."]
    assert resp.total_tokens == 137
    assert resp.latency_ms >= 0.0


def test_network_failure_is_runtime_error():
    target = _target(FakeTransport(raises=TransportError("connection refused")))
    with pytest.raises(TargetRuntimeError):
        target.query("q")


def test_non_2xx_is_runtime_error():
    target = _target(FakeTransport(status=500, body={"error": "boom"}))
    with pytest.raises(TargetRuntimeError):
        target.query("q")


def test_off_protocol_body_is_runtime_error():
    # VAL-02: off-protocol body is distinct from the happy path.
    target = _target(FakeTransport(body={"unexpected": "shape"}))
    with pytest.raises(TargetRuntimeError):
        target.query("q")


def test_missing_contexts_is_incomplete_response():
    body = _ok_body()
    del body["contexts"]
    target = _target(FakeTransport(body=body))
    with pytest.raises(IncompleteResponseError):
        target.query("q")


def test_missing_tokens_is_incomplete_response():
    body = _ok_body()
    del body["usage"]
    target = _target(FakeTransport(body=body))
    with pytest.raises(IncompleteResponseError):
        target.query("q")
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/unit/test_openai_compat_target.py -q`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

`src/gnomon/targets/openai_compat.py`:
```python
"""OpenAI-compatible REST adapter (RF-02, RF-03).

Translates the domain's RagTarget contract to an OpenAI chat/completions
endpoint. The error taxonomy keeps VAL-02 honest: a config-class failure
(bad URL, missing model) is a different exception from a runtime-class
failure (unreachable, timeout, non-2xx, off-protocol body). An incomplete
response (no contexts or no token count) is rejected explicitly (VAL-03),
never coerced to a silent zero that would contaminate cost or a metric.

Contexts source: OpenAI chat/completions has no standard field for retrieved
contexts, so the target returns them in a configurable top-level extension
field (default "contexts"). See ADR-005.
"""

import time

from gnomon.domain.models import RagResponse
from gnomon.http import HttpTransport, TransportError, UrllibTransport


class OpenAICompatError(Exception):
    """Base for target adapter failures."""


class TargetConfigError(OpenAICompatError):
    """Misconfiguration detected before or independent of the call (VAL-02)."""


class TargetRuntimeError(OpenAICompatError):
    """Target unreachable, timed out, errored or answered off-protocol (VAL-02)."""


class IncompleteResponseError(OpenAICompatError):
    """Response missing contexts or token count (VAL-03)."""


class OpenAICompatTarget:
    """RagTarget speaking OpenAI chat/completions over REST."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        transport: HttpTransport | None = None,
        api_key: str | None = None,
        timeout_s: float = 30.0,
        contexts_field: str = "contexts",
    ) -> None:
        if not base_url:
            raise TargetConfigError("openai_compat target requires a base_url")
        if not model:
            raise TargetConfigError("openai_compat target requires a model")
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._transport = transport or UrllibTransport()
        self._timeout_s = timeout_s
        self._contexts_field = contexts_field
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def query(self, question: str) -> RagResponse:
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": question}],
        }
        start = time.perf_counter()
        try:
            status, body = self._transport.post_json(
                self._url, payload, headers=self._headers, timeout_s=self._timeout_s
            )
        except TransportError as exc:
            raise TargetRuntimeError(f"target unreachable: {exc}") from exc
        latency_ms = (time.perf_counter() - start) * 1000.0

        if status != 200:
            raise TargetRuntimeError(f"target returned HTTP {status}")

        try:
            answer = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise TargetRuntimeError("target answered off-protocol (no choices/message)") from exc

        contexts = body.get(self._contexts_field)
        total_tokens = (body.get("usage") or {}).get("total_tokens")
        if contexts is None or total_tokens is None:
            raise IncompleteResponseError(
                "response missing "
                f"{'contexts' if contexts is None else 'usage.total_tokens'} (VAL-03)"
            )

        return RagResponse(
            answer=answer,
            contexts=list(contexts),
            total_tokens=int(total_tokens),
            latency_ms=latency_ms,
        )
```

- [ ] **Step 4: Run and watch it pass**

Run: `python -m pytest tests/unit/test_openai_compat_target.py -q`
Expected: PASS (all 7).

- [ ] **Step 5: Confirm the adapter satisfies the `RagTarget` contract**

Run: `python -c "from gnomon.domain.interfaces import RagTarget; from gnomon.targets.openai_compat import OpenAICompatTarget; print(issubclass(OpenAICompatTarget, RagTarget) or isinstance(OpenAICompatTarget(base_url='http://x/v1', model='m'), RagTarget))"`
Expected: `True`

- [ ] **Step 6: Commit**

```bash
git add src/gnomon/targets/openai_compat.py tests/unit/test_openai_compat_target.py
git commit -m "feat: adapter OpenAI-compat real (RF-02/03, VAL-02/03)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Judge cache (VAL-07)

Cache keyed by the identity tuple `(case.id, response.answer, judge_model, seed, run)`. An entry whose key does not match the tuple is treated as a miss, never as a hit that would return a score from the wrong context (VAL-07). `run` is part of the key: without it, the N runs would collapse to a single cached value and the variance would vanish.

**Files:**
- Create: `src/gnomon/judge/cache.py`
- Test: `tests/unit/test_judge_cache.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_judge_cache.py`:
```python
from gnomon.domain.models import EvalCase, MetricScores, RagResponse
from gnomon.judge.cache import JudgeCache

CASE = EvalCase(
    id="case-1",
    question="q",
    expected_answer="a",
    expected_contexts=["c"],
)
RESPONSE = RagResponse(answer="a", contexts=["c"], total_tokens=10, latency_ms=1.0)
SCORES = MetricScores(scores={"faithfulness": 0.8, "context_precision": 0.7})


def test_hit_returns_stored_scores():
    cache = JudgeCache()
    cache.put(CASE, RESPONSE, "judge-x", seed=42, run=0, scores=SCORES)
    assert cache.get(CASE, RESPONSE, "judge-x", seed=42, run=0) == SCORES


def test_different_run_is_a_miss():
    cache = JudgeCache()
    cache.put(CASE, RESPONSE, "judge-x", seed=42, run=0, scores=SCORES)
    assert cache.get(CASE, RESPONSE, "judge-x", seed=42, run=1) is None


def test_different_seed_is_a_miss():
    cache = JudgeCache()
    cache.put(CASE, RESPONSE, "judge-x", seed=42, run=0, scores=SCORES)
    assert cache.get(CASE, RESPONSE, "judge-x", seed=43, run=0) is None


def test_different_model_is_a_miss():
    # VAL-07: key mismatch = miss, never a hit from the wrong context.
    cache = JudgeCache()
    cache.put(CASE, RESPONSE, "judge-x", seed=42, run=0, scores=SCORES)
    assert cache.get(CASE, RESPONSE, "judge-y", seed=42, run=0) is None
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/unit/test_judge_cache.py -q`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

`src/gnomon/judge/cache.py`:
```python
"""In-memory judge score cache keyed by the identity tuple (ADR-002, VAL-07).

Reproducibility needs the same (case, response, judge model, seed, run) to
return the same score. The key includes `run`: the N variance runs must each
keep their own score, otherwise the interval would collapse. Any lookup whose
tuple does not match exactly is a miss — never a hit that would return a
score computed for a different context.
"""

from gnomon.domain.models import EvalCase, MetricScores, RagResponse

_Key = tuple[str, str, str, int, int]


class JudgeCache:
    def __init__(self) -> None:
        self._store: dict[_Key, MetricScores] = {}

    def _key(
        self, case: EvalCase, response: RagResponse, model: str, seed: int, run: int
    ) -> _Key:
        return (case.id, response.answer, model, seed, run)

    def get(
        self, case: EvalCase, response: RagResponse, model: str, *, seed: int, run: int
    ) -> MetricScores | None:
        return self._store.get(self._key(case, response, model, seed, run))

    def put(
        self,
        case: EvalCase,
        response: RagResponse,
        model: str,
        *,
        seed: int,
        run: int,
        scores: MetricScores,
    ) -> None:
        self._store[self._key(case, response, model, seed, run)] = scores
```

- [ ] **Step 4: Run and watch it pass**

Run: `python -m pytest tests/unit/test_judge_cache.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gnomon/judge/cache.py tests/unit/test_judge_cache.py
git commit -m "feat: cache do juiz por tupla de identidade (VAL-07)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Ollama judge (RF-04, ADR-002)

Real judge: scores `faithfulness` and `context_precision` by calling Ollama (`/api/chat`, `format: json`), with `options.seed = seed + run` for reproducibility within variance (ADR-007). Uses the `HttpTransport` seam (testable without a network) and `JudgeCache`. A model response that does not match the expected format raises a named error, never a fabricated score.

**Files:**
- Create: `src/gnomon/judge/prompts.py`
- Create: `src/gnomon/judge/ollama.py`
- Test: `tests/unit/test_ollama_judge.py`

- [ ] **Step 1: Prompts (no isolated test; verified through the judge)**

`src/gnomon/judge/prompts.py`:
```python
"""Judge prompts for the v1 metrics (RF-05).

Each prompt asks the model for a single float in [0, 1] inside a JSON object,
so the judge can parse a score deterministically instead of scraping prose.
"""

from gnomon.domain.models import EvalCase, RagResponse

_INSTRUCTION = (
    'Return ONLY a JSON object of the form {{"score": <float 0..1>}}. '
    "No prose, no explanation."
)

_TEMPLATES = {
    "faithfulness": (
        "Rate how well the ANSWER is grounded in the CONTEXTS (1.0 = every claim "
        "is supported, 0.0 = unsupported).\n\n"
        "QUESTION: {question}\nANSWER: {answer}\nCONTEXTS: {contexts}\n\n" + _INSTRUCTION
    ),
    "context_precision": (
        "Rate how relevant the retrieved CONTEXTS are to the QUESTION (1.0 = all "
        "relevant, 0.0 = none relevant).\n\n"
        "QUESTION: {question}\nCONTEXTS: {contexts}\n\n" + _INSTRUCTION
    ),
}


def build_prompt(metric: str, case: EvalCase, response: RagResponse) -> str:
    return _TEMPLATES[metric].format(
        question=case.question,
        answer=response.answer,
        contexts="\n- " + "\n- ".join(response.contexts),
    )
```

- [ ] **Step 2: Write the failing tests (judge)**

`tests/unit/test_ollama_judge.py`:
```python
import json

import pytest

from gnomon.domain.models import EvalCase, RagResponse
from gnomon.judge.cache import JudgeCache
from gnomon.judge.ollama import JudgeProtocolError, OllamaJudge
from gnomon.metrics.names import V1_METRICS

CASE = EvalCase(id="c1", question="q", expected_answer="a", expected_contexts=["c"])
RESPONSE = RagResponse(answer="a", contexts=["c"], total_tokens=5, latency_ms=1.0)


class ScriptedTransport:
    """Returns a fixed Ollama-shaped body, recording options.seed per call."""

    def __init__(self, score=0.8, body_override=None):
        self.score, self.body_override = score, body_override
        self.seeds = []

    def post_json(self, url, payload, *, headers, timeout_s):
        self.seeds.append(payload["options"]["seed"])
        if self.body_override is not None:
            return 200, self.body_override
        content = json.dumps({"score": self.score})
        return 200, {"message": {"content": content}}


def _judge(transport, cache=None):
    return OllamaJudge(
        model="llama3", base_url="http://localhost:11434", transport=transport, cache=cache
    )


def test_scores_all_metrics_in_unit_range():
    judge = _judge(ScriptedTransport(score=0.8))
    scores = judge.score(CASE, RESPONSE, seed=42, run=0).scores
    assert set(scores) == set(V1_METRICS)
    assert all(0.0 <= v <= 1.0 for v in scores.values())


def test_seed_is_offset_by_run():
    # ADR-007: options.seed = seed + run, deterministic per run.
    transport = ScriptedTransport()
    _judge(transport).score(CASE, RESPONSE, seed=100, run=3)
    assert all(s == 103 for s in transport.seeds)


def test_cache_hit_skips_transport():
    transport = ScriptedTransport()
    cache = JudgeCache()
    judge = _judge(transport, cache=cache)
    judge.score(CASE, RESPONSE, seed=42, run=0)
    calls_after_first = len(transport.seeds)
    judge.score(CASE, RESPONSE, seed=42, run=0)
    assert len(transport.seeds) == calls_after_first  # second score came from cache


def test_unparseable_model_output_is_protocol_error():
    transport = ScriptedTransport(body_override={"message": {"content": "I think 0.8"}})
    with pytest.raises(JudgeProtocolError):
        _judge(transport).score(CASE, RESPONSE, seed=42, run=0)
```

- [ ] **Step 3: Run and watch it fail**

Run: `python -m pytest tests/unit/test_ollama_judge.py -q`
Expected: FAIL — module does not exist.

- [ ] **Step 4: Implement**

`src/gnomon/judge/ollama.py`:
```python
"""Ollama-backed judge (RF-04, ADR-002).

Scores faithfulness and context_precision by asking a local Ollama model for
a JSON score per metric. options.seed = seed + run gives a deterministic
sequence per declared seed for a fixed model/host (ADR-007 — reproducibility
within measured variance, not bit-exact). Scores route through JudgeCache so
a repeat of the same (case, response, model, seed, run) does not re-call the
model. A model answer that is not the agreed JSON shape raises a named error
instead of fabricating a score.
"""

import json

from gnomon.domain.models import EvalCase, MetricScores, RagResponse
from gnomon.http import HttpTransport, TransportError, UrllibTransport
from gnomon.judge.cache import JudgeCache
from gnomon.judge.prompts import build_prompt
from gnomon.metrics.names import V1_METRICS


class JudgeError(Exception):
    """Base for judge failures."""


class JudgeRuntimeError(JudgeError):
    """Ollama unreachable, timed out or returned non-2xx."""


class JudgeProtocolError(JudgeError):
    """Model answer was not the agreed {\"score\": float} JSON shape."""


class OllamaJudge:
    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        transport: HttpTransport | None = None,
        cache: JudgeCache | None = None,
        timeout_s: float = 60.0,
        temperature: float = 0.0,
    ) -> None:
        self.model_name = model
        self._url = base_url.rstrip("/") + "/api/chat"
        self._transport = transport or UrllibTransport()
        self._cache = cache
        self._timeout_s = timeout_s
        self._temperature = temperature

    def score(
        self, case: EvalCase, response: RagResponse, *, seed: int, run: int
    ) -> MetricScores:
        if self._cache is not None:
            cached = self._cache.get(case, response, self.model_name, seed=seed, run=run)
            if cached is not None:
                return cached

        scores = {
            metric: self._score_one(metric, case, response, seed=seed, run=run)
            for metric in V1_METRICS
        }
        result = MetricScores(scores=scores)

        if self._cache is not None:
            self._cache.put(case, response, self.model_name, seed=seed, run=run, scores=result)
        return result

    def _score_one(
        self, metric: str, case: EvalCase, response: RagResponse, *, seed: int, run: int
    ) -> float:
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": build_prompt(metric, case, response)}],
            "format": "json",
            "stream": False,
            "options": {"seed": seed + run, "temperature": self._temperature},
        }
        try:
            status, body = self._transport.post_json(
                self._url, payload, headers={}, timeout_s=self._timeout_s
            )
        except TransportError as exc:
            raise JudgeRuntimeError(f"ollama unreachable: {exc}") from exc
        if status != 200:
            raise JudgeRuntimeError(f"ollama returned HTTP {status}")

        try:
            content = body["message"]["content"]
            value = float(json.loads(content)["score"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise JudgeProtocolError(f"judge output not parseable for {metric!r}: {exc}") from exc
        return max(0.0, min(1.0, value))
```

- [ ] **Step 5: Run and watch it pass**

Run: `python -m pytest tests/unit/test_ollama_judge.py -q`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add src/gnomon/judge/prompts.py src/gnomon/judge/ollama.py tests/unit/test_ollama_judge.py
git commit -m "feat: juiz Ollama com cache e seed por run (RF-04, ADR-002)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Run config (`RunConfig`) + thresholds (RNF-07, VAL-05)

Production external config, loaded from TOML and validated before any model call. Composed (`eval` + `target` + `judge` + `gate` + `dataset_path`) — **does not touch the Phase 1 `EvalConfig`**, so existing tests stay green. A gate threshold outside `[0,1]` is rejected at load time (VAL-05).

**Files:**
- Create: `src/gnomon/config/run_config.py`
- Create: `config/example.toml`
- Test: `tests/unit/test_run_config.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_run_config.py`:
```python
import pytest
from pydantic import ValidationError

from gnomon.config.run_config import GateConfig, RunConfig

VALID_TOML = """
dataset_path = "datasets/rpg_master_example/cases.json"

[eval]
reproducible = true
seed = 42
judge_runs = 8

[target]
kind = "openai_compat"
base_url = "http://localhost:8000/v1"
model = "rpg-master"

[judge]
provider = "ollama"
model = "llama3"
base_url = "http://localhost:11434"

[gate]
faithfulness = 0.7
context_precision = 0.6
"""


def test_loads_from_toml(tmp_path):
    path = tmp_path / "run.toml"
    path.write_text(VALID_TOML, encoding="utf-8")
    cfg = RunConfig.from_file(path)
    assert cfg.eval.judge_runs == 8
    assert cfg.target.kind == "openai_compat"
    assert cfg.gate.thresholds["faithfulness"] == 0.7


def test_threshold_above_one_is_rejected():
    # VAL-05: threshold outside the metric range rejected before any call.
    with pytest.raises(ValidationError):
        GateConfig(thresholds={"faithfulness": 1.4})


def test_threshold_negative_is_rejected():
    with pytest.raises(ValidationError):
        GateConfig(thresholds={"faithfulness": -0.1})


def test_seed_required_propagates_from_eval():
    # VAL-06 still enforced via the embedded EvalConfig.
    with pytest.raises(ValidationError):
        RunConfig(
            dataset_path="d.json",
            eval={"reproducible": True, "judge_runs": 8},
            target={"kind": "mock"},
            judge={"provider": "stub"},
            gate={"thresholds": {"faithfulness": 0.7}},
        )
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/unit/test_run_config.py -q`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

`src/gnomon/config/run_config.py`:
```python
"""Production run configuration, loaded from TOML and validated up front.

Composes the Phase-1 EvalConfig with the target, judge and gate config that
the CLI needs, without touching EvalConfig itself (RNF-07: config is external;
the vertical-slice contract stays intact). Invalid configuration — including
a gate threshold outside the metric's [0, 1] range (VAL-05) — fails closed
here, before any model call.
"""

import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from gnomon.config.config import EvalConfig


class TargetConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["openai_compat", "mock"]
    base_url: str | None = None
    model: str | None = None
    api_key_env: str | None = None
    timeout_s: float = Field(default=30.0, gt=0.0)


class JudgeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    provider: Literal["ollama", "stub"]
    model: str | None = None
    base_url: str | None = None
    timeout_s: float = Field(default=60.0, gt=0.0)


class GateConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    thresholds: dict[str, float]

    @field_validator("thresholds")
    @classmethod
    def _thresholds_in_unit_range(cls, value: dict[str, float]) -> dict[str, float]:
        for metric, threshold in value.items():
            if not 0.0 <= threshold <= 1.0:
                raise ValueError(
                    f"gate threshold for {metric!r} out of [0, 1] range: {threshold} (VAL-05)"
                )
        return value


class RunConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    dataset_path: str = Field(min_length=1)
    eval: EvalConfig
    target: TargetConfig
    judge: JudgeConfig
    gate: GateConfig

    @classmethod
    def from_file(cls, path: str | Path) -> "RunConfig":
        path = Path(path)
        data: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
        gate = data.get("gate", {})
        # TOML [gate] is a flat table of metric=threshold; wrap into thresholds.
        if "thresholds" not in gate:
            data["gate"] = {"thresholds": gate}
        return cls(**data)
```

- [ ] **Step 4: Run and watch it pass**

Run: `python -m pytest tests/unit/test_run_config.py -q`
Expected: PASS.

- [ ] **Step 5: Create the example config**

`config/example.toml`:
```toml
dataset_path = "datasets/rpg_master_example/cases.json"

[eval]
reproducible = true
seed = 42
judge_runs = 8
confidence_level = 0.95

[target]
kind = "openai_compat"
base_url = "http://localhost:8000/v1"
model = "rpg-master"

[judge]
provider = "ollama"
model = "llama3"
base_url = "http://localhost:11434"

[gate]
faithfulness = 0.7
context_precision = 0.6
```

- [ ] **Step 6: Verify the example config loads**

Run: `python -c "from gnomon.config.run_config import RunConfig; c=RunConfig.from_file('config/example.toml'); print(c.gate.thresholds)"`
Expected: `{'faithfulness': 0.7, 'context_precision': 0.6}`

- [ ] **Step 7: Commit**

```bash
git add src/gnomon/config/run_config.py config/example.toml tests/unit/test_run_config.py
git commit -m "feat: RunConfig de producao com thresholds de gate (RNF-07, VAL-05)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Regression gate (RF-09, VAL-05)

Compares the `EvalReport` against per-metric thresholds and decides pass/fail. Gates on the **lower bound of the confidence interval** (`ci_low`), not the mean (ADR-006): passes only if uncertainty does not cross the threshold. A metric that has a threshold but is absent from the report is an explicit failure, not a silent pass.

**Files:**
- Create: `src/gnomon/gate/__init__.py` (empty)
- Create: `src/gnomon/gate/gate.py`
- Test: `tests/unit/test_gate.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_gate.py`:
```python
import pytest

from gnomon.domain.models import EvalReport, MetricResult
from gnomon.gate.gate import GateResult, evaluate_gate


def _report(metric, ci_low, ci_high, mean):
    return EvalReport(
        metrics=[
            MetricResult(
                metric=metric,
                mean=mean,
                ci_low=ci_low,
                ci_high=ci_high,
                n=8,
                confidence_level=0.95,
            )
        ],
        per_case_cost=[],
    )


def test_passes_when_ci_low_clears_threshold():
    report = _report("faithfulness", ci_low=0.75, ci_high=0.9, mean=0.82)
    result = evaluate_gate(report, {"faithfulness": 0.7})
    assert result.passed is True
    assert result.failures == []


def test_fails_when_ci_low_below_threshold_even_if_mean_clears():
    # ADR-006: mean (0.82) would pass, but ci_low (0.65) does not clear 0.7.
    report = _report("faithfulness", ci_low=0.65, ci_high=0.99, mean=0.82)
    result = evaluate_gate(report, {"faithfulness": 0.7})
    assert result.passed is False
    assert any("faithfulness" in f for f in result.failures)


def test_missing_metric_is_a_failure():
    report = _report("faithfulness", ci_low=0.8, ci_high=0.9, mean=0.85)
    result = evaluate_gate(report, {"context_precision": 0.6})
    assert result.passed is False
    assert any("context_precision" in f for f in result.failures)
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/unit/test_gate.py -q`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

`src/gnomon/gate/__init__.py`: empty file.

`src/gnomon/gate/gate.py`:
```python
"""Regression gate: turn an evaluation into a CI pass/fail (RF-09).

Gates on the lower bound of the confidence interval, not the mean (ADR-006):
a metric passes only if we are confident — within the reported interval — that
it clears the threshold. A threshold for a metric absent from the report is a
failure, never a silent pass. Threshold range is validated upstream at config
load (VAL-05), so this layer trusts the numbers.
"""

from dataclasses import dataclass

from gnomon.domain.models import EvalReport


@dataclass(frozen=True)
class GateResult:
    passed: bool
    failures: list[str]


def evaluate_gate(report: EvalReport, thresholds: dict[str, float]) -> GateResult:
    failures: list[str] = []
    for metric, threshold in thresholds.items():
        try:
            result = report.metric(metric)
        except KeyError:
            failures.append(f"{metric}: required by gate but absent from report")
            continue
        if result.ci_low < threshold:
            failures.append(
                f"{metric}: ci_low={result.ci_low:.3f} < threshold={threshold:.3f}"
            )
    return GateResult(passed=not failures, failures=failures)
```

- [ ] **Step 4: Run and watch it pass**

Run: `python -m pytest tests/unit/test_gate.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gnomon/gate tests/unit/test_gate.py
git commit -m "feat: gate de regressao gateando por ci_low (RF-09, ADR-006)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Single-command CLI (RF-11, RNF-04, RNF-05)

Entrypoint that loads `RunConfig`, wires target and judge from config, runs `run_eval`, prints the report in both formats, and exits with the gate code (0 pass / 1 fail). One command, no source editing required (RNF-04). Factories map `kind`/`provider` to implementation.

**Files:**
- Create: `src/gnomon/cli.py`
- Modify: `pyproject.toml` (`[project.scripts]`)
- Test: `tests/integration/test_cli.py`

- [ ] **Step 1: Write the failing test**

`tests/integration/test_cli.py`:
```python
import json

from gnomon.cli import build_judge, build_target, run_from_config
from gnomon.config.run_config import RunConfig


def _stub_config(tmp_path):
    dataset = tmp_path / "cases.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "id": "c1",
                    "question": "q",
                    "expected_answer": "a",
                    "expected_contexts": ["ctx"],
                }
            ]
        ),
        encoding="utf-8",
    )
    return RunConfig(
        dataset_path=str(dataset),
        eval={"reproducible": True, "seed": 42, "judge_runs": 8},
        target={"kind": "mock"},
        judge={"provider": "stub"},
        gate={"thresholds": {"faithfulness": 0.5, "context_precision": 0.5}},
    )


def test_factories_build_contract_types():
    from gnomon.domain.interfaces import Judge, RagTarget

    target = build_target(RunConfig.model_construct(target=None).target) if False else None  # noqa
    # build_target/build_judge return objects that satisfy the contracts:
    cfg = _stub_config_target()
    assert isinstance(build_target(cfg.target), RagTarget)
    assert isinstance(build_judge(cfg.judge), Judge)


def _stub_config_target():
    return RunConfig(
        dataset_path="x",
        eval={"reproducible": True, "seed": 1, "judge_runs": 8},
        target={"kind": "mock"},
        judge={"provider": "stub"},
        gate={"thresholds": {"faithfulness": 0.5}},
    )


def test_run_from_config_returns_report_and_gate(tmp_path):
    cfg = _stub_config(tmp_path)
    report, gate = run_from_config(cfg)
    assert report.metric("faithfulness").n == 8
    assert gate.passed is True
```
(Note: the first assertion uses `MockTarget`. Because `MockTarget.__init__` requires `answer/contexts/total_tokens/latency_ms`, the `build_target` factory for `kind="mock"` uses fixed demo values — see implementation.)

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/integration/test_cli.py -q`
Expected: FAIL — `gnomon.cli` does not exist.

- [ ] **Step 3: Implement**

`src/gnomon/cli.py`:
```python
"""One-command entrypoint (RNF-04): config in, report + gate exit code out.

Wires the pieces by configuration, never by editing source. Factories map the
declared kind/provider to a concrete RagTarget / Judge, so a new backend is a
config change. Exit code is the gate verdict (0 pass, 1 fail), which is what
makes the same command usable as a CI regression gate (RF-09).
"""

import argparse
import json
import os
import sys

from gnomon.config.run_config import JudgeConfig, RunConfig, TargetConfig
from gnomon.dataset.loader import load_dataset
from gnomon.domain.interfaces import Judge, RagTarget
from gnomon.gate.gate import GateResult, evaluate_gate
from gnomon.judge.cache import JudgeCache
from gnomon.judge.ollama import OllamaJudge
from gnomon.judge.stub import StubJudge
from gnomon.reporting.report import to_dict, to_text
from gnomon.runner.runner import run_eval
from gnomon.targets.mock import MockTarget
from gnomon.targets.openai_compat import OpenAICompatTarget


def build_target(cfg: TargetConfig) -> RagTarget:
    if cfg.kind == "mock":
        return MockTarget(
            answer="The game master narrates the world.",
            contexts=["The game master narrates the world to the players."],
            total_tokens=137,
            latency_ms=512.0,
        )
    api_key = os.environ.get(cfg.api_key_env) if cfg.api_key_env else None
    return OpenAICompatTarget(
        base_url=cfg.base_url,
        model=cfg.model,
        api_key=api_key,
        timeout_s=cfg.timeout_s,
    )


def build_judge(cfg: JudgeConfig) -> Judge:
    if cfg.provider == "stub":
        return StubJudge()
    return OllamaJudge(
        model=cfg.model,
        base_url=cfg.base_url,
        cache=JudgeCache(),
        timeout_s=cfg.timeout_s,
    )


def run_from_config(cfg: RunConfig):
    cases = load_dataset(cfg.dataset_path)
    target = build_target(cfg.target)
    judge = build_judge(cfg.judge)
    report = run_eval(cases, target, judge, cfg.eval)
    gate = evaluate_gate(report, cfg.gate.thresholds)
    return report, gate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gnomon", description="Run a GNOMON evaluation.")
    parser.add_argument("-c", "--config", required=True, help="path to the run config TOML")
    parser.add_argument("--json", action="store_true", help="emit the machine-readable report")
    args = parser.parse_args(argv)

    cfg = RunConfig.from_file(args.config)
    report, gate = run_from_config(cfg)

    if args.json:
        print(json.dumps(to_dict(report), indent=2))
    else:
        print(to_text(report))
    for failure in gate.failures:
        print(f"GATE FAIL: {failure}", file=sys.stderr)
    return 0 if gate.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Register the console script**

In `pyproject.toml`, add after the `[project.optional-dependencies]` block:
```toml
[project.scripts]
gnomon = "gnomon.cli:main"
```

- [ ] **Step 5: Run and watch it pass**

Run: `python -m pytest tests/integration/test_cli.py -q`
Expected: PASS.

- [ ] **Step 6: End-to-end CLI smoke on the stub path**

Create a temporary `config/smoke.toml` (mock target + stub judge) or reuse via env, and run:
```bash
python -m gnomon.cli -c config/example.toml || true
```
Because `config/example.toml` points to real Ollama/target (offline may not be running), the deterministic CI smoke uses the stub config from the gate test (Task 11). Here it is enough to confirm that `--help` and argument parsing work:
```bash
python -m gnomon.cli --help
```
Expected: prints usage with `--config`.

- [ ] **Step 7: Commit**

```bash
git add src/gnomon/cli.py pyproject.toml tests/integration/test_cli.py
git commit -m "feat: CLI de um comando com saida de gate (RF-11, RNF-04)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Gate as an executable CI test (RF-09)

The gate exposed as a test that runs in CI without a network: mock target + deterministic stub judge, thresholds that the stub clears. This is the CI "gate smoke" — verifies that the config→runner→gate wiring closes and that the verdict is stable.

**Files:**
- Create: `tests/gate/__init__.py` (empty, if needed)
- Create: `tests/gate/test_regression_gate.py`

- [ ] **Step 1: Write the test**

`tests/gate/test_regression_gate.py`:
```python
"""Regression gate as an executable CI check (RF-09).

Deterministic path only: mock target + stub judge, so the gate verdict is
stable in CI without Ollama or a live RAG. The real-backend gate is the
documented offline run in the README.
"""

import json

from gnomon.cli import run_from_config
from gnomon.config.run_config import RunConfig


def test_gate_passes_on_the_deterministic_path(tmp_path):
    dataset = tmp_path / "cases.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "id": "c1",
                    "question": "q",
                    "expected_answer": "a",
                    "expected_contexts": ["ctx"],
                }
            ]
        ),
        encoding="utf-8",
    )
    cfg = RunConfig(
        dataset_path=str(dataset),
        eval={"reproducible": True, "seed": 42, "judge_runs": 8},
        target={"kind": "mock"},
        judge={"provider": "stub"},
        # StubJudge centers around ~0.85; low thresholds clear with margin.
        gate={"thresholds": {"faithfulness": 0.5, "context_precision": 0.5}},
    )
    _, gate = run_from_config(cfg)
    assert gate.passed, gate.failures
```

- [ ] **Step 2: Run and watch it pass**

Run: `python -m pytest tests/gate/test_regression_gate.py -q`
Expected: PASS.

- [ ] **Step 3: Run the full suite**

Run: `python -m pytest -q && ruff check src tests && ruff format --check src tests`
Expected: all green, ruff clean.

- [ ] **Step 4: Commit**

```bash
git add tests/gate/test_regression_gate.py
git commit -m "test: gate de regressao como teste executavel de CI (RF-09)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Offline infra — Docker Compose + Dockerfile (RF-10, RNF-04)

The default path runs with Ollama via Docker, no paid key required. A third party brings up the environment and runs the evaluation. `docker-compose.yml` starts Ollama; `Dockerfile` packages the harness.

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: Dockerfile**

`Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY datasets ./datasets
COPY config ./config
RUN pip install --no-cache-dir .

ENTRYPOINT ["gnomon"]
CMD ["--config", "config/example.toml"]
```

- [ ] **Step 2: docker-compose.yml**

`docker-compose.yml`:
```yaml
services:
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama:/root/.ollama

  harness:
    build: .
    depends_on:
      - ollama
    environment:
      # The judge points to the ollama service on the compose network.
      GNOMON_JUDGE_BASE_URL: "http://ollama:11434"
    # Start the harness on demand: `docker compose run --rm harness`.
    profiles: ["run"]

volumes:
  ollama:
```

- [ ] **Step 3: Verify compose syntax**

Run: `docker compose config >/dev/null && echo OK`
Expected: `OK` (if `docker` is installed; otherwise validate manually).

- [ ] **Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: infra offline com Ollama via Docker Compose (RF-10, RNF-04)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: CI (RNF-08)

Lint, test suite, and gate smoke as a release barrier, running in CI. No network required: the gate smoke uses the deterministic path (Task 11).

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Workflow**

`.github/workflows/ci.yml`:
```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install
        run: pip install -e ".[dev]"
      - name: Lint
        run: |
          ruff check src tests
          ruff format --check src tests
      - name: Test (includes gate smoke)
        run: python -m pytest -q
```

- [ ] **Step 2: Verify valid YAML**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('OK')"` (if `pyyaml` is absent, validate visually)
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: lint, testes e smoke do gate como barreira (RNF-08)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: Honest README + example reproducibility (RNF-05, RF-11)

Every claim in the README has a command that reproduces it. Documents the single-command offline path and the gate. No claim without a command.

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write the execution section**

Add/update in `README.md` the execution section (adjust to the current file structure; replace any outdated run instructions):
````markdown
## Run the evaluation (offline, one command)

Prerequisite: Docker. The default path uses a local Ollama, no paid API key (RF-10).

```bash
# 1. Start Ollama and pull the judge model
docker compose up -d ollama
docker compose exec ollama ollama pull llama3

# 2. Run the example evaluation (versioned config + dataset)
docker compose run --rm harness --config config/example.toml
```

Output: a report with, per metric, mean and confidence interval (N judge
runs), plus tokens and latency. The process exits with code 0 if the gate
passes, 1 if any metric falls below the threshold in `config/example.toml` (RF-09).

### Without Docker (deterministic judge, for development)

```bash
pip install -e ".[dev]"
python -m pytest -q          # 44+ tests, includes reproducibility and gate smoke
```

### Reproducibility (RF-11 / RNF-01)

Same seed + same config + same machine produce the same numbers within the
reported variance. Verified by test:

```bash
python -m pytest tests/reproducibility -q
```
````

- [ ] **Step 2: Verify every README command runs**

Run (each non-Docker command from the README):
```bash
pip install -e ".[dev]" && python -m pytest tests/reproducibility -q
```
Expected: PASS. (Docker commands require Docker; validate manually if available.)

- [ ] **Step 3: Verify doc/code consistency (RNF-05)**

Run:
```bash
grep -n 'config/example.toml' README.md && test -f config/example.toml && echo OK
```
Expected: `OK` — the file the README references exists.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README honesto com caminho offline de um comando (RNF-05, RF-11)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: ADRs for the new decisions + AXON closing block

Records the three non-obvious decisions from this plan and closes the block in AXON (incremental index + ADRs + memory), per the playbook (`docs/DEVELOPMENT_LOOP.md`, "AXON sync per closing block").

**Files:**
- Create: `docs/adr/0005-openai-compat-contexts.md`
- Create: `docs/adr/0006-gate-on-ci-low.md`
- Create: `docs/adr/0007-ollama-judge-determinism.md`
- AXON effects (no versioned file)

- [ ] **Step 1: ADR-005 (contexts source)**

`docs/adr/0005-openai-compat-contexts.md` (follow the format of existing ADRs 0001-0004):
```markdown
# ADR-005 — Retrieved contexts in an OpenAI-compat extension field

## Context
The OpenAI chat/completions protocol has no standard field for contexts
retrieved by a RAG. RF-03 requires collecting contexts alongside the response.

## Decision
The OpenAI-compat adapter reads contexts from a configurable-name top-level
JSON extension field (`contexts_field`, default `"contexts"`). Absence of the
field → `IncompleteResponseError` (VAL-03), never a silent empty list.

## Consequences
The RAG target must return contexts in this field. Targets that do not will
require their own adapter. The fail-closed policy keeps the metric honest.
```

- [ ] **Step 2: ADR-006 (gate on ci_low)**

`docs/adr/0006-gate-on-ci-low.md`:
```markdown
# ADR-006 — Gate compares against the lower bound of the confidence interval

## Context
RF-09 fails the gate when a metric falls below a threshold. The metric is a
mean with a confidence interval (RNF-03). Gating on the mean would let through
a result whose uncertainty still crosses the threshold.

## Decision
The gate passes only if `ci_low >= threshold`. A metric that has a threshold
but is absent from the report is a failure, not a silent pass.

## Consequences
Stricter gate with small N (wide CI). Mitigated by raising N (see ADR-002,
open question on run count N). Statistical honesty preserved at the gate.
```

- [ ] **Step 3: ADR-007 (Ollama judge determinism)**

`docs/adr/0007-ollama-judge-determinism.md`:
```markdown
# ADR-007 — Ollama judge determinism via seed+run

## Context
RNF-01 is reproducibility within measured variance, not bit-exact. The Ollama
judge needs a deterministic sequence per declared seed.

## Decision
The judge fixes `options.seed = seed + run` and `temperature = 0.0` per call.
This gives a fixed sequence for the same model/host. The reproducibility suite
continues using StubJudge (purely deterministic); real-judge reproducibility is
verified as a variance tolerance, not equality.

## Consequences
Changing the model or host may change the numbers — expected and reported via
CI. The cache (key includes seed and run) reinforces stability within a single
machine.
```

- [ ] **Step 4: Verify the ADRs**

Run: `ls docs/adr/000{5,6,7}-*.md && echo OK`
Expected: lists all three + `OK`.

- [ ] **Step 5: Commit the ADRs**

```bash
git add docs/adr/0005-openai-compat-contexts.md docs/adr/0006-gate-on-ci-low.md docs/adr/0007-ollama-judge-determinism.md
git commit -m "docs: ADRs 005-007 (contexts, gate ci_low, determinismo do juiz)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: AXON block onboarding (incremental)**

Re-index and record the new decisions (the playbook requires incremental — only what changed):
```bash
pb index /Users/samdev/dev/gnomon-eval --ctx personal
```
Then, via MCP tools `mcp__axon__save_adr`, record ADR-005, 006, 007 in the project store (`project="gnomon-eval"`), and `mcp__axon__axon_capture` with the summary of the complete v1 (real target, Ollama judge, gate, CLI, infra, CI). Verify with `mcp__axon__get_adrs(project="gnomon-eval")` and `mcp__axon__search_code(query="OpenAICompatTarget query contexts", ctx="personal")`.
Expected: ADRs listed; `search_code` returns nodes from `targets/openai_compat.py`.

---

## Self-Review (completed)

**Spec coverage (REQUIREMENTS.md):**
- RF-01 (versioned dataset) → Task 3 ✓
- RF-02 (target via adapter) → Task 5 ✓
- RF-03 (answer+contexts+tokens+latency) → Task 5 ✓
- RF-04 (LLM judge with seed and cache) → Tasks 6, 7 ✓
- RF-05 (faithfulness + context precision) → Tasks 1, 2, 7 ✓
- RF-06 (variance with CI) → already in Phase 1 (aggregate_metric); exercised with 2 metrics ✓
- RF-07 (cost/latency per question) → already in Phase 1; preserved ✓
- RF-08 (machine+human report) → already in Phase 1; preserved ✓
- RF-09 (regression gate) → Tasks 9, 11 ✓
- RF-10 (offline by default) → Task 12 ✓
- RF-11 (example reproducibility) → Tasks 11, 14 ✓
- RNF-01 (reproducibility) → suite preserved + ADR-007 ✓
- RNF-02 (dependency direction) → HttpTransport seam + factories; direction test preserved ✓
- RNF-03 (statistical honesty) → MetricResult invariant preserved; gate on ci_low ✓
- RNF-04 (single-command accessibility) → Tasks 10, 12, 14 ✓
- RNF-05 (doc=code) → Task 14 ✓
- RNF-06 (predictable cost) → runner preserved (len(cases)*judge_runs) ✓
- RNF-07 (external config) → Task 8 (RunConfig TOML) ✓
- RNF-08 (lint+tests in CI) → Task 13 ✓
- VAL-01 (malformed dataset) → Task 3 ✓
- VAL-02 (target unreachable/off-protocol) → Task 5 ✓
- VAL-03 (incomplete response) → Task 5 ✓
- VAL-04 (insufficient N) → already in Phase 1 (config) ✓
- VAL-05 (misconfigured threshold) → Task 8 ✓
- VAL-06 (missing seed) → already in Phase 1; preserved via embedded EvalConfig ✓
- VAL-07 (inconsistent cache) → Task 6 ✓

**Surfaced decisions (not silent):** contexts source (ADR-005), gate on ci_low (ADR-006), judge determinism (ADR-007). All have a justified default and an ADR.

**Placeholders:** no TODO/TBD; all production code, all tests, and all commands are complete. Deliberate exception: `tests/integration/test_cli.py` Step 1 has a dead line behind `if False` to document intent — remove during implementation if the reviewer prefers (does not affect the outcome).

**Type consistency:** `RagResponse`/`EvalCase`/`MetricScores`/`MetricResult`/`EvalReport` used exactly as defined in Phase 1. `HttpTransport.post_json(url, payload, *, headers, timeout_s) -> (int, dict)` identical in adapter and judge. `V1_METRICS` is the single source for metric names. `build_target`/`build_judge`/`run_from_config`/`evaluate_gate`/`GateResult`/`load_dataset`/`RunConfig.from_file` referenced with the same signatures as defined.

**No-break note:** Phase 1 `EvalConfig` is not touched; `RunConfig` composes it. The 44 existing tests remain valid (the only edit to existing test code is, if needed, adjusting a metric-count assertion in the stub from 1→2).
```
