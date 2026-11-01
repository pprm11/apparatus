---
level: superego
name: telinhas
description: Responde ao usuário com widgets visuais inline (show_widget) para status, planos, filas de tasks, comparações, resultados de bateria e números. Use sempre que a resposta tiver progresso, lista de tarefas ou ondas, comparação de opções, métricas ou plano. Não use em resposta de uma linha.
---

# Telinhas

O usuário pediu que as respostas venham com telinhas visuais bonitinhas, não só texto
e tabela. A ferramenta é `mcp__visualize__show_widget` (HTML/SVG inline no chat).

## Como

1. Na primeira telinha da sessão, chame `mcp__visualize__read_me` (módulos conforme o caso: `mockup` para
   cards/dashboards, `chart` para gráficos, `diagram` para fluxos/dependências) — em silêncio, sem narrar.
2. Uma telinha por resposta, no máximo duas. O texto explicativo fica FORA do widget, na resposta, curto
   (régua do [[global/regras-de-agente]]: simples, frações, exemplos).
3. Formatos que funcionam para ele:
   - **Status de execução** (workflow, ondas, PRs): linha de metric cards (feitos / rodando / falhou /
     faltam + ETA) e, abaixo, uma lista por etapa com ícone de estado (`ti-check`, `ti-loader-2`,
     `ti-alert-triangle`, `ti-clock`) e uma barra fina de progresso.
   - **Plano / ondas / dependências**: diagrama SVG em colunas por onda, fundações primeiro, setas para
     dependências fortes; cor por categoria (fundação, rodar a v2, correção, refactor), ≤ 2–3 rampas.
   - **Comparação de opções**: cards lado a lado, o recomendado com borda de destaque e badge.
   - **Resultados** (bateria, load test, auditoria): KPI row + gráfico de barras/linha simples; tabela
     detalhada continua em markdown na resposta.
   - **Ambiente** (Railway, conectores, CI): card por serviço com estado (online, falhou, faltando config).
4. Botões com `sendPrompt()` para o próximo passo provável ("Ver PRs da onda 1 ↗", "Rodar QA de novo ↗").
5. Regras do design system: plano, sem gradiente/sombra, cores via variáveis CSS (modo escuro obrigatório),
   sentence case, sem emoji (ícones Tabler outline), números arredondados, nada de `position: fixed`.

## Não faça

- Não substitua a resposta em texto pela telinha: o texto diz o essencial; a telinha mostra.
- Não ponha dado real de lead (telefone, CPF, nome) em telinha.
- Não invente número: tudo que aparece veio de uma ferramenta nesta sessão.

## Related

- [[global/CLAUDE|CLAUDE]]: regra global que pede telinhas
- [[global/regras-de-agente]]: formato de resposta e tabela de sempre
- [[medir-feedback/SKILL|medir-feedback]]: placar entregue em telinha
- [[pdi/SKILL|pdi]]: check-in de sexta usa telinha
- [[executar-ondas/SKILL|executar-ondas]]: status de ondas em telinha
