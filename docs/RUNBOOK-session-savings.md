# Runbook: Session savings measurement

Prereqs: AXON endpoint reachable at `http://localhost:8765/v1`, Ollama judge
reachable at `http://100.78.123.92:11434`, and the session datasets present at
`datasets/sessions/sessions.json` and `datasets/sessions/smoke.json`.

1. Start the AXON server with the session harness environment:

   ```bash
   AXON_MAX_PRE_SEND_TOKENS=32000 AXON_COMPLETION_MODEL="ollama/llama3.1:8b" AXON_PROVIDER_OLLAMA=1 OLLAMA_BASE_URL="http://100.78.123.92:11434" ~/.pyenv/versions/clock/bin/axon serve-http --port 8765
   ```

   Why `32000`: `AXON_MAX_PRE_SEND_TOKENS` defaults to `8000`
   (`../axon/src/axon/router/engine.py:39`). The router does not truncate:
   a request over the cap raises `DENY_BUDGET_PRE_SEND`, which the endpoint
   converts into an `"[LLM unavailable]"` answer with `usage_source="estimate"`
   (and the baseline arm's estimate covers only the bare current question, a
   wildly wrong prompt-token number). One over-cap turn therefore poisons that
   session's numbers; the validity gate (`non_provider_records == 0`) catches
   it and invalidates the run. The 32000 override keeps 10-turn baseline
   transcripts under the cap. This is an env override only. No code change is
   required.

2. Run the smoke check before the full run (from the gnomon-eval repo root -
   `sessions_path` in the configs is resolved relative to the working
   directory):

   ```bash
   gnomon session -c config/axon-session-smoke.toml --json
   ```

   Verify before continuing:
   - every turn record has `usage_source="provider"`
   - the JSON contains a sane `per_turn` curve, `cumulative`,
     `crossover_turn`, `quality_gate`, `validity.non_provider_records`, and
     `completion_tokens`

3. Run the full measurement and save the JSON:

   ```bash
   gnomon session -c config/axon-session.toml --json > session.json
   ```

   Then run the same full config a second time for stability. The two
   cumulative savings means must each fall within the other run's CI.

4. Budget the calls up front (RNF-06):
   - generation calls = `sessions x turns x 2` = `10 x 10 x 2 = 200`
   - judge calls = `sessions x 2 x judge_runs` = `10 x 2 x 6 = 120`
   - expect roughly 30-45 minutes of GPU time

5. Apply the validity checklist before treating the run as publishable:
   - `validity.non_provider_records == 0`
   - `quality_gate == "pass"`
   - the stability replicate passes
   - report the `crossover_turn` alongside the headline
   - never publish the headline without the full savings curve

6. Propagate the measured claim only after a valid measured run and owner
   review:
   - update the AXON README badge and `docs/METRICS.md` to:
     `"AXON's fixed-recall arm uses X% fewer input tokens over N-turn sessions (95% CI over M sessions, llama3.1:8b), with final-turn faithfulness held at parity; savings cross zero at turn K. Projection retired: 52.3% (deterministic model)."`

7. Publish the session assumptions block verbatim with the measured number:
   - AXON arm sends zero conversation history; recall is its only memory.
   - Recall budget cap is 2000 tokens per request. The effective budget is
     `min(2000, strategy.max_chars / 4)`, between 1000 and 2000 tokens
     depending on the retrieval strategy AXON selects per query
     (`../axon/src/axon/mcp/server.py:340`); a smaller effective budget can
     inflate savings relative to a literal "fixed 2000" reading.
   - Sessions are scripted: LLM-drafted, owner-reviewed, anchored to Wave 1's
     17 validated cases, not live traffic.
   - Referential turns intentionally stress the zero-history arm by design.
   - Judge is `llama3.1:8b`, faithfulness-only, no ground truth.
   - Known asymmetry: the baseline arm is judged for faithfulness against its
     own forwarded transcript, and answers drawing on the model's parametric
     knowledge read as ungrounded. This systematically understates baseline
     faithfulness and makes the parity gate more permissive; it is a stated
     limitation of the gate, not a neutral comparison.

Notes:
- The AXON arm uses `include_context=true` and `recall_max_tokens=2000`.
- The baseline arm uses `forward_history=true` and `include_context=false`.
- Final-turn faithfulness is judged against what each arm actually saw:
  retrieved contexts for AXON, forwarded transcript for baseline.
- If an arm's final turn has empty contexts, that session-arm scores `0.0`
  without a judge call. Keep the session in the run; do not exclude it.
