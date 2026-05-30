# ADR-004: Custo e latência como métricas de primeira classe

**Data:** 2026-05-29
**Status:** Aceito

## Contexto

A decisão real que um operador de RAG enfrenta nunca é "qual configuração responde melhor", e sim "qual responde bem o suficiente pelo custo que cobra". As ferramentas de avaliação existentes reportam qualidade isolada. Uma resposta de qualidade alta que consome muito mais tokens e muito mais tempo aparece como vencedora no relatório, mesmo quando a opção mais barata e mais rápida seria a escolha certa para o caso de uso.

Tratar custo e latência como anexo, fora do relatório de qualidade ou opcional, leva o operador a otimizar qualidade e descobrir o custo só na fatura.

## Decisão

Custo, medido em tokens, e latência, medida em milissegundos, são métricas de primeira classe. O target adapter coleta tokens e latência em toda resposta. O relatório de qualquer execução reporta esses números agregados e por pergunta, no mesmo relatório e ao lado da qualidade, nunca em saída separada e nunca como passo opcional.

## Consequências

**Positivas:**
- O operador decide sobre o trade-off real qualidade contra custo contra latência, numa única visão.
- Comparar duas configurações de RAG passa a expor o custo de cada ponto de qualidade ganho.
- O número de chamadas ao juiz por execução é função explícita do tamanho do dataset e do N de runs, o que torna o custo de rodar o próprio eval previsível.

**Negativas / trade-offs:**
- Exige que todo target adapter reporte tokens e latência. Um target que não exponha contagem de tokens força uma política de tratamento, definida na validação VAL-03, em vez de assumir zero.
- Acopla a coleta de custo ao adapter, que precisa medir latência de forma consistente para os números serem comparáveis entre targets.

**Neutras / a observar:**
- A comparabilidade de latência entre execuções depende de condições de máquina e rede. Vale documentar que latência é comparável dentro de um ambiente, não entre ambientes diferentes.

## Alternativas consideradas

| Alternativa | Por que foi descartada |
|---|---|
| Reportar só qualidade | Esconde o trade-off que é a decisão real do operador; otimizar qualidade às cegas leva a custo descoberto tarde. |
| Custo e latência como relatório separado opcional | Separar as duas dimensões da qualidade faz o operador comparar qualidade sem o custo na mesma visão, que é o erro que esta decisão corrige. |
| Medir custo só em moeda, não em tokens | Preço por token varia por provedor e muda com o tempo; tokens é a unidade estável e convertível, então é a base, com moeda como derivação opcional. |
