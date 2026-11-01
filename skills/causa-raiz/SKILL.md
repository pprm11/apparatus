---
level: superego
name: causa-raiz
description: "Diagnose an error, bug, CI failure or recurring rework: reproduce it, use Ishikawa and causal questions, prove the root cause and distinguish correction, containment and prevention. Use for causa raiz, Ishikawa or 5 porquês; measured correction decisions are handled by ciclo-correcao-decisao."
---

# Causa raiz (Ishikawa)

Corrigir o sintoma faz o problema voltar com outra cara. A ordem é fixa: problema → espinha → porquês → prova →
correção da raiz → trava. Solução só aparece no passo 5; antes dele, toda ideia de solução é reescrita como causa
("falta retry" vira "a chamada não trata 503").

`causa-raiz` owns diagnosis and proof. For a measured correction cycle and its decisions after diagnosis, use `ciclo-correcao-decisao`.

## 1. Problema (cabeça do peixe)

Uma frase observável com o quê, onde, desde quando e quanto (casos, %), com fonte. Sem causa e sem solução nela.
"O CI falha" não serve; "o check `test-domain` falha em 4 de 10 runs desde a #212, com timeout no Postgres" serve. Reproduza o problema antes de seguir (ub-mode, Fix Root Causes): sem
reprodução, o passo 4 não tem prova.

## 2. Espinha (6 categorias)

| Categoria | Em software e agentes |
|---|---|
| Método | processo, fluxo, ordem dos passos, regra de negócio, prompt, brief |
| Máquina | código, ferramenta, dependência, infra, modelo |
| Material | dado de entrada, estado, config, fixture, conversa do lote |
| Mão de obra | quem executou (pessoa, agente, subagente): contexto que faltou, handoff, conhecimento |
| Medida | teste, eval, juiz, régua, métrica, monitoramento (inclui o erro do teste) |
| Meio | ambiente (dev / HML / PRD), rede, versão, horário, concorrência, CI |

Em cada categoria, liste as causas candidatas ou escreva "nada encontrado". Marque cada uma como **fato** (com
arquivo e linha, commit, log ou comando) ou **hipótese**. Leia antes de supor: código, diff, logs, histórico.

## 3. Porquês

Nas 1 a 3 causas com mais evidência, pergunte "por quê?" até chegar a uma causa que:
- está sob controle do time;
- removida, impede a volta deste problema e dos parecidos;
- não é só "erro humano" ou "o agente errou": pergunte por que o processo deixou o erro passar.

Costuma levar 3 a 5 níveis. Se a cadeia sair do controle do time (fornecedor, cliente), pare ali e registre.

## 4. Prova

Antes de corrigir, prove a raiz: reproduza, ache o commit que introduziu, conte quantos casos ela explica. Raiz que
explica menos da metade dos casos não é a única: volte à espinha. Várias raízes são legítimas; ordene por casos.
Mudança que aconteceu junto com o problema é correlação, não prova.

## 5. Correção

Classifique cada ação proposta:
- **raiz**: remove a causa provada.
- **contenção**: segura o sintoma enquanto a raiz não sai (retry, timeout maior, regex, `skip`, `if` para o caso,
  rollback). Só com o rótulo "contenção" e uma task registrada para a raiz. Guard que só esconde o erro
  (`except` que engole, `if` que pula o caso sem registrar) não é contenção: é remendo e vira achado (ub-mode).
- **trava**: impede a volta (lint, teste, gate, regra no contexto). Toda raiz corrigida ganha uma trava.

Entrega só com contenção é falha, salvo quando a raiz está fora do escopo ou do controle: diga isso e registre.
Opções em menu (1-3-1) seguem a mesma regra: cada opção diz se é raiz ou contenção, e a recomendação ataca a raiz.

## 6. Entrega

Problema; espinha em tabela (categoria → causa → fato ou hipótese → fonte), ou em diagrama numa telinha quando houver
3 ou mais causas; a cadeia de porquês; a raiz e a prova; as ações com o rótulo. Escale ao tamanho: um bug pequeno
cabe em 5 linhas, um incidente ou o resultado de uma bateria pede a tabela inteira.

Dispensa: typo, ou erro cuja causa única o próprio stack trace prova. Mesmo assim, responda "por que isso passou?"
para decidir a trava.

## Armadilhas

- Parar no primeiro porquê ("o teste falhou porque o mock estava errado").
- Diagrama que é lista de soluções disfarçada.
- Agrupar por sintoma e chamar de causa (dez erros de "cidade errada" podem ter três raízes diferentes).
- Corrigir o mesmo padrão arquivo por arquivo quando a origem é uma só (gerador, template, prompt, helper).

## Related

- [[ciclo-correcao-decisao/SKILL|ciclo-correcao-decisao]]: o diagnóstico de cada causa usa esta skill
- [[code-review-critico/SKILL|code-review-critico]]: achado aceito pergunta por que passou
- [[todo-comentario-vira-lint]]: a trava de achado recorrente
- [[telinhas/SKILL|telinhas]]: diagrama da espinha
- [[ub-mode/SKILL|ub-mode]]: reproduzir, corrigir a causa, nunca esconder o erro
