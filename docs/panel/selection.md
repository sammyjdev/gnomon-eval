# Panel selection (ADR-0012, issue #55)

Execution plan item (c) from ADR-0012: screen free-rail candidates, distinct
vendor families of the same generation, through the B4 capacity bar, then
pin the panel with screening evidence linked. Pinned config:
`config/panel.toml`.

## Method

Each candidate is served by DeepInfra's OpenAI-compatible endpoint
(`https://api.deepinfra.com/v1/openai`, via `OpenAICompatJudge`). Model IDs
were confirmed live against DeepInfra's `/v1/openai/models` endpoint at
selection time (2026-07-21), not assumed from prior knowledge. Three probes
per candidate (`sb-001`, `sb-002`, `sb-003` from
`datasets/second_brain/cases.json`, the ADR-0012 screening corpus) go
through the canonical v1 judge prompt (`gnomon.judge.prompts.build_prompt`),
scoring the case's own `expected_answer`/`expected_contexts` (a response
that should score clean on every metric). The raw completion text (the
`choices[0].message.content` field of the wire response -- the same field
`OpenAICompatJudge` reads in production) is screened by
`gnomon.judge.screening.screen_candidate` (B4: valid JSON, schema-compliant,
no hallucinated keys), with no retries and no per-candidate prompt tuning --
membership is earned by the bar, not adjusted to fit it (ADR-0012 #4/#5).

## Panel members (pinned)

| Family (vendor) | Model | Size | Result | Evidence |
|---|---|---|---|---|
| Meta | `meta-llama/Meta-Llama-3.1-8B-Instruct` | 8B | pass (3/3) | `docs/panel/screening/deepinfra_llama31_8b.json` |
| Mistral AI | `mistralai/Mistral-Nemo-Instruct-2407` | 12B | pass (3/3) | `docs/panel/screening/deepinfra_mistral_nemo_12b.json` |
| Zhipu / Z.ai | `zai-org/GLM-4.6` | large (flagship MoE, not size-matched) | pass (3/3) | `docs/panel/screening/deepinfra_glm46.json` |

**Mistral size note:** DeepInfra does not currently carry a 7-9B Mistral
instruct model (the smallest available is the 12B Mistral-Nemo-Instruct;
Mistral-Small variants are 24B). Mistral-Nemo-2407 is the closest available
size to the 7-9B band and still the same "small open instruct" class as
Llama-3.1-8B.

**GLM-4.6 size/generation note (declared deviation, ADR-0012 revisit trigger
#1):** the third slot was originally targeted at a size-matched Alibaba
Qwen candidate; both viable Qwen options failed for operational reasons (see
Rejected candidates below), and no size-matched third-family alternative
(7-9B, distinct from Meta/Mistral) was available and reachable on DeepInfra
at selection time -- `google/gemini-1.5-flash-8b` is listed in the catalog
but returns HTTP 500 (upstream 404, not actually served). GLM-4.6 is a much
larger flagship MoE model than the other two members, which is exactly the
capability imbalance ADR-0012 #1 warns against ("same generation avoids
capability imbalance masquerading as disagreement"). It is pinned anyway
because it is the only distinct-family candidate that passed B4 cleanly and
reliably; this is flagged here as a live gap rather than smoothed over.
Revisit when a size-matched third family becomes reachable (a Qwen fix, a
different DeepInfra listing, or the local Ollama fallback family).

## Rejected candidates

| Candidate | Family | Reason | Evidence |
|---|---|---|---|
| `Qwen/Qwen3.5-9B` | Alibaba | Not a B4/schema failure -- `sb-001` passed cleanly, but response latency was extreme and inconsistent (163s for one probe; 240s+ timeouts on others), driven by very long reasoning-mode chain-of-thought before the final answer. Operationally unviable for a judge called ~dozens of times per run (ADR-0012 cost assumption of "trivial" per-call cost breaks down). No full evidence artifact -- screening never completed all 3 probes within a workable timeout. |
| `zai-org/GLM-4.7-Flash` | Zhipu / Z.ai | Failed B4: for all 3 probes, `choices[0].message.content` (the field `OpenAICompatJudge` reads) came back empty -- the model routed the entire JSON answer into `reasoning_content` instead, which the v1 wire contract does not read. Genuine schema-compliance failure, not an infra issue. | `docs/panel/screening/deepinfra_glm47_flash_REJECTED.json` |

## Offline fallback (ADR-0012 #6, not screened)

`llama3.1:8b` via local Ollama (desktop host) is the documented offline
fallback single judge. Not screened as part of this selection -- the desktop
Ollama host was offline at selection time. Any run using only this judge is
single-judge, not panel, and must be labeled as such per the ADR.
