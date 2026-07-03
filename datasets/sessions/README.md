# Session dataset (multi-turn savings harness, Wave 2)

Datasets consumed by the session savings harness (ADR-0010): `sessions.json`
(10 sessions x 10 turns, the full measurement set) and `smoke.json`
(3 sessions x 5 turns, for cheap end-to-end smoke runs before the full run).

## Schema

Each file is a JSON array of sessions matching `gnomon.domain.session.Session`:

```json
[
  {
    "id": "sess-001",
    "topic": "One coherent topic thread",
    "turns": ["first user turn", "second user turn", "..."]
  }
]
```

Constraints enforced by the loader (`gnomon.dataset.session_loader.load_sessions`):
non-empty `id` and `topic`, at least 2 turns, no empty turn strings, no
duplicate ids. Validate before running:

```
.venv/bin/python -c "from gnomon.dataset.session_loader import load_sessions; \
print(len(load_sessions('datasets/sessions/sessions.json')), 'sessions')"
```

## Provenance

Sessions are LLM-drafted from vault topics anchored to Wave 1's validated
cases (`datasets/second_brain/cases.json`), owner-reviewed before commit.
Every session is one topic thread the owner would plausibly ask about in
sequence: turns start broad and drill in. All turns are answerable from
indexed vault content in the personal/career/knowledge contexts - never from
work projects. Language follows the vault per topic: PT-BR dominant, EN mixed
where the underlying notes are EN (e.g. axon commit messages, dec-100).

## Zero-history arm caveat (by design)

Each session contains 2-3 referential turns ("e por que essa escolha?",
"quais os trade-offs disso?") that only make sense given the preceding
conversation. These intentionally stress the AXON arm, which sends ZERO
conversation history and relies on retrieval alone (plan design decision 3).
Do not "fix" these turns to be self-contained - degradation on referential
turns is part of what the harness measures, and the final-turn faithfulness
gate exists to catch a quality collapse.

## Grounding spot-checks performed (2026-07-03)

Checked with the AXON MCP search tool (`mcp__axon__ask`, semantic search over
the indexed vault) plus direct `rg` over `~/vault` for the exact Wave 1 source
snippets. Evidence per topic:

| Session | Topic | Evidence found |
|---|---|---|
| sess-001 | ADR pipeline dogfood | `vault/AXON/Sessions/2026-05-28-pipeline-dogfood-tree-sitter.md` (hook wiring gap dec-110, InferenceStatus enum, provider dinamico dec-106) |
| sess-002 | Density gate evolution | `vault/AXON/Decisions/dec-040.md` (caps 0.7 to 0.85 / 0.9 to 0.95, files touched, validation score); dec-039 listed in `vault/AXON/Architecture/axon.md` |
| sess-003 | Provider profiles / routing | `axon/docs/ADR.md` ADR-002 (tier shape, free/paid models); `axon/README.md` Provider profiles (rate-limit gates, DENY_RATE_LIMIT, dec-106) |
| sess-004 | Rename + MCP migration | `axon/docs/decisions/dec-100-rename-prometheus-to-axon.md`; dogfood session note has the `mcp__prometheus__`/`mcp__axon__` migration lines (rg: 2 hits) |
| sess-005 | rpg-master-ai RAG | `vault/AXON/Architecture/rpg-master-ai.md` + `vault/AXON/Decisions/dec-513.md` (TEI cpu-1.2 / Rosetta); chunking 400/80 and threshold/reranking in `vault/career/interviews/technical/{afya-prep-3-pilares,rag-flow-scripts,interview-defense-rag-topics,interview-drill-master}.md` and dec-506 |
| sess-006 | Embedding stack | bge-m3 in `vault/AXON/Architecture/axon.md` + `vault/AXON/Decisions/dec-409.md`; pgvector-vs-Qdrant rationale in `vault/career/interviews/technical/knowledge-map-ai-projects.md` |
| sess-007 | GNOMON / RAGAS removal | commit a3fe54a + ragas + gnomon-eval in `vault/career/interviews/technical/afya-prep-3-pilares.md` (rg: 5/5/7 hits); "5 perguntas" verdict in `vault/career/interviews/technical/veredito-tecnico-honesto.md` |
| sess-008 | GLYPH knowledge graph | full walkthrough in `vault/career/interviews/technical/rag-flow-scripts.md` (dual extractors, ambiguous-symbol edge omission, NetworkX default, Louvain over structural-edge projection, fair baseline, 25-query benchmark, graph-derived oracle); glyph also covered in `vault/career/interviews/technical/{interview-defense-rag-topics,knowledge-map-ai-projects}.md`; `mcp__axon__ask` surfaced the glyph-kg package (Extractor, EdgeType, NetworkXStore) |
| sess-009 | Vault knowledge strategy | `vault/knowledge/skill-priority-map.md` (top 5, tiers, curadoria); `vault/knowledge/ai-engineering/flows/{top5-skill-update-flow,top5-update-options-tradeoffs}.md` |
| sess-010 | LinkedIn pipeline | `vault/personal/adrs/linkedin_content_manager.md` (Sonnet 4.6 / Opus cost, Rejeitar keyboard, hero_strategy deletion; rg: 2/6/7/3 hits) |

No drafted topic lacked vault support; one candidate turn about the AXON
Postgres port (dec-121 operational detail) was replaced with the
pgvector-vs-Qdrant comparison because its grounding lives in machine-local
config, not in an indexed vault note. Owner review additionally replaced the
original sess-008 (a private commercial project excluded from public
benchmark data) with the GLYPH topic above.

## Regeneration

1. Re-read `datasets/second_brain/cases.json` and its README - topics must
   stay inside the universe those validated cases cover.
2. Draft sessions as coherent 10-turn threads (broad to specific), keeping
   2-3 referential turns per session.
3. For every topic, spot-check at least 2 turns against the vault via the
   AXON MCP search tool; replace any topic without supporting content.
4. Validate with `load_sessions` (both files).
5. Owner reviews and approves before commit (the published claim's
   provenance line depends on this gate).
