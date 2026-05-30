# ADR-001: Target RAG baseado em adapter

**Data:** 2026-05-29
**Status:** Aceito

## Contexto

O harness precisa de um RAG para avaliar, e o alvo de exemplo é o RPG Master AI. O RPG Master ainda está longe da versão final e vai mudar bastante por dentro. Se o harness acoplar na implementação atual dele, cada mudança no RPG Master quebra o exemplo do harness, e o exemplo é o que faz o portfólio vender. Além disso, um harness que só avalia um RAG específico não tem valor para nenhum cliente que tenha o próprio RAG.

A restrição real é dupla: o exemplo precisa sobreviver à evolução do RPG Master, e o harness precisa servir para qualquer RAG, não só o de exemplo.

## Decisão

Definimos o target por uma interface de domínio, `RagTarget`, e acessamos qualquer RAG concreto através de um adapter que implementa essa interface. O primeiro adapter concreto fala protocolo OpenAI-compat por REST, que é o protocolo que o RPG Master já expõe. O harness depende da interface, nunca de internals do RAG.

Trocar o RAG avaliado é trocar configuração e, no máximo, escolher outro adapter. Não exige tocar no núcleo de avaliação.

## Consequências

**Positivas:**
- O RPG Master evolui por dentro sem quebrar o harness enquanto mantém o contrato REST.
- O harness avalia qualquer RAG que fale OpenAI-compat, o que o torna vendável para cliente com RAG próprio.
- A direção de dependência fica explícita e verificável: implementações dependem do domínio, não o contrário.

**Negativas / trade-offs:**
- Um RAG que não fale OpenAI-compat exige escrever um novo adapter. O custo é isolado no adapter, mas existe.
- A interface esconde capacidades específicas de um target. Recurso peculiar de um RAG não aparece pela interface genérica sem extensão deliberada.

**Neutras / a observar:**
- A qualidade da abstração só se prova quando o segundo adapter for escrito. Se o segundo adapter forçar mudança na interface, a abstração estava errada e revisamos aqui.

## Alternativas consideradas

| Alternativa | Por que foi descartada |
|---|---|
| Acoplar direto no RPG Master AI | Cada mudança no RPG Master quebraria o harness, e o harness não serviria para nenhum outro RAG. |
| Suportar só um protocolo fixo sem camada de adapter | Tornaria impossível avaliar RAGs com protocolos diferentes sem reescrever o núcleo. |
