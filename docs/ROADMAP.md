# GNOMON — Roadmap v2

> **Status: rascunho, não comprometido.** Este documento é um backlog de candidatos para depois da v1, com dependências e um sequenciamento **proposto** (ajustável). Não é um plano executável: quando uma onda for escolhida, ela vira um plano via `superpowers:writing-plans`, seguindo `docs/DEVELOPMENT_LOOP.md`.

A v1 (entregue) está em `docs/REQUIREMENTS.md`. A seção "Fora de escopo da v1" lista o que foi deliberadamente adiado; este roadmap detalha esses itens e soma as dívidas descobertas ao validar o caminho real (juiz Ollama).

## Invariantes que a v2 herda (não-negociáveis)

Todo item abaixo precisa preservar:

- **Honestidade estatística** (RNF-03) — nenhuma métrica de juiz sem incerteza; nada de inflar `n` (ver ADR-008).
- **Direção de dependência** (RNF-02) — núcleo depende de contratos, não de implementações.
- **Offline-first** (RF-10) e **reprodutibilidade** (RNF-01).
- **Custo e latência de primeira classe** (ADR-004), **fail-closed** e **honestidade documental** (RNF-05).

## Habilitador transversal: usar o ground truth

`EvalCase` já carrega `expected_answer` e `expected_contexts`, mas o juiz da v1 **os ignora** — ele pontua a resposta contra os contextos *recuperados* (faithfulness) e a relevância dos contextos à pergunta (context precision). Métricas novas que comparam com a verdade de referência (context recall, answer relevance com referência) **dependem** de o pipeline passar esse ground truth ao juiz/métrica.

→ É a primeira peça estrutural da v2: expor `expected_*` ao juiz e às métricas, sem violar a direção de dependência.

## Backlog A — features adiadas da v1

| # | Item | O quê / por quê | Toca | Depende de |
|---|------|-----------------|------|------------|
| A1 | **Answer relevance** | Métrica: a resposta responde à pergunta (independente de estar ancorada)? Pode ser com referência (`expected_answer`) ou sem. | juiz (prompt), métricas, V1_METRICS→V2_METRICS | habilitador (se com referência) |
| A2 | **Context recall** | Métrica: a recuperação trouxe **todos** os contextos necessários? Compara contextos recuperados vs `expected_contexts`. | juiz/métrica, dataset | **habilitador** (ground truth) |
| A3 | **Persistência de histórico** | Guardar resultados de execuções ao longo do tempo (arquivo: sqlite/jsonl). | nova camada de store | — |
| A4 | **Dashboard temporal** | Acompanhar métricas por execução/tempo. | reporting/CLI, store | **A3** |
| A5 | **Comparação multi-target** | Rodar N targets e produzir relatório comparativo lado a lado. | runner, reporting, config | (talvez A3) |

## Backlog B — dívidas e itens descobertos na v1

| # | Item | Origem | Toca |
|---|------|--------|------|
| B1 | **`judge_runs=1` para juiz determinístico** | ADR-002/008: com `temperature=0` as runs são cópias; piso `>=2` (VAL-04) é desperdício. | `config.py`, testes |
| B2 | **Método de IC plugável** | ADR-008 alternativas: Wilson/Jeffreys (juiz binário, F1) e hierárquico (juiz ruidoso, C) além do bootstrap atual. | `confidence.py`, config |
| B3 | **Cache de juiz persistente (disco)** | ADR-002 (ponto de cache): hoje é em memória, perde-se entre processos; persistir economiza e reforça reprodutibilidade cross-process. | `judge/cache.py`, config |
| B4 | **Barra de capacidade do juiz / repair** | Caminho real: `phi3:mini` emitiu chave inválida (`faithlessness`) → fail-closed correto, mas a run inteira falha. Validar/calibrar o juiz, ou re-prompt/repair com K tentativas. | juiz, talvez nova etapa de calibração |
| B5 | **Custo em moeda + provedor pago** | ADR-004 / RF-10: hoje só tokens; um caminho pago isolado e a conversão tokens→custo. | métricas, config, target/judge |
| B6 | **Fixtures gravadas / MockTarget por pergunta** | O MockTarget devolve uma resposta fixa; demos e golden tests ganhariam respostas por pergunta (gravadas de um RAG real). | `targets/`, datasets |
| B7 | **Mais adapters de target** | Além de OpenAI-compat, conforme a necessidade de RAGs reais. | `targets/` |

## Dependências (resumo)

```
habilitador (ground truth) ──> A2 (context recall)
                           └─> A1 (answer relevance com referência)
A3 (persistência) ──> A4 (dashboard)
                  └─> A5 (multi-target, opcional)
```

B1, B2, B3, B5, B6, B7 são independentes entre si e do resto (podem entrar a qualquer momento).

## Sequenciamento proposto (PROPOSTA — ajuste à vontade)

- **Onda 1 — fundações baratas:** habilitador (ground truth), B1 (`judge_runs=1`), B3 (cache persistente), B4 (barra do juiz). Tudo de baixo risco, destrava as métricas novas e fecha pontas soltas da v1.
- **Onda 2 — métricas novas:** A2 (context recall) e A1 (answer relevance). É o coração de valor da v2.
- **Onda 3 — escala e observabilidade:** A3 (persistência) → A4 (dashboard) → A5 (multi-target).
- **Quando surgir necessidade:** B2 (IC plugável) se um juiz ruidoso ou binário entrar; B5/B6/B7 conforme casos reais aparecerem.

## Perguntas em aberto (decidir ao abrir a v2)

1. O foco da v2 é **métricas novas** (Onda 2) ou **escala/observabilidade** (Onda 3) primeiro?
2. Answer relevance (A1): **com** referência (usa `expected_answer`) ou **sem** (só pergunta↔resposta)?
3. Persistência (A3): arquivo local (sqlite/jsonl versionável) ou serviço? O offline-first puxa para arquivo local.
4. A barra do juiz (B4): validação one-shot na configuração, ou repair/retry por chamada? (retry com juiz determinístico exige variar seed/prompt).

## Como isto vira plano executável

Escolhida uma onda (ou fatia dela), rodar `superpowers:writing-plans` para produzir o plano task-by-task, e executar via `superpowers:subagent-driven-development` — o mesmo loop que entregou a v1. Decisões não-óbvias viram ADRs em `docs/adr/` (próximo número livre: ADR-009).
