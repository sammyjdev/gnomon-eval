# Design — Loop de desenvolvimento do gnomon-eval

**Data:** 2026-05-29
**Status:** Aprovado (brainstorming), aguardando plano de implementação
**Autor:** Sam + Claude

## Propósito

Estabelecer uma lógica repetível para **avaliar, evoluir, validar e documentar**
cada incremento do gnomon-eval, da Fase 1 → v1 → v2. Serve a dois objetivos
declarados: organização do trabalho e qualidade de portfólio. O projeto é
desenvolvido sob spec; este loop é o método que mantém a spec, o código, os
testes e os ADRs em sincronia enquanto o projeto cresce.

## Escopo e decisões de design

Quatro decisões fixadas no brainstorming governam este design:

1. **Camada: processo, não produto.** Isto é metodologia de trabalho ancorada
   nas skills disponíveis, não código dentro de `src/gnomon/`. Nenhum módulo
   novo no harness sai deste documento.
2. **Unidade de trabalho: fatia vertical (tracer bullet).** Cada ciclo entrega
   uma fatia ponta-a-ponta que toca várias camadas e fecha um conjunto de
   requisitos da spec — a mesma lógica que a Fase 1 já provou. Não se trabalha
   por requisito isolado (granular demais, fatias que não fecham) nem por
   componente arquitetural (esconde o fluxo ponta-a-ponta).
3. **Enforcement: playbook leve.** Disciplina por convenção, não por trilho
   automático. Sem gates de CI dedicados ao loop, sem git hooks novos, sem
   tracker de issues. O documento é seguido à mão. Se a convenção não bastar,
   automatizar é evolução futura, registrada como tal.
4. **Contexto AXON: `personal`.** O projeto entra no vault sob ctx `personal`.

## O loop de 4 estágios

Cada fatia vertical passa pelos quatro estágios em ordem. Cada estágio tem uma
skill âncora e uma saída concreta que destrava o próximo.

| Estágio | Pergunta que responde | Skill âncora | Saída |
|---|---|---|---|
| **1. Avaliação** | Qual a próxima fatia? Vale construir agora? Quais RF/RNF/VAL ela fecha? | `superpowers:brainstorming` (escopo) + `Plan` (estratégia) | Fatia nomeada + lista dos requisitos que ela satisfaz |
| **2. Evolução** | Onde encaixa na arquitetura sem violar a direção de dependência? Precisa aprofundar algum módulo antes? | `improve-codebase-architecture` | Ponto de encaixe + refactor pré-requisito (se houver) |
| **3. Validação** | A fatia está correta e honesta? | `superpowers:test-driven-development` + `superpowers:verification-before-completion` | Suíte verde com RED→GREEN observado + gates do projeto passando |
| **4. Documentação** | O que ficou decidido que não é óbvio no código? | `grill-with-docs` + AXON (`save_adr`, `pb index`) | ADR atualizado/novo + README honesto + decisão e código no vault |

O loop fecha quando a fatia passa na Definição de Pronto e retorna ao estágio 1
para a fatia seguinte.

## Definição de Pronto de uma fatia

O gate do estágio de Validação **reusa as regras inegociáveis já existentes** do
projeto; não cria critério novo. Uma fatia está pronta quando:

1. RED→GREEN foi observado para cada peça nova de produção (TDD — Lei de Ferro).
2. `ruff check` e `ruff format --check` passam limpos.
3. `pytest` está verde, incluindo a suíte de reprodutibilidade.
4. As regras inegociáveis tocadas pela fatia estão verificadas por teste
   (direção de dependência, honestidade estatística, reprodutibilidade,
   custo/latência de primeira classe, fail-closed, offline-first, honestidade
   documental — conforme a fatia toca cada uma).
5. Houve decisão não-óbvia → ADR atualizado/criado; afirmação nova no README →
   tem comando que a reproduz (RNF-05).
6. Documentação no AXON feita (estágio 4): decisão via `save_adr`, código
   reindexado, sessão capturada.

## Integração AXON

O AXON é onde o estágio de Documentação ganha permanência e busca semântica.

**Recorrente, a cada fatia (estágio 4):**
- `save_adr(project="gnomon-eval", ...)` para cada decisão de design relevante →
  vira ADR pesquisável no vault e alimenta `get_adrs`.
- `pb index /Users/samdev/dev/gnomon-eval --ctx personal` após a fatia → o
  `search_code` passa a enxergar o código novo, substituindo `read` cego (regra
  de ouro do AXON.md).
- Captura de memória de sessão ao fim → `get_session_memory` retoma o contexto
  entre sessões.

**Onboarding único (executado uma vez, junto desta entrega):**
1. `git init` + commit inicial da Fase 1. *(Feito.)*
2. `pb scan ~/dev` (atualiza o manifesto de projetos) +
   `pb index /Users/samdev/dev/gnomon-eval --ctx personal` (indexa o código).
3. Registrar via `save_adr`, sob `project="gnomon-eval"`:
   - Os 4 ADRs existentes (0001 adapter, 0002 não-determinismo, 0003
     offline-first, 0004 custo/latência), para que vivam no vault além dos
     arquivos markdown.
   - Os dois pontos abertos do ADR-002 (N de runs, granularidade de cache).
   - As três decisões novas tomadas na Fase 1:
     - **Clamp do IC a [0,1]** para métricas limitadas (média crua, intervalo
       clampado).
     - **Recomendação N=8 condicional**: piso de computabilidade é 2, mas N=2 é
       inútil para gate (t crítico 12.7); cotovelo em N≈8–10 para σ≈0.046 do
       stub; número final depende de medir a variância do juiz Ollama real.
     - **Nome `gnomon`** (pacote importável) vs `rag_eval` dos docs — divergência
       a reconciliar.
4. Capturar memória de sessão da Fase 1.

## Artefato e localização

Entregável A: `docs/DEVELOPMENT_LOOP.md` — o playbook operacional, derivado
deste design, em português, na voz de "como trabalhamos neste repo". Mais enxuto
que este design (que registra o *porquê* das escolhas); o playbook registra o
*como* do dia a dia.

Entregável B: o onboarding AXON acima, executado.

## Fora de escopo

- Comandos/slash-commands ou git hooks que automatizem os estágios do loop
  (contra a escolha "playbook leve"; evolução futura se a convenção falhar).
- Tracker de issues para as fatias (`to-issues`); as fatias são acompanhadas no
  próprio playbook e nos commits.
- Qualquer mudança no código de `src/gnomon/` — este é trabalho de processo.
- Decidir os parâmetros abertos do ADR-002 sem medição real do juiz Ollama.

## Riscos e mitigações

- **Convenção ignorada sob pressa.** Playbook leve não trava nada. Mitigação: a
  Definição de Pronto reusa gates que já são barreira de release (ruff, pytest),
  então a parte crítica da validação continua dura mesmo sem trilho de processo.
- **AXON desatualizado em relação ao código.** Se `pb index` não rodar ao fim da
  fatia, `search_code` mente. Mitigação: indexação é item explícito da Definição
  de Pronto (passo 6).
- **Divergência de nome (`gnomon` vs `rag_eval`).** Registrada como decisão a
  reconciliar; não bloqueia o loop, mas precisa virar ADR resolvido antes da v1.
