# ADR-003: Execução offline-first com Ollama

**Data:** 2026-05-29
**Status:** Aceito

## Contexto

O harness é uma peça de portfólio que precisa vender. O critério que governa isso é que um terceiro clone o repositório e rode a avaliação de exemplo em minutos. Se o exemplo do README exigir uma chave de API paga, uma parte dos avaliadores desiste antes de ver o número, e o portfólio não cumpre a função.

Ao mesmo tempo, o harness precisa servir para uso real, onde o juiz pode ser um modelo de provedor pago mais capaz.

## Decisão

O caminho default documentado no README roda com Ollama via Docker, sem nenhuma credencial paga. O exemplo completo, target e juiz, funciona localmente. O caminho com provedor pago existe atrás de configuração isolada e opcional, selecionável sem editar código.

A execução offline é o primeiro caminho a funcionar, não um modo adicionado depois. O `docker-compose.yml` sobe Ollama e o harness juntos, e a avaliação de exemplo roda com um comando.

## Consequências

**Positivas:**
- Qualquer avaliador roda o exemplo sem custo e sem cadastro em provedor, o que cumpre o critério de portfólio que vende.
- O desenvolvimento sob spec não fica refém de custo de API a cada execução de teste.
- O caminho offline força o harness a não assumir capacidades específicas de um provedor pago.

**Negativas / trade-offs:**
- Modelos locais via Ollama são menos capazes e mais lentos que modelos pagos de ponta. A qualidade do juiz offline é inferior, e o tempo de execução é maior, o que pesa sobre o N de runs de variância.
- O avaliador precisa ter Docker e baixar o modelo na primeira execução, o que adiciona uma etapa de espera inicial.

**Neutras / a observar:**
- A diferença de comportamento entre juiz offline e juiz pago precisa ser visível na documentação para o operador não tratar o número offline como equivalente ao pago.

## Alternativas consideradas

| Alternativa | Por que foi descartada |
|---|---|
| Default em provedor pago | Exigiria credencial para rodar o exemplo, derrubando o critério de portfólio clonável e executável. |
| Fixtures de resposta gravadas como default | Roda em qualquer lugar instantâneo, mas o exemplo deixa de ser "vivo"; o avaliador não vê o sistema executar de verdade, só reproduzir gravação. Mantido como possível modo de teste, não como default. |
| Sem caminho pago | Limitaria o uso real, onde um juiz mais capaz importa. O caminho pago opcional preserva os dois usos. |
