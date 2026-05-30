# GNOMON

> Avalia um pipeline RAG e reporta qualidade **com o intervalo de confiança junto**, mais custo e latência, rodando offline com Ollama. Honestidade estatística é invariante, não enfeite: nenhuma métrica de juiz sai como número solto.

## O que isto faz

Lê um dataset de casos de avaliação versionado, roda cada caso contra um RAG alvo (via adapter), pontua as respostas com um juiz LLM e reporta **faithfulness** e **context precision** — cada uma com intervalo de confiança — junto de custo em tokens e latência em milissegundos. O mesmo eval roda como teste de regressão no CI e falha o build quando uma métrica cai abaixo de um limite configurável.

O exemplo avalia um **MockTarget** (respostas canônicas) pontuado por um juiz **Ollama local**, sem dependência externa nem chave paga. Trocar para um RAG real que fale o protocolo OpenAI-compat é mudar o bloco `[target]` em `config/example.toml` — não o código.

## Executar a avaliação (offline, um comando)

Pré-requisito: Docker. O exemplo avalia o MockTarget pontuado pelo juiz Ollama real — não exige um serviço de RAG externo.

```bash
# 1. Sobe o Ollama e baixa o modelo do juiz (a 1ª vez leva alguns minutos)
docker compose up -d ollama
docker compose exec ollama ollama pull llama3

# 2. Roda a avaliação de exemplo (config + dataset versionados)
docker compose run --rm harness
```

O processo sai com código **0 se o gate passa**, **1 se alguma métrica fica abaixo do limite** em `config/docker.toml` (RF-09) — é isso que o torna usável como portão de regressão no CI.

### Exemplo de saída

```
Evaluation report
=================

Quality (judge metrics):
  faithfulness: mean=0.933 [0.800, 1.000] (95% CI, N=3)
  context_precision: mean=1.000 [1.000, 1.000] (95% CI, N=3)

Cost & latency:
  total tokens: 411
  mean latency: 512.0 ms

Per case:
  rpg-001: 137 tokens, 512.0 ms
  rpg-002: 137 tokens, 512.0 ms
  rpg-003: 137 tokens, 512.0 ms
```

`N` é o número de **casos** sobre os quais o intervalo é calculado (o dataset é a amostra; ver ADR-008). O intervalo é um bootstrap percentílico, limitado a [0,1] por construção. Para apertar o IC, adicione mais casos ao dataset — não mais runs do juiz.

### Rodar no host (Ollama local, sem Docker para o harness)

```bash
pip install -e ".[dev]"
# com um Ollama em localhost:11434 e o modelo llama3 baixado:
gnomon --config config/example.toml
```

### Check determinístico (sem Ollama, sem Docker)

```bash
pip install -e ".[dev]"
python -m pytest -q          # 77 testes: unidade, reprodutibilidade e smoke do gate
```

### Reprodutibilidade (RF-11 / RNF-01)

Mesma seed + mesma config + mesma máquina produzem os mesmos números. Com o juiz determinístico (temperatura 0) e o bootstrap semeado pela seed, o resultado é idêntico entre rodadas. Verificado por teste:

```bash
python -m pytest tests/reproducibility -q
```

## Arquitetura

O núcleo de avaliação depende de interfaces, nunca de implementações concretas. Targets e juiz dependem do núcleo. Detalhes e diagrama em `docs/ARCHITECTURE.md`.

```
Config -> Runner -> [Target adapter] -> RAG alvo (OpenAI-compat ou Mock)
                 -> [Judge] --------> faithfulness + context precision
                 -> [Metrics] ------> média sobre casos + IC (bootstrap)
                 -> [Reporting] ----> relatório máquina + humano (mesma fonte)
                 -> [Gate] ---------> passa/falha no CI (compara ci_low)
```

## Configuração

Toda a configuração vive em arquivos TOML versionados (RNF-07):

- `config/example.toml` — rodar no host com Ollama em `localhost:11434`
- `config/docker.toml` — rodar via `docker compose run --rm harness` (judge aponta para o serviço `ollama` da rede compose)

Os parâmetros (seed, runs do juiz, modelo, limites do gate, target) estão documentados dentro dos próprios arquivos. Configuração inválida — incluindo um limite de gate fora de [0,1] ou seed ausente em modo reproduzível — falha fechado no carregamento, antes de qualquer chamada de modelo.

## Como rodar os testes

```bash
pip install -e ".[dev]"
python -m pytest -q                         # suite completa: 77 testes
python -m pytest tests/unit -q              # só unitários
python -m pytest tests/reproducibility -q   # só reprodutibilidade
python -m pytest tests/gate -q              # só smoke do gate
ruff check src tests && ruff format --check src tests
```

## Decisões de design

As decisões que governam o projeto estão em `docs/adr/`:

- **ADR-001** — target baseado em adapter, para o harness servir a qualquer RAG.
- **ADR-002** — não-determinismo do juiz, com intervalo de confiança em vez de número único.
- **ADR-003** — execução offline-first com Ollama, para o exemplo rodar sem custo.
- **ADR-004** — custo e latência como métricas de primeira classe.
- **ADR-005** — contextos recuperados num campo de extensão OpenAI-compat (fail-closed).
- **ADR-006** — gate compara contra o limite inferior do IC (`ci_low`), não a média.
- **ADR-007** — determinismo do juiz Ollama por `seed+run`, uma chamada por caso.
- **ADR-008** — agregação por caso + IC por bootstrap (honestidade estatística do `n`).

Requisitos completos em `docs/REQUIREMENTS.md`. Visão de produto em `docs/PRODUCT_OVERVIEW.md`. O loop de desenvolvimento do projeto está em `docs/DEVELOPMENT_LOOP.md`.

## O que não faz (ainda)

Answer relevance, context recall, dashboard temporal, comparação multi-target e persistência de histórico ficam para a v2. A arquitetura comporta a adição sem reescrita.

## Contribuindo

Commits seguem Conventional Commits. O gate de CI roda `pytest` e `ruff check` — PRs precisam passar ambos.

## Licença

MIT — veja [LICENSE](LICENSE).
