# ADR-006: Gate compara contra o limite inferior do IC

**Data:** 2026-05-30
**Status:** Aceito

## Contexto

RF-09 falha o gate quando uma métrica cai abaixo de um limite definido. Toda métrica gerada pelo eval é uma média com intervalo de confiança (RNF-03). Gatear pela média pontual deixaria passar resultados cuja incerteza ainda cruza o limite — ou seja, um resultado que é estatisticamente indistinguível de uma falha seria reportado como aprovado.

## Decisão

O gate passa só se `ci_low >= threshold`. O limite inferior do intervalo de confiança precisa estar acima (ou igual) ao threshold para o gate aprovar. Métrica com threshold definido mas ausente do relatório é tratada como falha, não como passe silencioso.

## Consequências

**Positivas:**
- Honestidade estatística preservada no portão: um resultado ambíguo (IC que cruza o threshold) não passa.
- Métrica ausente é falha explícita, o que impede configurações incompletas de passar despercebidas.

**Negativas / trade-offs:**
- Gate mais rígido com N pequeno, porque o IC é mais largo. Com poucos runs, métricas reais acima do threshold podem falhar o gate por incerteza alta.
- Mitiga-se subindo N (ver ADR-002, ponto aberto do N de runs). O operador precisa entender que aumentar N reduz a largura do IC e, portanto, a rigidez do gate.

**Neutras / a observar:**
- A escolha de `ci_low` como critério é conservadora por design. Operadores que aceitam risco maior podem definir thresholds mais baixos, mas o critério de comparação permanece `ci_low`.

## Alternativas consideradas

| Alternativa | Por que foi descartada |
|---|---|
| Comparar pela média pontual | Deixaria passar resultados estatisticamente ambíguos; uma métrica de 0.70 ± 0.05 com threshold 0.68 passaria, mesmo que o IC cruze o limite. |
| Comparar pelo ponto médio do IC | Equivalente à média; não captura a incerteza do lado baixo. |
| Passe silencioso para métrica ausente | Permite que configurações incompletas ou erros no pipeline de coleta passem no gate sem sinalizar o problema. |
