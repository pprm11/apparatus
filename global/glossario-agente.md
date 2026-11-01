# Glossário de agente (nível superego)

Versão: v1.1, 30/10/2026. Cada camada tem um glossário neste formato (campo `glossary` do `layer.json`),
carregado na ordem superego, collective, ego, id; em conflito vale o da camada mais específica.

## Regras de uso

1. Use o termo padrão do glossário, mesmo que o usuário escreva outro.
2. Corrija só se o termo, lido de dois jeitos, mudaria a ação.
   - No começo: "Você disse X; entendi Y (padrão: Z)." Uma por resposta.
   - Irreversível ou externa: pergunte antes.
3. Não corrija sinônimo inócuo, acento, caixa, digitação, apelido nem texto colado.
4. Identificadores ficam como estão: branches, repos, tools, perfis de nuvem, código.
5. Conceito novo ou termo trocado: pergunte "Adiciono/troco X no glossário?"; edite após o sim, com nova versão.

## Colisões (mesma palavra, coisas diferentes)

| Palavra | Sentidos | Termo padrão |
|---|---|---|
| harness | gates, guias e sensores de um repo · o agente de código que roda a sessão | **harness do repo** · **harness** |
| agente | agente de código (Claude Code, Codex) · agente que a sessão dispara · agente de um produto | **harness** · **subagente** · **agente** |
| dev | ambiente · máquina · pessoa | **dev** · **local** · **desenvolvedor** |
| regra | regra de engenharia (lint, CI, revisão) · regra de negócio de um produto | **regra de engenharia** · **regra de negócio** |

## Termos padrão

### Camadas do contexto
- **superego**: regras gerais de agente, iguais para qualquer pessoa ou empresa. **collective**: o que um
  time compartilha. **ego**: uma empresa, uma camada por empresa. **id**: a pessoa (preferências, PDI, vida
  fora do trabalho), privado, cifrado onde preciso. **psique**: repo meta com o **manifesto** (`manifest.json`)
  que lista as camadas e gera o `CLAUDE.md`. **camada**: um desses repos. **nível**: o `level:` de memória e
  skill, que diz a camada dela.

### Trabalho e decisão
- **task** (T#): unidade de trabalho. **card**: texto da task. **ticket**: registro da task no tracker.
- **onda**: lote de tasks por dependência, sem data. **rodada**: volta de revisão na onda. **run**: execução de Workflow. **plano**: documento com quê, porquê e ondas. **backlog**: tasks fora de onda.
- **critério de aceite**: sinal observável de pronto. **bloqueio**: depende de outra pessoa ou sistema. **pendência**: item aberto.
- **Q# / D# / I#**: pergunta aberta / decisão / ideia. **matriz de decisão**: opções com critérios (inclui 1-3-1).
- **Ishikawa**: causas de um problema em 6 categorias, com porquês até a raiz provada (skill `causa-raiz`). **causa raiz**: causa que, removida, impede a volta do problema. **contenção**: remendo no sintoma enquanto a raiz não sai. **trava**: lint, teste ou regra que impede a volta.

### Teste e qualidade
- **teste**: offline, sem modelo. **eval**: suíte com modelo real. **eval-gate**: subconjunto do eval que bloqueia PR. **gate**: checagem que bloqueia merge. **juiz**: LLM que avalia a resposta.
- **TDD**: teste que falha antes, menor mudança que passa, refatora. **CRAP**: CC² × (1 − cobertura)³ + CC por função, teto 10. **mutante sobrevivente**: mutação do código que nenhum teste pega.

### Sessões e entregáveis
- **sessão**: conversa do Claude Code ou Codex. **subagente**: agente que a sessão dispara. **handoff**: texto para continuar em outra sessão. **compact**: `/compact`. Modelos sempre pelo nome.
- **artefato**: página publicada no claude.ai. **relatório**: análise escrita, publicável como artefato. **telinha**: widget inline.

## Como interpretar pedidos
- **deploy**: levar uma versão a um ambiente. **sobe local**: iniciar servidor na máquina. **roda**: executar teste ou script. **publica**: artefato ou documento.
