# Runbook: AXON recall A/B (the honest number)

Prereqs: datasets/second_brain/cases.json (15+ cases, see datasets/
second_brain/README.md), AXON stack up (postgres/pgvector), Ollama up
(judge model llama3 pulled), and a completion model reachable by AXON.

1. Start the endpoint (axon repo):
       axon serve-http --port 8765
2. Optional but recommended - archive old telemetry so this run's
   records are isolated:
       mv "$(python -c 'from axon.observability.recall_telemetry import \
       RecallTelemetryStore; print(RecallTelemetryStore().stats_file)')" \
       /tmp/recall-backup.jsonl 2>/dev/null || true
3. Run both arms (gnomon-eval repo):
       gnomon -c config/axon-recall-on.toml  --json > on.json
       gnomon -c config/axon-recall-off.toml --json > off.json
4. Compare (telemetry path printed by the python one-liner above):
       python -m gnomon.reporting.compare on.json off.json \
           --telemetry <recall/requests.jsonl>
5. Validity checks - the number is only publishable if ALL hold:
   - compare output has NO "usage_source=estimate" warning;
   - no answer in on.json/off.json contains "[LLM unavailable";
   - stability: repeat step 3-4 into on2.json/off2.json; metric means
     must agree within their CIs across the two runs.
6. Record the final claim exactly as:
   "AXON recall lifts faithfulness A->B (95% CI, N cases) at a cost of
   +E input tokens/turn. Reproduce: gnomon -c config/axon-recall-on.toml."
   Never phrase Wave 1 as token savings (ADR 0009).
