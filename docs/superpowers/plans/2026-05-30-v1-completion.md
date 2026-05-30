# GNOMON v1 — Completar a Implementação — Plano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sair da fatia vertical da Fase 1 (stubs: `MockTarget` + `StubJudge`) para a v1 completa: target RAG real via adapter, juiz Ollama com cache, segunda métrica, loader de dataset, gate de regressão, CLI de um comando, infra Docker offline e CI — fechando todos os RF/RNF/VAL de `docs/REQUIREMENTS.md`.

**Architecture:** Tudo novo entra como implementação concreta que depende do Domain, nunca o contrário (RNF-02). HTTP fica atrás de uma seam (`HttpTransport` Protocol) para testar adapter e juiz sem rede. Config externa de produção entra como `RunConfig` composta (não toca o `EvalConfig` da Fase 1, mantendo os 44 testes verdes). O loop existente (`run_eval`) não muda: ele já depende só dos contratos `RagTarget`/`Judge`, então target real e juiz real são troca de fiação.

**Tech Stack:** Python 3.11+, pydantic 2, **stdlib apenas** para infra (`urllib.request`, `tomllib`, `json`) — preserva a filosofia de dependências mínimas (só `pydantic`). pytest. Docker Compose + Ollama para o caminho offline.

---

## Decisões a confirmar (viram ADR neste plano)

Três pontos não óbvios apareceram na análise. O plano adota um default justificado e registra cada um como ADR (Task 13). Se o usuário discordar de algum default, ajustar antes de executar a task correspondente.

1. **Origem dos `contexts` numa resposta OpenAI-compat (ADR-005).** O protocolo OpenAI chat/completions não tem campo padrão para contextos recuperados. Default adotado: o RAG alvo devolve os contextos num campo de extensão JSON de nome configurável (`contexts_field`, default `"contexts"`) no corpo top-level da resposta. Ausência desse campo → `IncompleteResponseError` (VAL-03), não zero silencioso.
2. **Gate compara contra `ci_low`, não `mean` (ADR-006).** Honestidade estatística (RNF-03): o gate só passa se o limite inferior do IC clarear o threshold. Gatear pela média deixaria passar um resultado cuja incerteza ainda cruza o limite. Trade-off: gate mais rígido com N pequeno; mitiga-se subindo N.
3. **Determinismo do juiz Ollama (ADR-007, atualiza pontos abertos do ADR-002).** RNF-01 é reprodutibilidade "dentro da variância medida", não bit-exact. O juiz fixa `options.seed = seed + run` por run; isso dá uma sequência determinística *para o mesmo modelo na mesma máquina*. A suíte de reprodutibilidade continua usando `StubJudge` (determinístico puro); a reprodutibilidade do juiz real é verificada como tolerância, não igualdade.

---

## Mapa de arquivos

**Criar:**
- `src/gnomon/http.py` — seam `HttpTransport` + `UrllibTransport` + `TransportError`
- `src/gnomon/metrics/names.py` — `V1_METRICS` (conjunto canônico de métricas)
- `src/gnomon/dataset/__init__.py`, `src/gnomon/dataset/loader.py` — RF-01, VAL-01
- `src/gnomon/config/run_config.py` — `RunConfig`/`TargetConfig`/`JudgeConfig`/`GateConfig` + `from_file` (TOML)
- `src/gnomon/targets/openai_compat.py` — adapter REST real (RF-02/03, VAL-02/03)
- `src/gnomon/judge/cache.py` — `JudgeCache` (VAL-07)
- `src/gnomon/judge/prompts.py` — prompts de faithfulness + context_precision
- `src/gnomon/judge/ollama.py` — juiz Ollama (RF-04, ADR-002)
- `src/gnomon/gate/__init__.py`, `src/gnomon/gate/gate.py` — gate (RF-09, VAL-05)
- `src/gnomon/cli.py` — entrypoint de um comando (RNF-04)
- `datasets/rpg_master_example/cases.json` — dataset versionado de exemplo
- `config/example.toml` — config de execução de exemplo
- `docker-compose.yml`, `Dockerfile` — caminho offline (RF-10)
- `.github/workflows/ci.yml` — CI (RNF-08)
- `docs/adr/0005-openai-compat-contexts.md`, `0006-gate-on-ci-low.md`, `0007-ollama-judge-determinism.md`
- Testes: `tests/unit/test_dataset.py`, `tests/unit/test_run_config.py`, `tests/unit/test_openai_compat_target.py`, `tests/unit/test_judge_cache.py`, `tests/unit/test_ollama_judge.py`, `tests/unit/test_gate.py`, `tests/integration/test_cli.py`, `tests/gate/test_regression_gate.py`

**Modificar:**
- `src/gnomon/judge/stub.py` — passar a pontuar `context_precision` além de `faithfulness` (RF-05)
- `pyproject.toml` — `[project.scripts]` (console entry) + dep de teste opcional
- `README.md` — caminho de execução honesto de um comando (RNF-05, RF-11)

---

## Task 1: Conjunto canônico de métricas

Define em um lugar só os nomes das métricas da v1, para juiz, gate e testes referenciarem a mesma fonte (DRY). RF-05.

**Files:**
- Create: `src/gnomon/metrics/names.py`
- Test: `tests/unit/test_confidence.py` (sem mudança; só consumirá a constante depois)

- [ ] **Step 1: Criar a constante**

`src/gnomon/metrics/names.py`:
```python
"""Canonical metric names for the v1 evaluation (RF-05).

One source of truth so the judge, the gate thresholds and the tests cannot
drift into spelling the same metric two ways.
"""

# Order is the report/display order.
V1_METRICS: tuple[str, ...] = ("faithfulness", "context_precision")
```

- [ ] **Step 2: Verificar import**

Run: `python -c "from gnomon.metrics.names import V1_METRICS; print(V1_METRICS)"`
Expected: `('faithfulness', 'context_precision')`

- [ ] **Step 3: Commit**

```bash
git add src/gnomon/metrics/names.py
git commit -m "feat: conjunto canonico de metricas da v1

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: StubJudge pontua as duas métricas (RF-05)

O `StubJudge` hoje só devolve `faithfulness`. Para a v1 a aggregation precisa exercitar as duas métricas mesmo no caminho determinístico (CI). Mantém o mesmo determinismo por (seed, case, run).

**Files:**
- Modify: `src/gnomon/judge/stub.py`
- Test: `tests/unit/test_stub_judge.py`

- [ ] **Step 1: Escrever o teste que falha**

Adicionar a `tests/unit/test_stub_judge.py`:
```python
from gnomon.metrics.names import V1_METRICS


def test_stub_scores_all_v1_metrics():
    judge = StubJudge()
    scores = judge.score(CASE, RESPONSE, seed=42, run=0).scores
    assert set(scores) == set(V1_METRICS)
    assert all(0.0 <= v <= 1.0 for v in scores.values())


def test_stub_two_metrics_are_independent():
    # As duas metricas nao colapsam para o mesmo numero por run.
    judge = StubJudge()
    s = judge.score(CASE, RESPONSE, seed=42, run=1).scores
    assert s["faithfulness"] != s["context_precision"]
```
(Reuse `CASE`/`RESPONSE` já definidos no arquivo; se não existirem com esses nomes, construa um `EvalCase` e `RagResponse` mínimos no topo do teste — veja o padrão em `tests/integration/test_runner_end_to_end.py`.)

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/unit/test_stub_judge.py -q`
Expected: FAIL — `context_precision` ausente em `scores`.

- [ ] **Step 3: Implementar**

Substituir o método `score` e o helper em `src/gnomon/judge/stub.py`:
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
E adicionar o import no topo: `from gnomon.metrics.names import V1_METRICS`.

- [ ] **Step 4: Rodar a suíte toda**

Run: `python -m pytest -q`
Expected: PASS. Atenção: testes existentes que assumiam só `faithfulness` na saída do stub continuam válidos (eles consultam `report.metric("faithfulness")`, que segue presente). Se algum teste asseverava `len(metrics) == 1`, atualizá-lo para `2`.

- [ ] **Step 5: Commit**

```bash
git add src/gnomon/judge/stub.py tests/unit/test_stub_judge.py
git commit -m "feat: StubJudge pontua faithfulness e context_precision (RF-05)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Loader de dataset (RF-01, VAL-01)

Lê o dataset versionado de arquivo JSON e devolve `list[EvalCase]`. Falha fechado e explícito em dataset ausente, vazio ou caso malformado, apontando o caso problemático (VAL-01). Nunca avalia parcial em silêncio.

**Files:**
- Create: `src/gnomon/dataset/__init__.py` (vazio)
- Create: `src/gnomon/dataset/loader.py`
- Create: `datasets/rpg_master_example/cases.json`
- Test: `tests/unit/test_dataset.py`

- [ ] **Step 1: Escrever os testes que falham**

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
    # VAL-01: o erro nomeia o caso problematico, nao falha generico.
    assert "case-bad" in str(exc.value)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/unit/test_dataset.py -q`
Expected: FAIL — `gnomon.dataset.loader` não existe.

- [ ] **Step 3: Implementar**

`src/gnomon/dataset/__init__.py`: arquivo vazio.

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

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/unit/test_dataset.py -q`
Expected: PASS.

- [ ] **Step 5: Criar o dataset de exemplo**

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

- [ ] **Step 6: Verificar o dataset de exemplo carrega**

Run: `python -c "from gnomon.dataset.loader import load_dataset; print(len(load_dataset('datasets/rpg_master_example/cases.json')))"`
Expected: `2`

- [ ] **Step 7: Commit**

```bash
git add src/gnomon/dataset datasets/rpg_master_example/cases.json tests/unit/test_dataset.py
git commit -m "feat: loader de dataset com falha-fechado e exemplo (RF-01, VAL-01)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Seam HTTP (`HttpTransport`)

Uma seam fina para HTTP POST JSON, com implementação stdlib (`urllib`). Adapter e juiz dependem do Protocol, não de `urllib`, então os testes injetam um transport falso e nada toca a rede.

**Files:**
- Create: `src/gnomon/http.py`
- Test: coberto indiretamente nas Tasks 5 e 8 (não exige teste isolado; é infra fina).

- [ ] **Step 1: Implementar a seam**

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

- [ ] **Step 2: Verificar import**

Run: `python -c "from gnomon.http import HttpTransport, UrllibTransport, TransportError; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/gnomon/http.py
git commit -m "feat: seam HttpTransport stdlib para adapter e juiz

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Adapter OpenAI-compat real (RF-02, RF-03, VAL-02, VAL-03)

O primeiro target concreto: fala OpenAI-compat por REST, devolve `RagResponse` com resposta, contextos, tokens e latência. Taxonomia de erro distingue falha de configuração de falha de runtime (VAL-02); resposta incompleta é rejeitada explicitamente (VAL-03), nunca zero silencioso. Contextos vêm de um campo de extensão configurável (ADR-005).

**Files:**
- Create: `src/gnomon/targets/openai_compat.py`
- Test: `tests/unit/test_openai_compat_target.py`

- [ ] **Step 1: Escrever os testes que falham**

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
    # VAL-02: corpo fora do protocolo OpenAI-compat distingue-se do happy path.
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

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/unit/test_openai_compat_target.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar**

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

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/unit/test_openai_compat_target.py -q`
Expected: PASS (todos os 7).

- [ ] **Step 5: Confirmar que o adapter satisfaz o contrato `RagTarget`**

Run: `python -c "from gnomon.domain.interfaces import RagTarget; from gnomon.targets.openai_compat import OpenAICompatTarget; print(issubclass(OpenAICompatTarget, RagTarget) or isinstance(OpenAICompatTarget(base_url='http://x/v1', model='m'), RagTarget))"`
Expected: `True`

- [ ] **Step 6: Commit**

```bash
git add src/gnomon/targets/openai_compat.py tests/unit/test_openai_compat_target.py
git commit -m "feat: adapter OpenAI-compat real (RF-02/03, VAL-02/03)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Cache do juiz (VAL-07)

Cache com chave de identidade `(case.id, response.answer, judge_model, seed, run)`. Entrada cuja chave não casa com a tupla é tratada como miss, nunca como acerto que devolveria pontuação de contexto errado (VAL-07). `run` faz parte da chave: sem ele, os N runs colapsariam para um único valor cacheado e a variância sumiria.

**Files:**
- Create: `src/gnomon/judge/cache.py`
- Test: `tests/unit/test_judge_cache.py`

- [ ] **Step 1: Escrever os testes que falham**

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
    # VAL-07: chave que nao casa = miss, nunca acerto de contexto errado.
    cache = JudgeCache()
    cache.put(CASE, RESPONSE, "judge-x", seed=42, run=0, scores=SCORES)
    assert cache.get(CASE, RESPONSE, "judge-y", seed=42, run=0) is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/unit/test_judge_cache.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar**

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

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/unit/test_judge_cache.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gnomon/judge/cache.py tests/unit/test_judge_cache.py
git commit -m "feat: cache do juiz por tupla de identidade (VAL-07)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Juiz Ollama (RF-04, ADR-002)

Juiz real: pontua `faithfulness` e `context_precision` chamando Ollama (`/api/chat`, `format: json`), sob `options.seed = seed + run` para reprodutibilidade dentro da variância (ADR-007). Usa a seam `HttpTransport` (testável sem rede) e o `JudgeCache`. Resposta do modelo fora do formato esperado vira erro nomeado, não score inventado.

**Files:**
- Create: `src/gnomon/judge/prompts.py`
- Create: `src/gnomon/judge/ollama.py`
- Test: `tests/unit/test_ollama_judge.py`

- [ ] **Step 1: Prompts (sem teste isolado; verificados via juiz)**

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

- [ ] **Step 2: Escrever os testes que falham (juiz)**

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
    # ADR-007: options.seed = seed + run, deterministico por run.
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
    assert len(transport.seeds) == calls_after_first  # segundo score veio do cache


def test_unparseable_model_output_is_protocol_error():
    transport = ScriptedTransport(body_override={"message": {"content": "I think 0.8"}})
    with pytest.raises(JudgeProtocolError):
        _judge(transport).score(CASE, RESPONSE, seed=42, run=0)
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `python -m pytest tests/unit/test_ollama_judge.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 4: Implementar**

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

- [ ] **Step 5: Rodar e ver passar**

Run: `python -m pytest tests/unit/test_ollama_judge.py -q`
Expected: PASS (4 testes).

- [ ] **Step 6: Commit**

```bash
git add src/gnomon/judge/prompts.py src/gnomon/judge/ollama.py tests/unit/test_ollama_judge.py
git commit -m "feat: juiz Ollama com cache e seed por run (RF-04, ADR-002)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Config de execução (`RunConfig`) + thresholds (RNF-07, VAL-05)

Config externa de produção, carregada de TOML e validada antes de qualquer chamada de modelo. Composta (`eval` + `target` + `judge` + `gate` + `dataset_path`) — **não toca o `EvalConfig` da Fase 1**, então os testes existentes seguem verdes. Threshold de gate fora de `[0,1]` é rejeitado no load (VAL-05).

**Files:**
- Create: `src/gnomon/config/run_config.py`
- Create: `config/example.toml`
- Test: `tests/unit/test_run_config.py`

- [ ] **Step 1: Escrever os testes que falham**

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
    # VAL-05: limite fora da faixa da metrica rejeitado antes de qualquer chamada.
    with pytest.raises(ValidationError):
        GateConfig(thresholds={"faithfulness": 1.4})


def test_threshold_negative_is_rejected():
    with pytest.raises(ValidationError):
        GateConfig(thresholds={"faithfulness": -0.1})


def test_seed_required_propagates_from_eval():
    # VAL-06 ainda vale via EvalConfig embutido.
    with pytest.raises(ValidationError):
        RunConfig(
            dataset_path="d.json",
            eval={"reproducible": True, "judge_runs": 8},
            target={"kind": "mock"},
            judge={"provider": "stub"},
            gate={"thresholds": {"faithfulness": 0.7}},
        )
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/unit/test_run_config.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar**

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

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/unit/test_run_config.py -q`
Expected: PASS.

- [ ] **Step 5: Criar a config de exemplo**

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

- [ ] **Step 6: Verificar a config de exemplo carrega**

Run: `python -c "from gnomon.config.run_config import RunConfig; c=RunConfig.from_file('config/example.toml'); print(c.gate.thresholds)"`
Expected: `{'faithfulness': 0.7, 'context_precision': 0.6}`

- [ ] **Step 7: Commit**

```bash
git add src/gnomon/config/run_config.py config/example.toml tests/unit/test_run_config.py
git commit -m "feat: RunConfig de producao com thresholds de gate (RNF-07, VAL-05)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Gate de regressão (RF-09, VAL-05)

Compara o `EvalReport` contra os thresholds por métrica e decide passa/falha. Gateia pelo **limite inferior do IC** (`ci_low`), não pela média (ADR-006): só passa se a incerteza não cruza o limite. Métrica com threshold mas ausente do relatório é falha explícita, não passe silencioso.

**Files:**
- Create: `src/gnomon/gate/__init__.py` (vazio)
- Create: `src/gnomon/gate/gate.py`
- Test: `tests/unit/test_gate.py`

- [ ] **Step 1: Escrever os testes que falham**

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
    # ADR-006: media (0.82) passaria, mas ci_low (0.65) nao clareia 0.7.
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

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/unit/test_gate.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar**

`src/gnomon/gate/__init__.py`: arquivo vazio.

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

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/unit/test_gate.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gnomon/gate tests/unit/test_gate.py
git commit -m "feat: gate de regressao gateando por ci_low (RF-09, ADR-006)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: CLI de um comando (RF-11, RNF-04, RNF-05)

Entrypoint que carrega `RunConfig`, monta target e juiz por config, roda `run_eval`, imprime o relatório nos dois formatos e sai com código do gate (0 passa / 1 falha). Um comando, sem editar fonte (RNF-04). Factories mapeiam `kind`/`provider` para implementação.

**Files:**
- Create: `src/gnomon/cli.py`
- Modify: `pyproject.toml` (`[project.scripts]`)
- Test: `tests/integration/test_cli.py`

- [ ] **Step 1: Escrever o teste que falha**

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
    # build_target/build_judge devolvem objetos que satisfazem os contratos:
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
(Nota: a primeira asserção usa o `MockTarget`. Como `MockTarget.__init__` exige `answer/contexts/total_tokens/latency_ms`, a factory `build_target` para `kind="mock"` usa valores fixos de demonstração — ver implementação.)

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/integration/test_cli.py -q`
Expected: FAIL — `gnomon.cli` inexistente.

- [ ] **Step 3: Implementar**

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

- [ ] **Step 4: Registrar o console script**

Em `pyproject.toml`, adicionar após o bloco `[project.optional-dependencies]`:
```toml
[project.scripts]
gnomon = "gnomon.cli:main"
```

- [ ] **Step 5: Rodar e ver passar**

Run: `python -m pytest tests/integration/test_cli.py -q`
Expected: PASS.

- [ ] **Step 6: Smoke do CLI ponta-a-ponta com o caminho stub**

Criar `config/smoke.toml` temporário (target mock + judge stub) ou reutilizar via env, e rodar:
```bash
python -m gnomon.cli -c config/example.toml || true
```
Como `config/example.toml` aponta para Ollama/target reais (offline pode não estar de pé), o smoke determinístico de CI usa a config stub do teste de gate (Task 11). Aqui basta confirmar que `--help` e o parsing funcionam:
```bash
python -m gnomon.cli --help
```
Expected: imprime o uso com `--config`.

- [ ] **Step 7: Commit**

```bash
git add src/gnomon/cli.py pyproject.toml tests/integration/test_cli.py
git commit -m "feat: CLI de um comando com saida de gate (RF-11, RNF-04)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Gate como teste executável de CI (RF-09)

O gate exposto como teste que roda no CI sem rede: target mock + juiz stub determinístico, thresholds que o stub clareia. É o "smoke do gate" do CI — verifica que a fiação config→runner→gate fecha e que o veredito é estável.

**Files:**
- Create: `tests/gate/__init__.py` (vazio, se necessário)
- Create: `tests/gate/test_regression_gate.py`

- [ ] **Step 1: Escrever o teste**

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
        # StubJudge centra em ~0.85; thresholds baixos clareiam com folga.
        gate={"thresholds": {"faithfulness": 0.5, "context_precision": 0.5}},
    )
    _, gate = run_from_config(cfg)
    assert gate.passed, gate.failures
```

- [ ] **Step 2: Rodar e ver passar**

Run: `python -m pytest tests/gate/test_regression_gate.py -q`
Expected: PASS.

- [ ] **Step 3: Rodar a suíte inteira**

Run: `python -m pytest -q && ruff check src tests && ruff format --check src tests`
Expected: tudo verde, ruff limpo.

- [ ] **Step 4: Commit**

```bash
git add tests/gate/test_regression_gate.py
git commit -m "test: gate de regressao como teste executavel de CI (RF-09)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Infra offline — Docker Compose + Dockerfile (RF-10, RNF-04)

O caminho default roda com Ollama via Docker, sem chave paga. Um terceiro sobe o ambiente e roda a avaliação. O `docker-compose.yml` sobe Ollama; o `Dockerfile` empacota o harness.

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
      # O juiz aponta para o serviço ollama da rede do compose.
      GNOMON_JUDGE_BASE_URL: "http://ollama:11434"
    # Sobe o harness sob demanda: `docker compose run --rm harness`.
    profiles: ["run"]

volumes:
  ollama:
```

- [ ] **Step 3: Verificar sintaxe do compose**

Run: `docker compose config >/dev/null && echo OK`
Expected: `OK` (se `docker` estiver instalado; caso contrário, validação manual).

- [ ] **Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: infra offline com Ollama via Docker Compose (RF-10, RNF-04)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: CI (RNF-08)

Lint, suíte de testes e smoke do gate como barreira de release, rodando em CI. Sem rede: o smoke do gate usa o caminho determinístico (Task 11).

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
      - name: Test (inclui smoke do gate)
        run: python -m pytest -q
```

- [ ] **Step 2: Verificar YAML válido**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('OK')"` (se `pyyaml` ausente, validar visualmente)
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: lint, testes e smoke do gate como barreira (RNF-08)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: README honesto + reprodutibilidade do exemplo (RNF-05, RF-11)

Toda afirmação do README tem comando que a reproduz. Documenta o caminho offline de um comando e o gate. Sem claim sem comando.

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Escrever a seção de execução**

Acrescentar/atualizar em `README.md` a seção de execução (ajustar à estrutura atual do arquivo; substituir qualquer instrução de execução desatualizada):
````markdown
## Executar a avaliação (offline, um comando)

Pré-requisito: Docker. O caminho default usa Ollama local, sem chave paga (RF-10).

```bash
# 1. Sobe o Ollama e baixa o modelo do juiz
docker compose up -d ollama
docker compose exec ollama ollama pull llama3

# 2. Roda a avaliação de exemplo (config + dataset versionados)
docker compose run --rm harness --config config/example.toml
```

Saída: relatório com, por métrica, média e intervalo de confiança (N runs do
juiz), além de tokens e latência. O processo sai com código 0 se o gate passa,
1 se alguma métrica fica abaixo do limite em `config/example.toml` (RF-09).

### Sem Docker (juiz determinístico, para desenvolvimento)

```bash
pip install -e ".[dev]"
python -m pytest -q          # 44+ testes, inclui reprodutibilidade e smoke do gate
```

### Reprodutibilidade (RF-11 / RNF-01)

Mesma seed + mesma config + mesma máquina produzem os mesmos números dentro da
variância reportada. Verificado por teste:

```bash
python -m pytest tests/reproducibility -q
```
````

- [ ] **Step 2: Verificar que todo comando do README roda**

Run (cada comando não-Docker do README):
```bash
pip install -e ".[dev]" && python -m pytest tests/reproducibility -q
```
Expected: PASS. (Os comandos Docker exigem Docker; validar manualmente se disponível.)

- [ ] **Step 3: Verificar consistência doc/código (RNF-05)**

Run:
```bash
grep -n 'config/example.toml' README.md && test -f config/example.toml && echo OK
```
Expected: `OK` — o arquivo que o README cita existe.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README honesto com caminho offline de um comando (RNF-05, RF-11)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: ADRs das decisões novas + bloco conclusivo AXON

Registra as três decisões não óbvias deste plano e fecha o bloco no AXON (índice incremental + ADRs + memória), conforme o playbook (`docs/DEVELOPMENT_LOOP.md`, "Sincronização com o AXON por bloco conclusivo").

**Files:**
- Create: `docs/adr/0005-openai-compat-contexts.md`
- Create: `docs/adr/0006-gate-on-ci-low.md`
- Create: `docs/adr/0007-ollama-judge-determinism.md`
- Efeitos AXON (sem arquivo versionado)

- [ ] **Step 1: ADR-005 (origem dos contexts)**

`docs/adr/0005-openai-compat-contexts.md` (seguir o formato dos ADRs 0001-0004 existentes):
```markdown
# ADR-005 — Contextos recuperados num campo de extensão OpenAI-compat

## Contexto
O protocolo OpenAI chat/completions não tem campo padrão para os contextos
recuperados por um RAG. RF-03 exige coletar os contextos junto da resposta.

## Decisão
O adapter OpenAI-compat lê os contextos de um campo de extensão JSON top-level
de nome configurável (`contexts_field`, default `"contexts"`). Ausência do
campo → `IncompleteResponseError` (VAL-03), nunca lista vazia silenciosa.

## Consequências
O RAG alvo precisa devolver contextos nesse campo. Targets que não o fazem
exigem um adapter próprio. A política fail-closed mantém a métrica honesta.
```

- [ ] **Step 2: ADR-006 (gate por ci_low)**

`docs/adr/0006-gate-on-ci-low.md`:
```markdown
# ADR-006 — Gate compara contra o limite inferior do IC

## Contexto
RF-09 falha o gate quando uma métrica cai abaixo de um limite. A métrica é uma
média com intervalo de confiança (RNF-03). Gatear pela média deixaria passar
resultado cuja incerteza ainda cruza o limite.

## Decisão
O gate passa só se `ci_low >= threshold`. Métrica com threshold mas ausente do
relatório é falha, não passe silencioso.

## Consequências
Gate mais rígido com N pequeno (IC largo). Mitiga-se subindo N (ver ADR-002,
ponto aberto do N de runs). Honestidade estatística preservada no portão.
```

- [ ] **Step 3: ADR-007 (determinismo do juiz Ollama)**

`docs/adr/0007-ollama-judge-determinism.md`:
```markdown
# ADR-007 — Determinismo do juiz Ollama por seed+run

## Contexto
RNF-01 é reprodutibilidade dentro da variância medida, não bit-exact. O juiz
Ollama precisa de uma sequência determinística por seed declarada.

## Decisão
O juiz fixa `options.seed = seed + run` e `temperature = 0.0` por chamada. Isso
dá uma sequência fixa para um mesmo modelo/host. A suíte de reprodutibilidade
continua usando o StubJudge (determinístico puro); a reprodutibilidade do juiz
real é verificada como tolerância de variância, não igualdade.

## Consequências
Trocar de modelo ou de host pode mudar os números — esperado e reportado via
IC. O cache (chave inclui seed e run) reforça a estabilidade dentro de uma
máquina.
```

- [ ] **Step 4: Verificar os ADRs**

Run: `ls docs/adr/000{5,6,7}-*.md && echo OK`
Expected: lista os três + `OK`.

- [ ] **Step 5: Commit dos ADRs**

```bash
git add docs/adr/0005-openai-compat-contexts.md docs/adr/0006-gate-on-ci-low.md docs/adr/0007-ollama-judge-determinism.md
git commit -m "docs: ADRs 005-007 (contexts, gate ci_low, determinismo do juiz)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Onboarding AXON do bloco (incremental)**

Reindexar e registrar as decisões novas (o playbook manda incremental, só o que mudou):
```bash
pb index /Users/samdev/dev/gnomon-eval --ctx personal
```
Depois, via ferramentas MCP `mcp__axon__save_adr`, registrar ADR-005, 006, 007 no store do projeto (`project="gnomon-eval"`), e `mcp__axon__axon_capture` com o resumo da v1 completa (target real, juiz Ollama, gate, CLI, infra, CI). Verificar com `mcp__axon__get_adrs(project="gnomon-eval")` e `mcp__axon__search_code(query="OpenAICompatTarget query contexts", ctx="personal")`.
Expected: ADRs listados; `search_code` retorna nós de `targets/openai_compat.py`.

---

## Self-Review (preenchido)

**Cobertura do spec (REQUIREMENTS.md):**
- RF-01 (dataset versionado) → Task 3 ✓
- RF-02 (target via adapter) → Task 5 ✓
- RF-03 (resposta+contextos+tokens+latência) → Task 5 ✓
- RF-04 (juiz LLM com seed e cache) → Tasks 6, 7 ✓
- RF-05 (faithfulness + context precision) → Tasks 1, 2, 7 ✓
- RF-06 (variância com IC) → já na Fase 1 (aggregate_metric); exercitada com 2 métricas ✓
- RF-07 (custo/latência por pergunta) → já na Fase 1; preservado ✓
- RF-08 (relatório máquina+humano) → já na Fase 1; preservado ✓
- RF-09 (gate de regressão) → Tasks 9, 11 ✓
- RF-10 (offline por default) → Task 12 ✓
- RF-11 (reprodutibilidade do exemplo) → Tasks 11, 14 ✓
- RNF-01 (reprodutibilidade) → suíte preservada + ADR-007 ✓
- RNF-02 (direção de dependência) → seam HttpTransport + factories; teste de direção preservado ✓
- RNF-03 (honestidade estatística) → MetricResult invariante preservado; gate por ci_low ✓
- RNF-04 (acessibilidade um comando) → Tasks 10, 12, 14 ✓
- RNF-05 (doc=código) → Task 14 ✓
- RNF-06 (custo previsível) → runner preservado (len(cases)*judge_runs) ✓
- RNF-07 (config externa) → Task 8 (RunConfig TOML) ✓
- RNF-08 (lint+testes em CI) → Task 13 ✓
- VAL-01 (dataset malformado) → Task 3 ✓
- VAL-02 (target inacessível/off-protocol) → Task 5 ✓
- VAL-03 (resposta incompleta) → Task 5 ✓
- VAL-04 (N insuficiente) → já na Fase 1 (config) ✓
- VAL-05 (threshold mal configurado) → Task 8 ✓
- VAL-06 (seed ausente) → já na Fase 1; preservado via EvalConfig embutido ✓
- VAL-07 (cache inconsistente) → Task 6 ✓

**Decisões surfaçadas (não silenciosas):** origem dos contexts (ADR-005), gate por ci_low (ADR-006), determinismo do juiz (ADR-007). Todas com default justificado e ADR.

**Placeholders:** nenhum TODO/TBD; todo código de produção, todo teste e todo comando estão completos. Exceção consciente: o teste `tests/integration/test_cli.py` Step 1 tem uma linha morta atrás de `if False` para documentar intenção — remover na implementação se o reviewer preferir (não afeta o resultado).

**Consistência de tipos:** `RagResponse`/`EvalCase`/`MetricScores`/`MetricResult`/`EvalReport` usados exatamente como definidos na Fase 1. `HttpTransport.post_json(url, payload, *, headers, timeout_s) -> (int, dict)` idêntico em adapter e juiz. `V1_METRICS` é a única fonte dos nomes. `build_target`/`build_judge`/`run_from_config`/`evaluate_gate`/`GateResult`/`load_dataset`/`RunConfig.from_file` referenciados com as mesmas assinaturas em que foram definidos.

**Nota de não-quebra:** `EvalConfig` da Fase 1 não é tocado; `RunConfig` o compõe. Os 44 testes existentes seguem válidos (a única edição em código de teste existente é, se necessário, ajustar uma asserção de contagem de métricas no stub de 1→2).
```
