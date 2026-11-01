# Etapa 5: arquitetura de alto nível (HLA) com ADRs

Leitor: revisor da plataforma que aprova a arquitetura. Estrutura arc42 + C4, enxuta.

## Esqueleto

```
# High level architecture (HLA): <system>
Series: ...
## In one minute            decision, ask to reviewers (approve the architecture and ADRs), key numbers, open items
## What changed in revision N
## Goals · ## Constraints   constraints cite AS# and team decisions
## Context and scope        C4 context diagram (mermaid)
## Traffic through the <component>   every webhook, event and destination that passes AND that does not pass, diagram + table
## Solution strategy · ## Building blocks (C4 containers)
## Runtime views            one subsection per scenario: happy path, reverse events, kills, outage, bypass, scheduled sends...
## Deployment               per environment (dev / HML / PRD)
## Cross-cutting concepts · ## Observability and monitoring   logs (no PII, retention), metrics, alarms → destination, dashboard, tracing
## Cost and hosting decision   1-3-1: one problem, three options, one recommendation; price list with date; volume basis with source; crossover
### Public benchmarks (summary)   3 rows + link to the market study
## Technology choices (summary)   language, runtime, IaC, test tools: options, criteria, decision; detail in the HLD; each decision becomes an ADR
## Decisions to record as ADRs     table ADR-#: "We will ..." · basis · alternatives and why they lose · negative consequences
## Quality scenarios · ## Risks and technical debt (K#) · ## Assumptions added · ## Open questions · ## Future possibilities
```

## Custo 1-3-1

1. Preço público do provedor por região (ex.: `curl` da price list JSON da AWS, guarde o arquivo com data). Nada de preço de memória.
2. Volume de hoje e de alvo com fonte (dados do negócio, arquivo de capacidade no commit). Unidades derivadas explícitas (ex.: 7,75 turnos por lead × 6 callbacks por turno).
3. Três opções com o custo por linha (compute, requests, gateway, banco, logs, métricas e alarmes) hoje e no alvo, o ponto de cruzamento e o que mudaria a decisão. Cada linha tem preço ou NOT PRICED com teto e Q#. A topologia com preço é a da seção Deployment (número de tasks, load balancer, NAT, banco, tráfego de saída). Sem volume alvo dos donos, use 1×, 10× e 100× do volume de hoje. Cite o arquivo da price list e o SKU de cada preço. Use o primeiro tier on-demand, sem free tier, e diga se o volume alvo passa de um tier. Os totais da tabela saem do script de custo salvo, sem conta à mão. Códigos da price list da AWS: `AWSLambda`, `AmazonApiGateway`, `AmazonDynamoDB`, `AmazonCloudWatch`, `AmazonECS` (Fargate), `AWSELB`, `AmazonRDS`, `AmazonSQS`, `AmazonSNS`, `AWSSecretsManager`; NAT Gateway e tráfego de saída ficam em `AmazonEC2` (arquivo grande: filtre por `usagetype` com `NatGateway` e `DataTransfer-Out`).
4. Decida (quando o usuário pede decisão) e escreva a ADR.

## Como escolher a tecnologia (vai para a seção Technology choices)

Compare linguagem, runtime, framework, bibliotecas, IaC e ferramentas de teste por critérios ditos (cold start, maturidade, o que o time já usa, custo de operação) e decida; o detalhe vai para o HLD, a decisão vira ADR.

## Pronto quando

Cada ADR diz "We will ...", tem a alternativa mais forte e por que perde, e a consequência negativa; o custo tem fonte de preço e de volume; o diagrama de tráfego cobre tudo que passa e o que não passa.
