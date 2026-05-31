# GNOMON

> Mede a qualidade de um pipeline RAG e reporta o número honesto, com a margem de incerteza junto, sem fingir mais confiança do que os dados sustentam.

O nome é a haste do relógio de sol que projeta a sombra que você lê. Também fecha como acrônimo do projeto: **G**ated **N**umerical **O**ffline **M**etrics **O**ver **N**-cases.

## O problema

Quem coloca um RAG em produção não sabe dizer se ele piorou depois do último deploy. As ferramentas de avaliação que existem reportam um score único de qualidade, e esse número mente por dois motivos.

O primeiro é estatístico, e é mais sutil do que parece. A intuição diz que o problema é o juiz LLM ser não-determinístico, então a ferramenta roda o juiz N vezes e reporta uma média com intervalo de confiança. Parece rigoroso. Só que com o juiz em modo reproduzível, a temperatura zero, ele é determinístico: as N execuções são cópias idênticas. Contar cópias idênticas como observações independentes estreita o intervalo por um fator de raiz de N. É rigor de fachada, um palpite vestido de medição.

A incerteza que de fato importa não é o juiz repontuando o mesmo caso. É que o seu dataset de teste é uma amostra pequena de todas as perguntas que os usuários vão fazer. O número honesto carrega a margem dessa amostragem: o intervalo se calcula sobre os casos, não sobre as repetições do juiz. Um score único esconde isso, e o "conserto" padrão de repetir o juiz esconde pior.

O segundo é que qualidade aparece sozinha, descolada de custo e latência. A resposta de qualidade 0.95 que custou quatro vezes mais tokens e três vezes mais tempo que a de 0.91 parece melhor no relatório, mas pode ser a escolha errada para o caso de uso. A decisão real nunca é "qual responde melhor", e sim "qual responde bem o suficiente pelo custo que cobra".

## O que é

Um harness de avaliação que roda contra qualquer RAG que fale o protocolo OpenAI-compat. Define um conjunto de casos de teste com pergunta, resposta esperada e contextos esperados, executa o RAG alvo contra esses casos e calcula métricas de qualidade.

A diferença está em três pontos. Toda métrica baseada em juiz sai com intervalo de confiança, nunca como número solto, então a pessoa vê o ruído em vez de ignorá-lo. Custo e latência por pergunta saem no mesmo relatório que a qualidade, lado a lado, para a decisão ser tomada sobre o trade-off real. E o harness roda como teste de regressão no CI, falhando o build quando uma métrica cai abaixo de um limite configurável, o que transforma avaliação de relatório manual em portão automático.

O alvo de exemplo é um sistema RAG real, não um brinquedo. O harness avalia o RPG Master AI através da API REST que ele já expõe, e trocar para outro RAG é mudar uma linha de configuração.

## Para quem

Engenheiro que mantém um pipeline RAG em produção e precisa de um sinal confiável de que a qualidade não regrediu entre deploys. Time pequeno que não tem infraestrutura de avaliação e não quer montar uma do zero. Quem compara modelos ou estratégias de retrieval e precisa de número com significância estatística, não impressão.

## Como funciona

1. Você define um dataset de avaliação: perguntas, respostas esperadas e contextos esperados, versionado junto do código.
2. Configura o target apontando para o seu RAG via endpoint OpenAI-compat.
3. Roda o harness. Ele executa cada caso contra o RAG, coleta resposta, contextos, tokens e latência.
4. Um juiz LLM pontua cada resposta em faithfulness e context precision. As N runs por caso fazem denoise; o intervalo de confiança vem do espalhamento **entre os casos** via bootstrap, não da repetição do juiz (ADR-008).
5. O relatório sai com cada métrica acompanhada do intervalo de confiança, mais custo e latência agregados e por pergunta.
6. No CI, o mesmo eval roda como teste e falha o build se uma métrica cruza o limite configurado.

## Stack

- Linguagem: Python 3.11
- Avaliação offline: Ollama via Docker
- Juiz e target: protocolo OpenAI-compat
- Testes e gate: pytest
- Lint e formatação: ruff

## Status atual

v1 entregue. Target real (OpenAI-compat), juiz Ollama, agregação por caso com IC por bootstrap (ADR-008), gate, CLI de um comando, infra Docker offline e CI — 77 testes verdes, 8 ADRs. O caminho de execução offline com Ollama é o default desde o primeiro corte. Backlog da v2 em `docs/ROADMAP.md`.

## O que não faz (ainda)

- Answer relevance e context recall ficam para a v2. A arquitetura de juiz já comporta, mas não estão no primeiro corte.
- Não tem dashboard de tendência temporal. O relatório é por execução. Histórico persistido e visualização vêm depois.
- Não compara múltiplos targets numa única execução. Isso entra quando o orquestrador que consome este harness precisar.
- Não substitui avaliação humana em casos de alta criticidade. Mede o que dá para medir de forma reproduzível e é honesto sobre a margem.

## Links

- Repositório: https://github.com/sammyjdev/gnomon-eval
- Documentação técnica: ver `README.md` e `docs/`
- Decisões de arquitetura: ver `docs/adr/`
