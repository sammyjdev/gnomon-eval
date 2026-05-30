# Loop de desenvolvimento do GNOMON

Como o gnomon-eval evolui, fatia por fatia. Playbook leve: disciplina por
convenção, não por trilho automático. A unidade de trabalho é a **fatia vertical**
(tracer bullet) — um incremento ponta-a-ponta que toca várias camadas e fecha
um conjunto de requisitos da spec.

## O loop

Cada fatia passa por quatro estágios em ordem:

1. **Avaliação** — qual a próxima fatia? Vale agora? Quais RF/RNF/VAL ela fecha?
   - Skills: `superpowers:brainstorming` (escopo), `superpowers:writing-plans` (estratégia).
   - Saída: fatia nomeada + lista de requisitos que satisfaz.
2. **Evolução** — onde encaixa na arquitetura sem violar a direção de
   dependência? Precisa aprofundar algum módulo antes?
   - Skill: `improve-codebase-architecture`.
   - Saída: ponto de encaixe + refactor pré-requisito (se houver).
3. **Validação** — a fatia está correta e honesta?
   - Skills: `superpowers:test-driven-development`,
     `superpowers:verification-before-completion`.
   - Saída: suíte verde com RED→GREEN observado + gates do projeto passando.
4. **Documentação** — o que ficou decidido que não é óbvio no código?
   - Skill: `grill-with-docs`; AXON ao fechar blocos conclusivos.
   - Saída: ADR atualizado/novo + README honesto.

Fechou a Definição de Pronto, volta ao estágio 1 para a fatia seguinte.

## Definição de Pronto (por fatia)

1. RED→GREEN observado para cada peça nova de produção (TDD — Lei de Ferro).
2. `ruff check` e `ruff format --check` limpos.
3. `pytest` verde, incluindo a suíte de reprodutibilidade.
4. As regras inegociáveis tocadas pela fatia verificadas por teste.
5. Decisão não-óbvia → ADR em `docs/adr/`; afirmação nova no README → tem
   comando que a reproduz (RNF-05).

As regras inegociáveis estão no kickoff e nos ADRs: direção de dependência,
honestidade estatística, reprodutibilidade, custo/latência de primeira classe,
offline-first, fail-closed, honestidade documental.

## Sincronização com o AXON (por bloco conclusivo)

O AXON não roda a cada fatia — roda ao fechar um **bloco conclusivo** (um marco
ou fase coesa). Sempre incremental: adiciona documentos novos e alterações,
nunca re-registra em massa o que não mudou.

- `pb index /Users/samdev/dev/gnomon-eval --ctx personal` — reindexa código e
  docs alterados. Depois disso, use `search_code` antes de `read` cego.
- `save_adr(project="gnomon-eval", ...)` para cada decisão **nova** do bloco.
- Captura de memória de sessão do bloco (o PostStop hook do Claude Code roda
  `pb session-save`, se configurado).

## Fora do loop (por ora)

Automação dos estágios (slash-commands, hooks), tracker de issues. Evolução
futura, só se a convenção leve não bastar.
