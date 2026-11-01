---
level: superego
name: code-review-critico
description: "Review a branch before push through four lenses, scope audit and corrections. Use for code review bem crítico or revisa antes de subir; review-pr owns reviewer comments. The active company collective owns an equivalent procedure; use this fallback when delegated or explicitly invoked."
---

# Code review crítico

O review acontece ANTES do push. Um push sem review já precisou de pedido de desculpas.

This is the author-side critical review before push. For a review of an existing PR and its comments, use `review-pr`; `publicar-na-pr` owns the authorized publication workflow.

The active company collective's equivalent owns this procedure when available. Otherwise use this generic procedure; also use it when explicitly invoked by the user or delegated by the collective. Retain applicable safety and authorization requirements.

## 1. Escopo

Defina a base (branch alvo da PR) e liste o diff (`git diff --stat <base>...HEAD`). Se houve merge de outra
branch, separe o que veio de lá do que é desta task.

## 2. Revisores em paralelo (Agent, só leitura, mesma mensagem)

Cada um recebe a lista de arquivos, o objetivo da task e o AGENTS.md; devolve achados com arquivo:linha,
severidade, cenário concreto de falha e correção sugerida.
- **CR1 bugs e comportamento**: caminhos de erro, fail-open, estado por run não limpo, concorrência, regressão
  de testes, regex apagando resposta.
- **CR2 arquitetura (Google eng-practices)**: design, camadas/catraca, duplicação, nomes, complexidade,
  testes que testam o que importa, código morto. Aplique as métricas de `ub-mode` aos arquivos do diff
  quando as ferramentas estiverem disponíveis.
- **CR3 prompts e regras**: contradições entre prompt, regras condensadas, docstrings de ferramenta e código;
  instruções que o modelo não consegue cumprir; tamanho do prompt.
- **CR4 escopo, segurança e higiene**: cada hunk pertence à task? instrumentação, artefatos de lab, `.env`,
  segredos, dados reais em teste, arquivos formatados à toa, mudanças de outra branch. Subtração que a mudança
  exige, pinada por teste e com a suíte provando que o comportamento não mudou, pertence à task (ub-mode,
  Subtract Before You Add); refatoração solta continua achado.

## 3. Triagem e correção

- Verifique cada achado (leia o código) antes de aceitar; descarte falso positivo dizendo por quê.
- Para cada achado aceito, pergunte por que ele passou e onde nasce (skill `causa-raiz`): o mesmo padrão em
  vários arquivos se corrige na origem (helper, template, prompt), e o achado ganha uma trava (lint ou teste).
- Corrija o que é desta task. O que é de outra task: reverta daqui e registre como tarefa separada.
- Decisões de produto sem resposta óbvia: siga o comportamento de produção (v1) e registre.
- Correções em paralelo por subagentes só com escopo de arquivos disjunto.
- Formate/lint só os trechos alterados (a base pode já estar suja; formatar tudo polui o diff).
- Rode testes focados e a suíte completa.

## 4. Relato

Tabela curta: achado → severidade → feito / descartado (motivo) / adiado (onde ficou registrado). Liste os
follow-ups de arquitetura não feitos. Siga as regras globais para commit local; push e publicação exigem
autorização (skill `publicar-na-pr`).

## Related

- [[publicar-na-pr/SKILL|publicar-na-pr]]: commit e push depois do review
- [[review-pr/SKILL|review-pr]]: review de PR publicado em comentários
- [[rules/uso-de-ia|uso-de-ia]]: parar ciclo de revisão que não converge
- [[aprendizados-revisao-prs-17-10]]: escopo, dribles e isenções achados em revisões
- A régua de arquitetura do usuário (memória do nível id, quando existir): critérios que o revisor CR2 aplica
- [[todo-comentario-vira-lint]]: achado recorrente vira lint ou teste
- [[ub-mode/SKILL|ub-mode]]: métricas (CRAP, duplicação, mutação) e o que conta como subtração em escopo
