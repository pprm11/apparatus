# Etapa 1: domínio do problema (RFC)

Leitor: quem decide se o problema e os requisitos estão certos (time de plataforma, dono do negócio). Esta etapa é a fonte de todas as outras e não escolhe tecnologia.

## Esqueleto (headings em inglês, nesta ordem)

```
# RFC: <topic>, problem domain
Status · Date · Author · Decision owners
Series: 1 problem domain (this document) · 2 [as-is](...) · 3 [market study](...) · 4 [solution domain](...) · 5 [HLA](...) · 6 [HLD](...) · [README](...)

## In one minute            answer + ask + the 3 rules that matter + what is still open (with owner)
## What changed in revision N
## Conventions              BCP 14 keywords (MUST/SHOULD/MAY), EARS (WHEN, WHILE, IF ... THEN), ID kinds
## Motivation               what breaks today, who feels it, cost of doing nothing
## Goals and non-goals      G#, N#
## Assumptions              A#: working answers, each with what would change if wrong
## Context
### Current state           short; the detail lives in the as-is stage
### Decisions of <date> that shape the problem   "Team decision, DD/MM/YYYY", no quotes, no names
### <Flow around one unit of work>               e.g. traffic around one Conversation
## Problem domain
### Subdomains              core / supporting / generic
### Glossary                market-standard names first (Variant, Unit, Assignment, Allocation, Canary release...)
### Event classes           MECE: every event belongs to exactly one class
### Business rules          BR#: rule, then reason with its number and source
## Requirements             R#, in EARS, each tracing to a BR# or G#
### Quality scenarios       QS#: source, stimulus, environment, response, measure (with source for the number)
## Profiles                 contract + the first concrete profile (e.g. Ariadne) + its acceptance checks AC#
## Cross-cutting concerns   privacy, compliance, observability, retention
## Open questions           Q#: question, owner, what changes with each answer
## Next steps               next stage first, by dependency, no dates
```

## Como chegar lá

1. Comece pelas perguntas para os donos. Salve o rascunho com as perguntas como revisão 1 (`evidence/problem-r1-before-answers.md`) e grave quando as respostas foram lidas (`evidence/answers-read-at.txt`); aplique as respostas como revisão 2, liste cada D# em "What changed in revision 2" e diga qual Q# cada D# fecha. As perguntas: o que só o negócio ou a plataforma responde (tempo de vida da atribuição, volume, critérios de estágio, rollback). Liste em Q# com dono, mande o usuário perguntar, e grave cada resposta no arquivo de decisões. Em execução autônoma (sem o usuário), as perguntas ficam na etapa 1 e no arquivo de decisões como "pending", e a série segue com as A# de trabalho.
2. Glossário com nomes de mercado (Statsig, LaunchDarkly, Argo Rollouts usam Variant/Unit/Allocation/Canary). Termo da casa que colide com outro sistema muda de nome ("pause" colidia com a pausa do Relay: virou soft kill / hard kill).
3. Checagem MECE: vocabulário (um termo por conceito, sem sobreposição), subdomínios e classes de evento (cada evento numa classe só, nenhum fora). Registre o resultado no README.
4. Rastreabilidade interna: cada R# aponta para um BR# ou G#; cada BR# tem pelo menos um AC#; cada Q# respondido por decisão do time sai de Open e entra em Decided.
5. Números de volume e custo vêm com fonte (arquivo do repo no commit, base de dados do negócio com data).

## Pronto quando

Um leitor frio responde, só com o documento: qual problema, para quem, que regras valem, como saber que está certo (AC#) e o que ainda depende de quem.
