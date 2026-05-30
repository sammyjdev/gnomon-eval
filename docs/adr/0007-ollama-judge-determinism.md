# ADR-007: Determinismo do juiz Ollama por seed+run

**Data:** 2026-05-30
**Status:** Aceito

## Contexto

RNF-01 é reprodutibilidade dentro da variância medida, não bit-exact. O juiz Ollama precisa de uma sequência determinística por seed declarada para que duas execuções com o mesmo seed produzam resultados comparáveis. Sem fixar seed e temperatura, o juiz introduz variância não controlada que se confunde com variância real do RAG avaliado.

## Decisão

O juiz fixa `options.seed = seed + run` e `temperature = 0.0` por chamada. Isso produz uma sequência fixa para um mesmo modelo e host. A suíte de reprodutibilidade continua usando o StubJudge (determinístico puro); a reprodutibilidade do juiz real é verificada como tolerância de variância, não igualdade de valores. O cache (cuja chave inclui seed e run) reforça a estabilidade dentro de uma mesma máquina.

## Consequências

**Positivas:**
- Sequência determinística por seed declarada: repetir uma execução com o mesmo seed produz o mesmo resultado dentro do mesmo modelo e host.
- O cache, ao incluir seed e run na chave, evita recálculo e reforça consistência em reruns parciais.
- A separação entre StubJudge (testes) e juiz real (produção) mantém os testes rápidos e independentes de Ollama.

**Negativas / trade-offs:**
- Trocar de modelo ou de host pode mudar os números — esperado e reportado via IC. A reprodutibilidade é garantida dentro de um ambiente, não entre ambientes.
- `temperature = 0.0` em Ollama não é garantia absoluta de determinismo em todos os backends de inferência; o seed é o mecanismo primário.

**Neutras / a observar:**
- A combinação `seed + run` (não só `seed`) é intencional: cada run dentro de uma execução recebe uma semente diferente, o que evita que todas as runs de uma pergunta sejam idênticas entre si, preservando a medição de variância.

## Alternativas consideradas

| Alternativa | Por que foi descartada |
|---|---|
| Seed fixo igual para todos os runs | Todas as runs de uma pergunta seriam idênticas; a variância medida seria zero e o IC seria inútil. |
| Não fixar seed nem temperatura | Introduz variância não controlada no juiz, que se confunde com variância do RAG e infla o IC sem valor real. |
| Verificar reprodutibilidade por igualdade bit-exact | Incompatível com RNF-01 e com a realidade de modelos quantizados em hardware variado; a tolerância de variância é a métrica correta. |
