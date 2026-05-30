# ADR-005: Contextos recuperados num campo de extensão OpenAI-compat

**Data:** 2026-05-30
**Status:** Aceito

## Contexto

O protocolo OpenAI chat/completions não tem campo padrão para os contextos recuperados por um RAG. RF-03 exige que o eval colete os contextos junto da resposta para calcular métricas de fidelidade e relevância. Sem um campo explícito para os contextos, o adapter não tem como separar o que é resposta gerada do que é material recuperado.

## Decisão

O adapter OpenAI-compat lê os contextos de um campo de extensão JSON top-level de nome configurável (`contexts_field`, default `"contexts"`). Ausência do campo não é tratada como lista vazia — resulta em `IncompleteResponseError` (VAL-03). Nunca lista vazia silenciosa.

## Consequências

**Positivas:**
- A política fail-closed mantém a métrica honesta: nenhum resultado sem contexto é contabilizado como avaliação válida.
- O nome do campo é configurável, o que permite adaptar a targets que já usam outro nome sem alterar o adapter central.
- A semântica é explícita: o operador sabe que o target precisa devolver contextos nesse campo.

**Negativas / trade-offs:**
- O RAG alvo precisa devolver contextos nesse campo de extensão. Targets que não o fazem exigem um adapter próprio ou modificação na resposta do servidor.
- Não há fallback automático: se o campo estiver ausente, a execução falha com erro, não com degradação silenciosa.

**Neutras / a observar:**
- Targets que devolvem os contextos embutidos no texto da resposta ou em campos aninhados precisam de adapter dedicado — esse adapter assume campo de extensão top-level.

## Alternativas consideradas

| Alternativa | Por que foi descartada |
|---|---|
| Lista vazia quando o campo estiver ausente | Produziria métricas de fidelidade calculadas sobre contexto vazio, que são inúteis ou enganosas; a honestidade da métrica exige falha explícita. |
| Campo fixo não configurável | Targets existentes usam nomes variados; configurabilidade evita forçar mudança no servidor alvo. |
| Extrair contextos do texto da resposta por heurística | Frágil e não generalizável; dependeria do formato de saída de cada modelo. |
