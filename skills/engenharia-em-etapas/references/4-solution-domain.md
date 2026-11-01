# Etapa 4: domínio da solução (RFC)

Leitor: engenheiro que confere o modelo de domínio antes da arquitetura. Ainda sem tecnologia: contextos, agregados, invariantes, comandos, políticas e onde a peça fica (posicionamento).

## Esqueleto

```
# RFC: <topic>, solution domain
Series: ...
## In one minute · ## What changed in revision N · ## Conventions
## From subdomains to bounded contexts   one context per subdomain, or the reason for merging
## Context map              upstream/downstream, conformist, anticorruption layer; who calls whom
## Ownership by context     matrix: context × data it owns × who may write
## Aggregates               one subsection each: purpose, fields, invariants I#, lifecycle
### Removed aggregates      "Removed in revision N: <reason>"
## Commands and domain events   command → aggregate → events; who may issue it (e.g. only the owning Variant)
## Policies                 forward, tracing, outage, kill, sale end, pin: each as WHEN/IF ... THEN
## Measurement              exposure log, comparison report, who builds it
## Decision: placement (ADR-# or D#)   options A to E with pros and cons; the decision and why; Background: the options compared
## Prior art (summary)      3 lines + link to the market study
## Assumptions · ## Open questions · ## Next steps
```

## Como fazer

1. Trace: cada BR# e R# da etapa 1 e cada AS# do as-is → agregado, invariante, comando ou política. Requisito sem casa é buraco; elemento sem requisito é orphan (remova ou justifique).
2. Invariantes testáveis: cada I# vira depois um teste ou condição de escrita no HLD (ex.: "first write wins", "a sale-ended Assignment never comes back").
3. Opções de posicionamento neutras quando outros decidem (B8). Com decisão do time, registre "Team decision, data" e mova as opções para Background.
4. Política de concorrência explícita: o que acontece quando dois eventos chegam juntos (venda × nova mensagem, status atrasado × mais novo).

## Pronto quando

Todo R# tem um elemento do modelo, todo comando diz quem pode emiti-lo, e cada invariante tem como ser verificada.
