# Validação de contrato do GNOMON para integração GraphRAG (pull-based)

> Validado lendo código e testes do repositório `sammyjdev/gnomon-eval`. Cada item cita a fonte real (`arquivo:linha`).
>
> **As-of:** validado contra o master de 2026-06-11 (commit `b32d69c`). O master avançou desde então (ChatEval multi-turn etc.); as citações `arquivo:linha` podem ter drifted — reverifique antes de depender de uma linha específica. A superfície do contrato (RagTarget/RagResponse/run_eval) é estável.
>
> **Aviso:** alguns nomes assumidos na pergunta não batem com o código — as divergências estão sinalizadas em cada item.

---

## A. Empacotamento / import

### 1. Nome da distribuição e referência sem PyPI
- Nome da distribuição: **`gnomon-eval`**, versão `0.1.0` (`pyproject.toml:6-7`). Build backend: `hatchling`.
- **Nome do pacote de import é diferente: `gnomon`** (≠ distribuição). Ver `pyproject.toml:25-26`: `[tool.hatch.build.targets.wheel] packages = ["src/gnomon"]`.
- Não está no PyPI. Formas de referência no `pyproject` do consumidor:
  - **git canônica**: `gnomon-eval @ git+https://github.com/sammyjdev/gnomon-eval.git@<ref>` (repo no escopo: `sammyjdev/gnomon-eval`; o `origin` local é apenas um proxy `http://local_proxy@127.0.0.1:.../git/sammyjdev/gnomon-eval`).
  - **path local editável**: `pip install -e .` (usado no README, `README.md:55,63`), ou dependência por path `gnomon-eval @ file:///caminho`.

### 2. Caminhos de import exatos
Não há re-export no topo (`src/gnomon/__init__.py` vazio; todos os `__init__.py` de subpacote vazios). Use o caminho completo:

```python
from gnomon.runner.runner import run_eval               # runner.py:23 (usado em cli.py:22)
from gnomon.metrics.confidence import aggregate_metric  # confidence.py:31 (usado em runner.py:20)
```

### 3. Python e dependências de runtime
- `requires-python = ">=3.11"` (`pyproject.toml:11`) — usa `tomllib` da stdlib (`run_config.py:10`).
- **Única dependência de runtime: `pydantic>=2.6`** (`pyproject.toml:12-14`). HTTP é stdlib `urllib` (`UrllibTransport` em `gnomon/http.py`, sem lib externa).
- **LLM-judge: o GNOMON traz o cliente embutido**, não espera que você traga o seu. Dois judges atrás do mesmo Protocol: `OllamaJudge` (cliente Ollama local via HTTP stdlib, `judge/ollama.py:34`) e `StubJudge` (determinístico, `judge/stub.py:20`). **Nenhum cliente OpenAI/Anthropic embutido** — o judge default é Ollama local. O consumidor só *configura* provider/modelo (TOML), não injeta um cliente.

---

## B. Contrato do target (pull-based)

### 4. Protocol do target — confirma `RagTarget`
`domain/interfaces.py:13-19`, `@runtime_checkable Protocol`. Método único:

```python
def query(self, question: str) -> RagResponse   # interfaces.py:17
```

- `question: str` → retorna `RagResponse`. **É síncrono** (não async).

### 5. run_eval chama só `query`
`target.query(case.question)` (`runner.py:31`). Não acessa `name`, `setup`, `teardown` nem qualquer outro atributo do target. (Os judges têm `model_name`, mas isso é do lado Judge, não do target.)

---

## C. RagResponse (`domain/models.py:25-33`, modelo `frozen`)

### 6. Campos completos
Todos **obrigatórios**, sem default:

| campo | tipo | constraint | fonte |
|---|---|---|---|
| `answer` | `str` | nenhum | models.py:30 |
| `contexts` | `list[str]` | nenhum | models.py:31 |
| `total_tokens` | `int` | `Field(ge=0)` ✓ validado ≥0 | models.py:32 |
| `latency_ms` | `float` | `Field(ge=0.0)` ✓ validado ≥0 | models.py:33 |

### 7. Crítico
- **Campo de resposta gerada: SIM → `answer: str`** (`models.py:30`).
- **Campo de contextos recuperados: SIM → `contexts: list[str]`** (`models.py:31`). **Tipo é `list[str]` puro — NÃO são objetos com `.text`**, não há `source_documents`.
- **NÃO há campo de id na resposta.** `RagResponse` não liga à pergunta. O vínculo é **posicional**: o runner pareia `case → response` no laço (`runner.py:30-31`), e o `id` mora no `EvalCase` (`models.py:19`), não no response.

---

## D. Entrada de run_eval / dataset

### 8. Assinatura de run_eval
`runner.py:23-25` — sem defaults, tudo obrigatório:

```python
def run_eval(
    cases: list[EvalCase], target: RagTarget, judge: Judge, config: EvalConfig
) -> EvalReport
```

### 9. Schema do exemplo — `EvalCase`
`domain/models.py:14-22` (`frozen`), carregado por `load_dataset` (`dataset/loader.py:21`):

| campo | tipo | obrigatório |
|---|---|---|
| `id` | `str` (`min_length=1`) | sim |
| `question` | `str` (`min_length=1`) | sim |
| `expected_answer` | `str` (`min_length=1`) | sim |
| `expected_contexts` | `list[str]` (`min_length=1`) | sim |

- **Ground-truth (`expected_answer`, `expected_contexts`) é EXIGIDO pelo schema do dataset.** **PORÉM, atenção (divergência crítica):** o prompt do judge v1 **não usa** esses campos. `build_prompt` (`judge/prompts.py:28-36`) referencia apenas `case.question`, `response.answer`, `response.contexts`. **Logo, na implementação atual, `faithfulness` e `context_precision` são reference-free** — o ground-truth é obrigatório-porém-ignorado pelo scoring. Você precisa fornecê-lo para o dataset validar, mas ele não entra na nota.

### 10. Como as métricas são selecionadas
**Não são passadas a `run_eval`.** As métricas são exatamente as chaves que o judge retorna em `MetricScores.scores`; o runner coleta por `metric_name` do output do judge (`runner.py:44-48`). O conjunto canônico `V1_METRICS = ("faithfulness", "context_precision")` está hardcoded no judge/prompt (`metrics/names.py:8`). Ou seja: **você seleciona métricas escolhendo/configurando o judge, não por argumento de `run_eval`.**

---

## E. Métricas v1

### 11. Identificadores exatos
Strings `"faithfulness"` e `"context_precision"` (`metrics/names.py:8`). São **chaves string de dict**, não objetos.

### 12. O que cada uma consome
Do prompt, `judge/prompts.py:14-22`:

- `faithfulness`: "how well the ANSWER is grounded in the CONTEXTS" → precisa de **`response.answer` + `response.contexts`**. **Exige resposta gerada.**
- `context_precision`: "how relevant the CONTEXTS are to the QUESTION" → precisa de **`case.question` + `response.contexts`**. **NÃO usa a answer.**
- **Decisão para o GLYPH:** `faithfulness` obriga um passo de geração (answer); `context_precision` sozinha não precisaria. Como ambas são pedidas numa única chamada, na prática você terá de fornecer `answer` de qualquer forma. Nenhuma das duas usa ground-truth.

### 13. Exigem LLM-judge? SIM
Configuração via bloco TOML `[judge]` (`config/run_config.py:29-35`; wiring em `cli.py:45-53`):

- `provider`: `"ollama"` ou `"stub"` (`run_config.py:31`).
- `OllamaJudge` (`judge/ollama.py:34-89`): `model` + `base_url`, `temperature=0.0`, `seed = seed + run` (`ollama.py:72`). **Uma chamada de modelo por `score()`** = por `(case, run)`. Custo billável = **`len(cases) * config.judge_runs`** chamadas, sem multiplicador por-métrica (todas as métricas numa só chamada) — documentado em `runner.py:8-12` e implementado em `ollama.py:64-89`. Cache por `(case, response, model, seed, run)` via `JudgeCache` (`ollama.py:53-62`).
- **Não há env var para provider**; chave de API é só do *target* (`api_key_env`, `run_config.py:23`). **Chamada é por-exemplo → custo escala com dataset × judge_runs.**

---

## F. Saída / agregação

### 14. run_eval retorna `EvalReport`
`models.py:88-115`:

- `metrics: list[MetricResult]` + `per_case_cost: list[CaseCost]`.
- `MetricResult` (`models.py:51-67`): `metric, mean, ci_low, ci_high, n (≥2), confidence_level`.
- Helpers: `.metric(name)` (`models.py:101`), `.total_tokens` (`:107`), `.mean_latency_ms` (`:112`).
- **NÃO contém scores por-exemplo de qualidade.** `per_case_cost` é só custo/latência por caso (`CaseCost`: `case_id, total_tokens, latency_ms`, `models.py:78-85`).

### 15. `aggregate_metric`
`metrics/confidence.py:31-33`:

```python
def aggregate_metric(
    metric: str, case_scores: list[float], *, confidence_level: float = 0.95, seed: int
) -> MetricResult
```

- Retorna `MetricResult` = média sobre casos + **CI por bootstrap percentil semeado** (2000 resamples, `confidence.py:28,44-54`). Exige n≥2 (`MIN_CASES`, `confidence.py:22,36`).
- **Crítico para o seu bootstrap de CI percentil:** **`run_eval` NÃO expõe os scores por-exemplo.** O runner monta `case_scores_by_metric` internamente (`runner.py:28,47-48`) e o **descarta** após agregar — o `EvalReport` guarda só `MetricResult` agregado + custo por-caso. **Você não consegue os scores de qualidade por-caso a partir do output de `run_eval`.** Opções para a P3.0:
  - **(a)** não usar `run_eval`: chame `judge.score(case, response, seed=..., run=...)` você mesmo por caso, colete os floats por-métrica, e então passe sua própria `list[float]` para `aggregate_metric` (que já faz exatamente o bootstrap percentil que você quer — pode reusar em vez de reimplementar); ou
  - **(b)** alterar `run_eval` para devolver também `case_scores_by_metric`. **Essa é a principal lacuna de integração da P3.0.**

---

## G. Exemplo mínimo end-to-end

Real, de `tests/integration/test_runner_end_to_end.py:27-59` (o menor fluxo completo: definir cases + target, rodar `run_eval`, ler o report agregado):

```python
from gnomon.config.config import EvalConfig
from gnomon.domain.models import EvalCase
from gnomon.judge.stub import StubJudge
from gnomon.runner.runner import run_eval
from gnomon.targets.mock import MockTarget

CASE = EvalCase(
    id="case-1",
    question="Who narrates the world?",
    expected_answer="The game master narrates the world.",
    expected_contexts=["The game master narrates the world to the players."],
)
CASE2 = EvalCase(
    id="case-2",
    question="Who adjudicates the rules?",
    expected_answer="The game master adjudicates the rules.",
    expected_contexts=["The game master adjudicates the rules at the table."],
)

target = MockTarget(
    answer="The game master narrates the world.",
    contexts=["The game master narrates the world to the players."],
    total_tokens=137, latency_ms=512.0,
)

cfg = EvalConfig(reproducible=True, seed=42, judge_runs=8)
report = run_eval([CASE, CASE2], target, StubJudge(), cfg)

faithfulness = report.metric("faithfulness")   # MetricResult
assert faithfulness.n == 2                      # n = nº de CASOS, não runs (ADR-008)
assert 0.0 <= faithfulness.ci_low <= faithfulness.mean <= faithfulness.ci_high <= 1.0
```

A agregação acontece **dentro** de `run_eval` (`runner.py:50-56`, que chama `aggregate_metric`). Para o seu fluxo pull-based, o equivalente substituindo `MockTarget`/`StubJudge` pelos seus adaptadores GraphRAG é trivial — o único ponto de atrito é o item 15 (per-case scores não expostos).

---

## Resumo dos 3 pontos que mais afetam a P3.0

1. **Per-case scores de qualidade não saem de `run_eval`** — você precisa chamar `judge.score` por caso (ou patchear o runner) para o seu bootstrap percentil. `aggregate_metric` já faz bootstrap percentil semeado e é reutilizável.
2. **Métricas v1 são reference-free na prática** — o judge ignora `expected_answer`/`expected_contexts` (embora o schema os exija). `faithfulness` precisa da `answer` gerada; `context_precision` não.
3. **Judge embutido = Ollama local**, 1 chamada por `(case, run)`, custo = `len(cases) * judge_runs`. Nada de cliente externo a configurar além de `model`/`base_url` no TOML.
