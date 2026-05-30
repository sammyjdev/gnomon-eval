# GNOMON — Arquitetura

Documento de arquitetura da v1. Descreve os componentes, a direção de dependência entre eles, o fluxo de dados de uma execução e a estrutura de pastas do repositório.

## Princípio organizador

O harness é organizado por direção de dependência. O núcleo de avaliação não conhece detalhes de nenhum target nem de nenhum provedor de juiz. Ele depende de contratos. As implementações concretas de target e juiz dependem do núcleo, nunca o contrário. Essa regra é a mesma que sustenta a evolução independente do RAG alvo: enquanto o contrato se mantém, o RPG Master AI muda por dentro sem quebrar o harness.

## Componentes

### Domain
O coração tipado do sistema. Contém os modelos de caso de avaliação, resposta do target, pontuação de métrica e resultado com intervalo de confiança. Não importa nada de infraestrutura. Define as interfaces que o resto implementa.

### Target adapter
Traduz entre o contrato `RagTarget` do domínio e um RAG concreto. O primeiro adapter fala protocolo OpenAI-compat por REST. Recebe uma pergunta, devolve resposta, contextos, tokens e latência no formato do domínio. Um novo target é um novo adapter, sem tocar no núcleo.

### Judge
Pontua um par caso/resposta nas métricas de qualidade. Encapsula o controle de seed e o cache que sustentam a reprodutibilidade. Roda a pontuação N vezes para alimentar o cálculo de variância. O provedor de juiz é configurável; o default offline usa Ollama.

### Metrics
Calcula faithfulness e context precision a partir das pontuações do juiz, e agrega custo e latência a partir das respostas do target. Produz `MetricResult` sempre com média e intervalo de confiança, nunca número solto.

### Runner
Orquestra uma execução. Lê o dataset, itera os casos, chama o target via adapter, chama o juiz, agrega as métricas e monta o relatório. É o ponto onde as peças se encontram, e o único que conhece todas elas.

### Reporting
Serializa o resultado da execução em formato legível por máquina e por humano. Mesma fonte de dados para os dois formatos, para não haver divergência entre o que a máquina lê e o que a pessoa vê.

### Gate
Compara o resultado contra limites configurados por métrica e decide passa ou falha. Exposto como teste para rodar no CI. É a camada que transforma avaliação em portão de regressão.

### Config
Carrega configuração externa: endpoint e tipo de target, modelo de juiz, seed, N de runs de variância e limites de gate. Valida a configuração antes de qualquer chamada de modelo.

## Direção de dependência

```
                 +-------------------+
                 |      Domain       |
                 |  (modelos +       |
                 |   interfaces)     |
                 +-------------------+
                   ^   ^   ^   ^   ^
                   |   |   |   |   |
     +-------------+   |   |   |   +-------------+
     |             +---+   |   +---+             |
     |             |       |       |             |
+----------+  +--------+  +-------+  +--------+  +---------+
| Target   |  | Judge  |  |Metrics|  | Gate   |  |Reporting|
| adapter  |  |        |  |       |  |        |  |         |
+----------+  +--------+  +-------+  +--------+  +---------+
     ^             ^          ^          ^           ^
     |             |          |          |           |
     +-------------+----+-----+----------+-----------+
                        |
                   +---------+
                   | Runner  |
                   +---------+
                        ^
                        |
                   +---------+
                   | Config  |
                   +---------+
```

Todas as setas apontam para o Domain. O Domain não aponta para ninguém. O Runner depende das implementações; as implementações dependem do Domain. Nenhuma implementação concreta depende de outra implementação concreta.

## Fluxo de dados de uma execução

1. Config carrega e valida a configuração. Configuração inválida para a execução antes de qualquer chamada de modelo.
2. Runner lê o dataset. Dataset malformado para a execução com erro que aponta o caso.
3. Para cada caso, Runner chama o Target adapter com a pergunta.
4. Target adapter consulta o RAG concreto e devolve resposta, contextos, tokens e latência no formato do domínio.
5. Runner passa o par caso/resposta ao Judge.
6. Judge pontua N vezes sob seed controlada, usando cache para pontuações já calculadas.
7. Metrics calcula faithfulness e context precision com intervalo de confiança a partir das N pontuações, e agrega custo e latência das respostas.
8. Reporting serializa o resultado nos dois formatos a partir da mesma fonte.
9. Gate, quando rodando no CI, compara o resultado aos limites e decide passa ou falha.

## Estrutura de pastas

```
gnomon-eval/
├── README.md
├── pyproject.toml
├── ruff.toml
├── docker-compose.yml          # Ollama + harness para execução offline
├── Dockerfile
├── .github/
│   └── workflows/
│       └── ci.yml              # ruff, pytest matrix, gate smoke
├── docs/
│   ├── PRODUCT_OVERVIEW.md
│   ├── REQUIREMENTS.md
│   ├── ARCHITECTURE.md
│   └── adr/
│       ├── 0001-adapter-based-target.md
│       ├── 0002-judge-nondeterminism.md
│       ├── 0003-offline-first-ollama.md
│       └── 0004-cost-latency-first-class.md
├── src/
│   └── gnomon/
│       ├── domain/             # modelos e interfaces, sem dependência de infra
│       ├── targets/            # adapters; openai_compat é o primeiro
│       ├── judge/              # juiz, seed control, cache
│       ├── metrics/            # faithfulness, context precision, agregação custo/latência
│       ├── runner/             # orquestração da execução
│       ├── reporting/          # serialização máquina e humano
│       ├── gate/               # comparação contra limites
│       └── config/             # carregamento e validação de config
├── datasets/
│   └── rpg_master_example/     # ground truth versionado do exemplo
└── tests/
    ├── unit/                   # domínio, métricas, config, gate com mocks
    ├── integration/            # runner contra target via adapter
    └── reproducibility/        # mesma seed produz mesmo resultado dentro da variância
```

## Decisões de design

As decisões que governam esta arquitetura estão registradas em ADRs:

- **ADR-001** justifica o target baseado em adapter em vez de acoplamento direto ao RPG Master AI.
- **ADR-002** define como o sistema trata o não-determinismo do juiz LLM.
- **ADR-003** explica por que o caminho default é offline com Ollama.
- **ADR-004** registra por que custo e latência são métricas de primeira classe.

## Mapa de testes para a estrutura

Os testes refletem a direção de dependência. Testes unitários cobrem domínio, métricas, config e gate isoladamente com mocks, sem rede nem modelo. Testes de integração cobrem o Runner contra um target através do adapter. Testes de reprodutibilidade verificam que a mesma seed produz o mesmo resultado dentro da variância reportada, o que é a verificação executável de RNF-01.
