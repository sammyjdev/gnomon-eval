# Loop de Desenvolvimento + Onboarding AXON — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar o playbook do loop de desenvolvimento (`docs/DEVELOPMENT_LOOP.md`), alinhar a identidade do projeto para GNOMON nos docs, e fazer o onboarding do projeto no AXON (índice + ADRs novos + memória de sessão).

**Architecture:** Trabalho de processo e documentação, não código de produto. Nenhuma mudança em `src/gnomon/`. Três blocos independentes: (1) reconciliação de nome, (2) playbook, (3) onboarding AXON. A ordem importa: o nome é alinhado antes de indexar para o vault não capturar `rag_eval`.

**Tech Stack:** Markdown, git, AXON (`pb` CLI + ferramentas MCP `mcp__axon__*`).

**Nota sobre TDD:** Estas tarefas produzem docs e efeitos de operação (índice, ADRs no vault), não código executável. A Lei de Ferro do TDD não se aplica; cada tarefa usa **verificação explícita** (grep, saída de comando, `get_adrs`/`search_code`) no lugar do ciclo red-green.

---

## Mapa de arquivos

- Modify: `docs/ARCHITECTURE.md` — linhas 1, 83, 102 (título + árvore de pastas)
- Modify: `docs/REQUIREMENTS.md` — linha 1 (título)
- Modify: `docs/PRODUCT_OVERVIEW.md` — linha 1 (título)
- Modify: `README.md` — linhas 1, 15 (título + path do clone)
- Create: `docs/DEVELOPMENT_LOOP.md` — o playbook operacional do loop
- Efeitos AXON (sem arquivo no repo): índice no Qdrant, ADRs no store, memória de sessão

---

## Task 1: Reconciliar identidade para GNOMON nos docs

Resolve a decisão 6 do design. Mudanças cirúrgicas: só identificadores (path de pacote, path de repo, path de clone) e títulos H1. A prosa que descreve a categoria ("harness de avaliação RAG") fica intacta.

**Files:**
- Modify: `docs/ARCHITECTURE.md:1,83,102`
- Modify: `docs/REQUIREMENTS.md:1`
- Modify: `docs/PRODUCT_OVERVIEW.md:1`
- Modify: `README.md:1,15`

- [ ] **Step 1: Corrigir a árvore de pastas e identificadores em ARCHITECTURE.md**

Em `docs/ARCHITECTURE.md`, trocar a raiz da árvore (linha ~83) de:

```
rag-eval-harness/
```

para:

```
gnomon-eval/
```

E o pacote src (linha ~102) de:

```
│   └── rag_eval/             # modelos e interfaces, sem dependência de infra
```

para:

```
│   └── gnomon/               # modelos e interfaces, sem dependência de infra
```

- [ ] **Step 2: Alinhar os títulos H1 para GNOMON**

Trocar a linha 1 de cada arquivo:

- `docs/ARCHITECTURE.md`: `# RAG Eval Harness — Arquitetura` → `# GNOMON — Arquitetura`
- `docs/REQUIREMENTS.md`: `# RAG Eval Harness — Requisitos` → `# GNOMON — Requisitos`
- `docs/PRODUCT_OVERVIEW.md`: `# RAG Eval Harness` → `# GNOMON`
- `README.md`: `# RAG Eval Harness` → `# GNOMON`

- [ ] **Step 3: Corrigir o path do clone no README**

Em `README.md` (linha ~15), trocar:

```bash
cd rag-eval-harness
```

para:

```bash
cd gnomon-eval
```

- [ ] **Step 4: Verificar zero ocorrências de identificador antigo (fora do spec)**

Run:
```bash
grep -rn -e 'rag_eval' -e 'rag-eval-harness' docs README.md | grep -v 'superpowers/specs'
```
Expected: nenhuma saída (exit 1). As únicas ocorrências restantes vivem no design doc em `docs/superpowers/specs/`, que discute a própria divergência e deve mantê-las.

- [ ] **Step 5: Commit**

```bash
git add docs/ARCHITECTURE.md docs/REQUIREMENTS.md docs/PRODUCT_OVERVIEW.md README.md
git commit -m "docs: alinhar identidade do projeto para GNOMON / gnomon-eval

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Escrever o playbook docs/DEVELOPMENT_LOOP.md

O artefato operacional A: o "como trabalhamos neste repo", derivado do design. Mais enxuto que o design (que registra o porquê).

**Files:**
- Create: `docs/DEVELOPMENT_LOOP.md`

- [ ] **Step 1: Criar o playbook com o conteúdo completo**

Criar `docs/DEVELOPMENT_LOOP.md` com exatamente:

```markdown
# Loop de desenvolvimento do GNOMON

Como o gnomon-eval evolui, fatia por fatia. Playbook leve: disciplina por
convenção, não por trilho automático. A unidade de trabalho é a **fatia
vertical** (tracer bullet) — um incremento ponta-a-ponta que toca várias
camadas e fecha um conjunto de requisitos da spec.

## O loop

Cada fatia passa por quatro estágios em ordem:

1. **Avaliação** — qual a próxima fatia? Vale agora? Quais RF/RNF/VAL ela fecha?
   - Skills: `superpowers:brainstorming` (escopo), `Plan` (estratégia).
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

- `pb index <repo-root> --ctx personal` — reindexa código e
  docs alterados. Depois disso, use `search_code` antes de `read` cego.
- `save_adr(project="gnomon-eval", ...)` para cada decisão **nova** do bloco.
- Captura de memória de sessão do bloco (o PostStop hook do Claude Code já roda
  `pb session-save`).

## Fora do loop (por ora)

Automação dos estágios (slash-commands, hooks), tracker de issues. Evolução
futura, só se a convenção leve não bastar.
```

- [ ] **Step 2: Verificar que o playbook bate com o design**

Run:
```bash
test -f docs/DEVELOPMENT_LOOP.md && grep -q 'bloco conclusivo' docs/DEVELOPMENT_LOOP.md && grep -q 'fatia vertical' docs/DEVELOPMENT_LOOP.md && echo OK
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add docs/DEVELOPMENT_LOOP.md
git commit -m "docs: playbook do loop de desenvolvimento

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Onboarding AXON (bloco conclusivo 0)

Indexa o projeto no vault (ctx personal), registra as decisões novas como ADRs no AXON, e captura a memória da Fase 1. As mudanças de nome (Task 1) e o playbook (Task 2) já estão commitados antes deste passo, então o índice captura a identidade GNOMON correta.

**Files:**
- Efeitos AXON (sem arquivo versionado no repo)

- [ ] **Step 1: Atualizar o manifesto de projetos e indexar**

Run:
```bash
pb scan ~/dev --depth 2
pb index <repo-root> --ctx personal
```
Expected: `scan` lista `gnomon-eval` entre os repos descobertos; `index` reporta arquivos indexados sem erro.

- [ ] **Step 2: Verificar que o código entrou no vault**

Usar a ferramenta MCP `mcp__axon__search_code`:
```
search_code(query="aggregate_metric confidence interval t-interval", ctx="personal")
```
Expected: retorna nós de `src/gnomon/metrics/confidence.py` (a função `aggregate_metric`). Se voltar vazio, a indexação falhou — investigar antes de seguir.

- [ ] **Step 3: Registrar a decisão dos pontos abertos do ADR-002 (N de runs)**

Usar `mcp__axon__save_adr`:
```
save_adr(
  project="gnomon-eval",
  title="ADR-002 ponto aberto: N de runs do juiz por métrica",
  context="As métricas usam um juiz LLM não-determinístico. O IC depende de N runs; mais N aperta o IC mas multiplica custo/tempo, crítico no Ollama offline.",
  decision="Piso de computabilidade é N=2. N=2 é inútil para gate (t crítico 12.7 → IC largo demais). Recomendação provisória: começar com N=8 e re-medir com o juiz Ollama real; N final = menor N cujo meia-largura de IC < metade do menor espaçamento de threshold.",
  rationale="Medição na fatia da Fase 1 (StubJudge, σ≈0.046): meia-largura cai de 0.21 (N=2) para ~0.036 (N=8) e ~0.029 (N=10); cotovelo em N≈8-10. O número real exige medir a variância do Ollama, ainda não feito."
)
```
Expected: retorna um id de ADR.

- [ ] **Step 4: Registrar a decisão de granularidade de cache (ADR-002)**

```
save_adr(
  project="gnomon-eval",
  title="ADR-002 ponto aberto: granularidade do cache do juiz",
  context="O juiz usa cache para reprodutibilidade. A granularidade da chave decide o trade-off contaminação vs economia.",
  decision="Chave fina (caso, resposta, modelo de juiz, seed) é o default. Só afrouxar para chave mais grossa com evidência de que o custo justifica.",
  rationale="A chave fina é a mais segura contra contaminação cruzada de pontuações. Cache ainda não implementado na Fase 1; decisão a confirmar com custo real do Ollama na Fase 2."
)
```
Expected: retorna um id de ADR.

- [ ] **Step 5: Registrar a decisão de clamp do IC**

```
save_adr(
  project="gnomon-eval",
  title="Clamp do intervalo de confiança ao range da métrica",
  context="Métricas como faithfulness são limitadas a [0,1]. Com N pequeno o t crítico é grande e o IC bruto pode ultrapassar 1.0 (ex: ci_high=1.49 para N=2).",
  decision="A média é reportada crua; os limites do IC são clampados a [0,1]. Um 'limite superior' de 1.49 para métrica limitada é artefato do t crítico, não afirmação significativa.",
  rationale="Mantém honestidade estatística (a incerteza aparece via ci_low) sem reportar número sem sentido para o leitor. Decisão tomada na Fase 1, não coberta pelos docs originais."
)
```
Expected: retorna um id de ADR.

- [ ] **Step 6: Verificar que os ADRs entraram no store**

Usar `mcp__axon__get_adrs`:
```
get_adrs(project="gnomon-eval")
```
Expected: lista os 3 ADRs registrados (N de runs, granularidade de cache, clamp do IC).

- [ ] **Step 7: Capturar a memória da Fase 1**

Usar `mcp__axon__axon_capture`:
```
axon_capture(
  summary="Fase 1 do gnomon-eval entregue: fatia vertical ponta-a-ponta (domain tipado, MockTarget, StubJudge seeded, agregação com IC t-interval, runner, reporting, config fail-closed). 44 testes verdes, ruff limpo. Regras inegociáveis 1,2,3,4,6 cobertas por teste. Decisões: clamp do IC, recomendação N=8, nome GNOMON.",
  repo="gnomon-eval",
  files=["src/gnomon/metrics/confidence.py","src/gnomon/judge/stub.py","src/gnomon/runner/runner.py","src/gnomon/domain/models.py"],
  symbols=["aggregate_metric","StubJudge","run_eval","MetricResult"]
)
```
Expected: retorna um id de decisão capturada.

- [ ] **Step 8: Confirmar a pegada no AXON**

Usar `mcp__axon__get_session_memory`:
```
get_session_memory(project="gnomon-eval")
```
Expected: já não retorna "Nenhuma memória de sessão"; mostra o resumo da Fase 1.

---

## Self-Review (preenchido)

**Cobertura do spec:**
- Decisão 1 (processo) → Task 2 (playbook é processo, sem código de produto). ✓
- Decisão 2 (fatia vertical) → documentada no playbook (Task 2 Step 1). ✓
- Decisão 3 (playbook leve) → seção "Fora do loop" do playbook. ✓
- Decisão 4 (ctx personal) → Task 3 Step 1 (`--ctx personal`). ✓
- Decisão 5 (AXON por bloco conclusivo, incremental) → playbook seção AXON + Task 3 só registra decisões novas. ✓
- Decisão 6 (nome GNOMON) → Task 1. ✓
- Definição de Pronto → playbook (Task 2 Step 1). ✓
- Onboarding AXON (index + save_adr novos + sessão) → Task 3. ✓

**Placeholders:** nenhum TODO/TBD; todo conteúdo de doc e toda chamada de ferramenta estão completos.

**Consistência:** `project="gnomon-eval"` em todas as chamadas AXON; `--ctx personal` consistente; nomes de símbolos (`aggregate_metric`, `StubJudge`, `run_eval`, `MetricResult`) batem com o código da Fase 1.
