# Etapa 6: design de alto nível (HLD) e POCs

Leitor: quem vai implementar. Exato: rotas, payloads, itens, condições de escrita, algoritmos e falhas. Condição antes da ação.

## Esqueleto

```
# High level design (HLD): <system>
Series: ...
## In one minute            answer, the ask to implementers and reviewers, the numbers the POCs proved
## What changed in revision N
## Components
## Interfaces               routes with method, path, auth, full request and response, errors with the caller's action
## Data                     the table, every item with keys and fields, retention/TTL, IAM least privilege
## Algorithms               one subsection each, id ALG# (A# is reserved for assumptions), pseudo-code in fenced blocks, conditions (e.g. DynamoDB ConditionExpression) written out
## Sequences                mermaid sequence per key scenario
## Failure modes            table: failure · detection · behaviour · recovery
## Configuration · ## Observability (log line, metrics, alarms, tracing, dashboard) · ## Security · ## Cost
## <Rollout>                stages, entry/exit criteria per stage (from BR#), kill switches, rollback
## Migration from the current state   steps by dependency, each with what blocks it (Q#)
## Tests                    unit, contract, load; what each proves
## Coverage                 table: R# / AC# / I# → where in this HLD → which test
## Technology choices       language and runtime, framework, libraries, IaC and delivery, tracing, test tools: options, criteria, choice
## Proof of concept results one subsection per POC + "What the proofs of concept leave open"
## Next steps · ## Assumptions · ## Open questions · ## Sources
```

## POCs

- Um POC prova um conceito, não uma feature: escreva a hipótese e o critério de aprovação antes de rodar. O critério precisa poder falhar: rode um controle negativo que quebra sem a proteção testada (sem lock compartilhado no harness, sem resultado montado para passar) e uma carga que consiga passar do limite que o POC diz provar. Sem a ferramenta de mock (moto, banco local), use um substituto e diga qual e o que ele não prova. Um POC com vários checks tem um controle por check, e o resumo diz quantos checks têm controle. Os dados sintéticos seguem os formatos do HLD (chave, id, linha de log); com outro formato o POC prova outra coisa.
- Local, sem nuvem: mocks (moto para DynamoDB, respx para HTTP, k6 para carga), dados sintéticos, nenhum telefone real. moto prova a forma da chamada, não a atomicidade: escrita condicional concorrente vai em DynamoDB Local, ou num banco local declarado como substituto.
- Teto de 5 minutos por POC; passou, reduza a carga e diga quanto.
- Resultado com número medido, comando para reproduzir e o que ficou aberto. Ex. da série original: draw estável entre estágios (qui-quadrado), first write wins com 40 threads, latência p95 adicionada sem banco, rotas novas com corrida venda × mensagem.
- Achado de POC que muda o design volta para a etapa certa (invariante na etapa 4, ADR na 5) e entra na cascata.

## Pronto quando

A tabela de cobertura liga todo R#, AC# e I# a um trecho do HLD e a um teste ou POC; toda rota tem exemplo completo; todo modo de falha tem detecção e recuperação.
