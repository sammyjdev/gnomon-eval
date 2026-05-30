# ADR-008: Unidade de agregação é o caso; IC por bootstrap sobre casos

**Data:** 2026-05-30
**Status:** Aceito (supersede a parte de t-interval + clamp do ADR-006)

## Contexto

Rodar o juiz Ollama real (`temperature=0`) expôs dois problemas na agregação original (Fase 1):

1. **`n` inflado.** O runner empilhava todas as pontuações `casos × runs` num único vetor e calculava um t-interval com `n = casos × runs`. Com o juiz determinístico, as N runs de um caso são **idênticas**. Contar 8 cópias idênticas como 8 observações independentes estreita o IC artificialmente — uma violação direta do RNF-03 (honestidade estatística), a invariante central do projeto. Medição: com 2 casos `[1.0, 0.0]` e 8 runs, o método antigo reportava `[0.225, 0.775]`; a informação real (2 observações) honesta é `[0.0, 1.0]`.
2. **Clamp do t-interval.** Com poucos pontos, o t-interval de uma métrica limitada a [0,1] estoura a faixa (ex.: `[-5.85, 6.85]`) e o ADR-006 o clampava a [0,1]. O clamp esconde o estouro e, perto dos extremos, **mente no limite superior** (deixa o gate afirmar "pode ser 100%" mesmo com falhas observadas).

As duas fontes de variação foram confundidas: ruído do juiz (Q1 — reincidência na mesma cena) e espalhamento entre casos (Q2 — o dataset é uma amostra da população de perguntas). O gate (RF-09) só se importa com Q2.

## Decisão

**Agregação (A): o caso é a unidade amostral.** As N runs de um caso são colapsadas na média (denoise dentro do caso, não amostras independentes). A métrica do dataset agrega sobre os **casos**: `n = número de casos`. Menos de 2 casos não delimita uma população e é rejeitado.

**Intervalo (F2): bootstrap percentílico sobre os casos.** O IC é o percentil (α/2, 1−α/2) das médias de reamostragens dos scores por-caso. Como cada média de reamostragem é média de valores já em [0,1], o intervalo é **limitado por construção — sem clamp**. O bootstrap é **semeado** (`config.seed`) para preservar a reprodutibilidade (RNF-01).

O gate continua comparando `ci_low >= threshold` (ADR-006), agora sobre o `ci_low` do bootstrap.

## Consequências

**Positivas:**
- Honestidade restaurada (RNF-03): o `n` reflete observações reais (casos); runs idênticas não fabricam confiança.
- Sem clamp e sem limite-superior-mentiroso: o intervalo nasce dentro de [0,1].
- Reprodutibilidade trivial e perfeita com juiz determinístico (`temperature=0`), via seed do bootstrap.
- Method-agnostic quanto ao nível de confiança: o bootstrap aceita qualquer `confidence_level` em (0,1), sem tabela t.

**Negativas / trade-offs:**
- Com poucos casos o IC é largo (correto, mas pode frustrar). O lever de IC estreito é **mais casos** no dataset (RF-01), não mais runs.
- O bootstrap é mais caro que uma fórmula fechada (2000 reamostragens), porém desprezível frente a uma chamada de modelo.
- N de runs vira útil só com juiz ruidoso (`temperature>0`); com `temperature=0` é redundante. O piso `judge_runs>=2` (VAL-04) foi mantido por ora; relaxar para 1 é follow-up.

**Neutras / a observar:**
- `MetricResult.n` muda de semântica: era runs, agora é casos.

## Alternativas consideradas

| Alternativa | Por que foi descartada |
|---|---|
| Manter pooling `casos × runs` com t-interval | Infla o `n` com cópias determinísticas e estreita o IC artificialmente (viola RNF-03). |
| Manter t-interval + clamp ao range | O clamp mente no limite superior perto dos extremos (afirma 100% com falhas observadas). |
| Wilson/Jeffreys (F1, binário) | Exigiria binarizar o score do juiz (✓/✗), perdendo a gradação 0–1; é uma mudança de produto. Reservado caso se queira robustez extra contra juiz fraco. |
| Variância do juiz com `temperature>0` (medir Q1) | Mede a pergunta menos útil para o gate; nossa medição mostrou variância ≈0 mesmo a temp=0.8 em casos claros, e temp>0 complica a reprodutibilidade. |
| Modelo hierárquico (2 níveis, Q1+Q2) | Estatisticamente mais completo, mas com juiz determinístico colapsa exatamente no bootstrap sobre casos; custo de implementação não se justifica na v1. |
