# ADR-002: Tratamento do não-determinismo do juiz LLM

**Data:** 2026-05-29
**Status:** Aceito (parâmetros de N de runs e granularidade de cache em aberto, ver seção Pontos abertos)

## Contexto

As métricas de qualidade da v1 usam um LLM como juiz. LLM não é determinístico: a mesma entrada produz pontuações diferentes em execuções diferentes, mesmo com temperatura baixa. Reportar um número único de qualidade esconde esse ruído e leva a decisão de deploy em cima de um valor que oscila sem o operador saber.

Esse é o diferencial central do harness. As ferramentas existentes em sua maioria reportam score único. Tratar o não-determinismo de frente, medindo e expondo a variância, é o que separa este harness das alternativas.

A restrição é a tensão entre confiança estatística e custo. Mais execuções do juiz por métrica apertam o intervalo de confiança, mas multiplicam chamadas de modelo, tempo e custo. A decisão precisa equilibrar honestidade estatística com viabilidade de execução, inclusive no caminho offline com Ollama, que é mais lento.

## Decisão

O juiz pontua cada par caso/métrica N vezes. O sistema reporta média com intervalo de confiança calculado sobre essas N pontuações. Nenhuma métrica baseada em juiz sai como número único; a saída sempre carrega média, limite inferior, limite superior e N.

Para sustentar reprodutibilidade dentro desse esquema, o juiz roda sob seed declarada e usa cache. A chave de cache é a tupla de identidade que define unicamente uma pontuação: caso, resposta, modelo de juiz e seed. Entrada cujo a chave não casa com essa tupla é miss, nunca acerto aproximado.

Modo reproduzível exige seed explícita. Execução em modo reproduzível sem seed falha, em vez de gerar seed implícita que quebraria a reprodutibilidade entre rodadas.

## Consequências

**Positivas:**
- O operador vê o ruído do juiz em vez de ignorá-lo, e decide deploy sobre intervalo, não sobre ponto.
- A reprodutibilidade vira invariante verificável: mesma seed e mesmo modelo de juiz produzem o mesmo resultado dentro da variância, testado na suíte de reprodutibilidade.
- O cache corta custo de reexecução quando a entrada não muda.

**Negativas / trade-offs:**
- N execuções por métrica multiplicam custo e tempo. No caminho offline com Ollama, o tempo é o limitante mais sensível.
- Cache por seed significa que mudar a seed invalida o cache inteiro. É correto, mas custa reexecução quando se varia seed deliberadamente.

**Neutras / a observar:**
- O valor de N adequado depende da estabilidade do modelo de juiz escolhido. Modelo mais estável permite N menor para o mesmo aperto de intervalo. Vale medir a variância do juiz default antes de fixar N.

## Pontos abertos

Dois parâmetros desta decisão ficam em aberto e dependem de medição com o modelo de juiz default antes de fixar:

1. **N de runs do juiz por métrica.** Trade-off direto entre aperto do intervalo de confiança e custo de execução. A definição vem de medir a variância do juiz default e escolher o menor N que entregue um intervalo aceitável para decisão de gate.
2. **Granularidade do cache.** A decisão atual define a chave como (caso, resposta, modelo de juiz, seed). Resta confirmar se essa granularidade é a certa ou se vale uma chave mais grossa que compartilhe pontuações entre execuções semelhantes. A mais fina é mais segura contra contaminação; a mais grossa economiza mais. A escolha segura é a fina, e é o default até haver evidência de que o custo justifica afrouxar.

## Alternativas consideradas

| Alternativa | Por que foi descartada |
|---|---|
| Reportar número único de qualidade | Esconde o não-determinismo do juiz; é a falha central das ferramentas existentes que este harness existe para corrigir. |
| Forçar temperatura zero e assumir determinismo | Temperatura zero reduz mas não elimina variância em muitos provedores; assumir determinismo que não existe é mentira estatística. |
| Seed implícita gerada quando ausente | Quebraria reprodutibilidade entre rodadas sem o operador perceber, violando a invariante central. |
