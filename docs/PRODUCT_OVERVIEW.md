# GNOMON

> Mede a qualidade de um pipeline RAG e reporta o número honesto, com a variância junto, sem esconder o quanto o próprio juiz oscila.

## O problema

Quem coloca um RAG em produção não sabe dizer se ele piorou depois do último deploy. As ferramentas de avaliação que existem reportam um score único de qualidade, e esse número mente por dois motivos.

O primeiro é que a maioria das métricas de RAG usa um LLM como juiz, e LLM não é determinístico. Roda a mesma avaliação duas vezes e os números mudam. Um relatório que diz "faithfulness 0.87" esconde que a segunda execução deu 0.83 e a terceira 0.90. A pessoa toma decisão de deploy em cima de um número que tem ruído embutido e não sabe disso.

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
4. Um juiz LLM pontua cada resposta em faithfulness e context precision, repetindo a pontuação N vezes para medir a própria variância.
5. O relatório sai com cada métrica acompanhada do intervalo de confiança, mais custo e latência agregados e por pergunta.
6. No CI, o mesmo eval roda como teste e falha o build se uma métrica cruza o limite configurado.

## Stack

- Linguagem: Python 3.11
- Avaliação offline: Ollama via Docker
- Juiz e target: protocolo OpenAI-compat
- Testes e gate: pytest
- Lint e formatação: ruff

## Status atual

Pré-v1. Spec e ADRs definidos, implementação em andamento sob desenvolvimento orientado a spec. O caminho de execução offline com Ollama é o default desde o primeiro corte.

## O que não faz (ainda)

- Answer relevance e context recall ficam para a v2. A arquitetura de juiz já comporta, mas não estão no primeiro corte.
- Não tem dashboard de tendência temporal. O relatório é por execução. Histórico persistido e visualização vêm depois.
- Não compara múltiplos targets numa única execução. Isso entra quando o orquestrador que consome este harness precisar.
- Não substitui avaliação humana em casos de alta criticidade. Mede o que dá para medir de forma reproduzível e é honesto sobre a margem.

## Links

- Repositório: [TODO: preencher]
- Documentação técnica: ver `README.md` e `docs/`
- Decisões de arquitetura: ver `docs/adr/`
