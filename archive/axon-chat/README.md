# Retired AXON chat targets

Historical only. These configs called AXON `POST /v1/chat/completions` on
`localhost:8765`. That endpoint has been dead since AXON dec-138. They are
not a live eval and they are not a CI gate.

The AXON evaluation planned for this lab is brief-eval (`AxonBriefTarget` /
brief@budget). It is not implemented. See the repository README.

| File | What it was |
|---|---|
| `axon.toml` | Toy single-turn chat eval (example dataset, local Ollama judge) |
| `axon-recall-on.toml` / `axon-recall-off.toml` | Code-recall A/B (`include_context` on vs off) |
| `axon-session.toml` / `axon-session-smoke.toml` / `axon-session-b500.toml` | Multi-turn session savings against the same chat endpoint |
| `alignment-on.toml` / `alignment-off.toml` | Judge-alignment draw against the same chat endpoint |

Faithfulness and recall figures produced with these files are historical
measurements of the retired endpoint. They are not current AXON results.
