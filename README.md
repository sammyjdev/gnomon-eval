# GNOMON

> Avalia um pipeline RAG e reporta qualidade com o intervalo de confiança junto, mais custo e latência, rodando offline com Ollama.

## Pré-requisitos

- Python 3.11+
- Docker 24+
- Ollama (sobe via docker-compose; nenhuma chave de API paga no caminho default)

## Setup local

```bash
git clone [TODO: url do repositório]
cd gnomon-eval
docker compose up -d        # sobe Ollama e baixa o modelo na primeira execução
[TODO: comando único de avaliação de exemplo, ex: make eval-example]
```

A primeira execução baixa o modelo do Ollama, o que leva alguns minutos. As seguintes usam o modelo já em cache.

## O que isto faz

Lê um dataset de casos de avaliação, roda cada caso contra um RAG alvo, pontua as respostas com um juiz LLM e reporta faithfulness e context precision, cada uma com intervalo de confiança, junto de custo em tokens e latência em milissegundos. O mesmo eval roda como teste de regressão no CI e falha o build quando uma métrica cai abaixo de um limite configurável.

O exemplo avalia o RPG Master AI através da API REST OpenAI-compat que ele expõe. Trocar para outro RAG que fale o mesmo protocolo é mudar configuração.

## Arquitetura

O núcleo de avaliação depende de interfaces, nunca de implementações concretas. Targets e juiz dependem do núcleo. Detalhes e diagrama em `docs/ARCHITECTURE.md`.

```
Config -> Runner -> [Target adapter] -> RAG alvo
                 -> [Judge] --------> métricas com intervalo de confiança
                 -> [Metrics] ------> custo e latência
                 -> [Reporting] ----> relatório máquina + humano
                 -> [Gate] ---------> passa/falha no CI
```

## Variáveis de ambiente

| Variável | Obrigatório | Descrição | Exemplo |
|---|---|---|---|
| `TARGET_BASE_URL` | sim | Endpoint OpenAI-compat do RAG alvo | `http://localhost:8080/v1` |
| `JUDGE_MODEL` | sim | Modelo de juiz (default offline via Ollama) | `[TODO: modelo default]` |
| `JUDGE_SEED` | sim em modo reproduzível | Seed do juiz; ausência em modo reproduzível falha | `42` |
| `JUDGE_RUNS` | sim | N de execuções do juiz por métrica para o intervalo de confiança | `[TODO: N default, ver ADR-002]` |
| `DATASET_PATH` | sim | Caminho do dataset de avaliação versionado | `datasets/rpg_master_example` |
| `GATE_THRESHOLDS` | não | Limites por métrica para o gate de regressão | `faithfulness=0.80,context_precision=0.75` |

## Como rodar os testes

```bash
[TODO: comando de unit tests, ex: pytest tests/unit]
[TODO: comando de integração, ex: pytest tests/integration]
[TODO: comando de reprodutibilidade, ex: pytest tests/reproducibility]
```

Os testes de reprodutibilidade verificam que a mesma seed produz o mesmo resultado dentro da variância reportada. Essa é a verificação executável da invariante central do projeto.

## Decisões de design

As decisões que governam o projeto estão em `docs/adr/`:

- ADR-001 — target baseado em adapter, para o harness servir a qualquer RAG e sobreviver à evolução do RPG Master AI.
- ADR-002 — tratamento do não-determinismo do juiz, com intervalo de confiança em vez de número único.
- ADR-003 — execução offline-first com Ollama, para o exemplo rodar sem custo.
- ADR-004 — custo e latência como métricas de primeira classe, ao lado da qualidade.

Requisitos completos em `docs/REQUIREMENTS.md`. Visão de produto em `docs/PRODUCT_OVERVIEW.md`.

## O que não faz (ainda)

Answer relevance, context recall, dashboard temporal, comparação multi-target e persistência de histórico ficam para a v2. A arquitetura comporta a adição sem reescrita.

## Contribuindo

[TODO: padrão de commit, fluxo de PR, gate de lint e testes como barreira de merge]

## Licença

[TODO: definir]
```
