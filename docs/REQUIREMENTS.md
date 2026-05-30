# RAG Eval Harness — Requisitos

Documento de requisitos da v1. Cada requisito tem um identificador para rastreio em spec, teste e ADR. Os requisitos funcionais descrevem o que o sistema faz. Os não funcionais descrevem as restrições de qualidade que governam como ele faz. As validações descrevem o que o sistema rejeita e como.

## Requisitos funcionais

### RF-01 — Definição de dataset de avaliação
O sistema lê um dataset de casos de avaliação versionado em arquivo. Cada caso contém pergunta, resposta esperada e lista de contextos esperados. O dataset é a fonte de verdade da avaliação e vive junto do código, não em banco externo.

### RF-02 — Target RAG via adapter
O sistema avalia qualquer RAG acessível por um adapter. O primeiro adapter concreto fala protocolo OpenAI-compat por REST. Trocar de target é trocar configuração, não código do harness.

### RF-03 — Execução de caso contra o target
Para cada caso do dataset, o sistema envia a pergunta ao target e coleta a resposta, os contextos recuperados, os tokens consumidos e a latência em milissegundos.

### RF-04 — Pontuação por juiz LLM
Um juiz LLM pontua cada par caso/resposta nas métricas de qualidade da v1. O juiz roda sob controle de seed e cache para sustentar reprodutibilidade.

### RF-05 — Métricas da v1
O sistema calcula faithfulness (a resposta está ancorada nos contextos recuperados) e context precision (os contextos recuperados são relevantes para a pergunta).

### RF-06 — Variância do juiz com intervalo de confiança
O sistema executa a pontuação do juiz N vezes por métrica e reporta média com intervalo de confiança. Nenhuma métrica baseada em juiz sai como número único.

### RF-07 — Custo e latência por pergunta
O sistema reporta tokens e latência por pergunta e agregados. Essas saídas aparecem no mesmo relatório que a qualidade, não em relatório separado.

### RF-08 — Relatório de execução
O sistema produz um relatório legível por máquina e por humano contendo, para cada métrica, média, limite inferior e superior do intervalo de confiança e número de execuções do juiz, além dos números de custo e latência.

### RF-09 — Gate de regressão
O sistema expõe a avaliação como teste executável que falha quando uma métrica cai abaixo de um limite configurável. O limite é definido por configuração, por métrica.

### RF-10 — Execução offline por default
O caminho de execução documentado no README roda com Ollama via Docker, sem chave de API paga. O caminho com provedor pago existe atrás de configuração isolada e opcional.

### RF-11 — Reprodutibilidade do exemplo
A execução de exemplo do README produz, dentro da variância reportada, os mesmos números a cada rodada na mesma máquina com a mesma configuração e seed.

## Requisitos não funcionais

### RNF-01 — Reprodutibilidade
Mesma entrada, mesma seed e mesmo modelo de juiz produzem o mesmo resultado dentro da variância medida e reportada. A reprodutibilidade é invariante de projeto, verificada por teste, não promessa de documentação.

### RNF-02 — Direção de dependência
O harness depende de targets por contrato (a interface do adapter), nunca de internals de uma implementação concreta. Um target é definido por interface. A evolução do RAG alvo não quebra o harness enquanto o contrato público se mantém.

### RNF-03 — Honestidade estatística
O sistema nunca apresenta número de qualidade baseado em juiz sem a margem de incerteza. Score único para métrica não-determinística é tratado como defeito, não como simplificação aceitável.

### RNF-04 — Acessibilidade de execução
Um terceiro clona o repositório, sobe o ambiente com Docker e roda a avaliação de exemplo com um comando. Nenhuma etapa do caminho default exige credencial paga ou infraestrutura que o avaliador não tenha localmente.

### RNF-05 — Consistência entre documentação e código
Toda afirmação do README tem um comando que a reproduz. Claim sem comando correspondente é tratado como defeito de documentação.

### RNF-06 — Custo de execução previsível
O número de chamadas ao juiz por execução é função explícita do tamanho do dataset e do N de runs de variância. O sistema não faz chamadas de modelo fora desse cálculo declarado.

### RNF-07 — Isolamento de configuração
Configuração de target, modelo de juiz, seed, N de runs e limites de gate vivem em configuração externa ao código. Mudar qualquer um não exige editar fonte.

### RNF-08 — Qualidade de código verificada
O projeto roda lint e testes em integração contínua. Lint, compilação e suíte de testes verdes são barreira de release.

## Validações esperadas

### VAL-01 — Dataset malformado falha fechado
Dataset ausente, com caso sem pergunta, sem resposta esperada ou sem contextos esperados, rejeita a execução com erro explícito que aponta o caso problemático. O sistema nunca avalia parcial em silêncio.

### VAL-02 — Target inacessível falha explícito
Target que não responde, responde fora do protocolo OpenAI-compat ou estoura timeout produz erro nomeado que distingue falha de configuração de falha do target em runtime.

### VAL-03 — Resposta do target incompleta
Resposta sem contextos, sem contagem de tokens ou sem latência é rejeitada ou marcada conforme política definida em ADR, nunca tratada como zero silencioso que contamina a métrica.

### VAL-04 — N de runs insuficiente para intervalo de confiança
N de runs do juiz abaixo do mínimo necessário para calcular intervalo de confiança rejeita a configuração com mensagem que indica o mínimo aceitável.

### VAL-05 — Limite de gate mal configurado
Limite de regressão fora da faixa válida da métrica (por exemplo, limite negativo ou acima do máximo possível) rejeita a configuração antes de qualquer chamada de modelo.

### VAL-06 — Seed ausente em modo reproduzível
Execução em modo reproduzível sem seed declarada falha, em vez de gerar seed implícita que quebraria a reprodutibilidade entre rodadas.

### VAL-07 — Cache inconsistente
Entrada de cache cuja chave não casa com a tupla de identidade definida (caso, resposta, modelo de juiz, seed) é tratada como miss, nunca como acerto que retornaria pontuação de contexto errado.

## Rastreabilidade

| Requisito | ADR relacionado |
|---|---|
| RNF-02, RF-02 | ADR-001 (adapter-based target) |
| RNF-01, RNF-03, RF-04, RF-06, VAL-06, VAL-07 | ADR-002 (não-determinismo do juiz) |
| RF-10, RNF-04 | ADR-003 (offline-first com Ollama) |
| RF-07, RNF-06 | ADR-004 (custo e latência como métrica de primeira classe) |

## Fora de escopo da v1

Answer relevance, context recall, dashboard temporal, comparação multi-target e persistência de histórico de execuções não fazem parte da v1. A arquitetura comporta a adição sem reescrita, mas a entrega inicial não os inclui.
