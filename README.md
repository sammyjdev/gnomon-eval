# GNOMON

> Avalia um pipeline RAG e reporta qualidade com o intervalo de confiança junto, mais custo e latência, rodando offline com Ollama.

## Executar a avaliação (offline, um comando)

Pré-requisito: Docker. O caminho default usa um Ollama local como juiz, sem
chave paga (RF-10). O exemplo avalia um **MockTarget** (respostas de RAG
canônicas) pontuado pelo juiz Ollama real — não exige um serviço de RAG
externo. Para avaliar um RAG real, troque o bloco `[target]` em
`config/example.toml` para `kind = "openai_compat"` (instruções no próprio
arquivo).

```bash
# 1. Sobe o Ollama e baixa o modelo do juiz
docker compose up -d ollama
docker compose exec ollama ollama pull llama3

# 2. Roda a avaliação de exemplo (config + dataset versionados)
docker compose run --rm harness
```

Saída: relatório com, por métrica, média e intervalo de confiança (N runs do
juiz), além de tokens e latência. O processo sai com código 0 se o gate passa,
1 se alguma métrica fica abaixo do limite em `config/docker.toml` (RF-09).

A primeira execução baixa o modelo do Ollama, o que leva alguns minutos. As seguintes usam o modelo já em cache.

### Rodar no host (Ollama local, sem Docker para o harness)

```bash
pip install -e ".[dev]"
# com um Ollama escutando em localhost:11434 e o modelo llama3 baixado:
gnomon --config config/example.toml
```

### Check determinístico (sem Ollama, sem Docker)

```bash
pip install -e ".[dev]"
python -m pytest -q          # 74 testes: unidade, reprodutibilidade e smoke do gate
```

### Reprodutibilidade (RF-11 / RNF-01)

Mesma seed + mesma config + mesma máquina produzem os mesmos números dentro da
variância reportada. Verificado por teste:

```bash
python -m pytest tests/reproducibility -q
```

## O que isto faz

Lê um dataset de casos de avaliação, roda cada caso contra um RAG alvo, pontua as respostas com um juiz LLM e reporta faithfulness e context precision, cada uma com intervalo de confiança, junto de custo em tokens e latência em milissegundos. O mesmo eval roda como teste de regressão no CI e falha o build quando uma métrica cai abaixo de um limite configurável.

O exemplo avalia um MockTarget (respostas canônicas) pontuado por um juiz Ollama local, sem dependência externa. Trocar para um RAG real que fale o protocolo OpenAI-compat é mudar o bloco `[target]` em `config/example.toml`.

## Arquitetura

O núcleo de avaliação depende de interfaces, nunca de implementações concretas. Targets e juiz dependem do núcleo. Detalhes e diagrama em `docs/ARCHITECTURE.md`.

```
Config -> Runner -> [Target adapter] -> RAG alvo
                 -> [Judge] --------> métricas com intervalo de confiança
                 -> [Metrics] ------> custo e latência
                 -> [Reporting] ----> relatório máquina + humano
                 -> [Gate] ---------> passa/falha no CI
```

## Configuração

Toda a configuração vive em arquivos TOML versionados:

- `config/example.toml` — para rodar no host com Ollama em `localhost:11434`
- `config/docker.toml` — para rodar via `docker compose run --rm harness` (judge aponta para o serviço `ollama` da rede compose)

Os parâmetros de avaliação (seed, número de runs do juiz, limites do gate) estão documentados dentro dos próprios arquivos de config.

## Como rodar os testes

```bash
pip install -e ".[dev]"
python -m pytest -q                    # suite completa: 74 testes
python -m pytest tests/unit -q         # só unitários
python -m pytest tests/reproducibility -q   # só reprodutibilidade
python -m pytest tests/gate -q         # só smoke do gate
```

Os testes de reprodutibilidade verificam que a mesma seed produz o mesmo resultado dentro da variância reportada. Essa é a verificação executável da invariante central do projeto.

## Decisões de design

As decisões que governam o projeto estão em `docs/adr/`:

- ADR-001 — target baseado em adapter, para o harness servir a qualquer RAG e sobreviver à evolução do RPG Master AI.
- ADR-002 — tratamento do não-determinismo do juiz, com intervalo de confiança em vez de número único.
- ADR-003 — execução offline-first com Ollama, para o exemplo rodar sem custo.
- ADR-004 — custo e latência como métricas de primeira classe, ao lado da qualidade.

Requisitos completos em `docs/REQUIREMENTS.md`. Visão de produto em `docs/PRODUCT_OVERVIEW.md`.

## O que não faz (ainda)

Answer relevance, context recall, dashboard temporal, comparação multi-target e persistência de histórico ficam para a v2. A arquitetura comporta a adição sem reescrita.

## Contribuindo

Commits seguem Conventional Commits. O gate de CI roda `pytest` e `ruff check` — PRs precisam passar ambos.

## Licença

[TODO: definir]
