### Adaptador: Claude Code

- Telinha: skill `telinhas` com `mcp__visualize__show_widget`; chame `mcp__visualize__read_me` em
  silêncio na primeira vez da sessão.
- Níveis de modelo (A5, B11): barato = Haiku, médio = Sonnet, topo = Opus. Passe `model` em todo
  `Agent`, `Workflow` e `start_session`.
- Subagentes (B20): combine Luna, Terra e Claude conforme a tarefa, a disponibilidade e o teto aprovado;
  o outro harness é uma opção, e não uma obrigação. Luna cobre trabalho mecânico e barato; Terra cobre
  implementação e revisão técnica; Claude traz uma segunda opinião quando útil. No mesmo harness use
  `Agent`; multiagente com `Workflow` (skills `executar-ondas` e `orquestrar-sonnet-haiku`, só neste harness).
  Para filhos no Codex: `python -I ~/Codes/superego/tools/delegate.py run --brief-file <f> --cwd <repo>
  --to codex --tier mid [--write] [--background]`. Esse helper usa o modelo configurado no Codex e ajusta
  o esforço; confira o comando para saber o modelo efetivo. Não invente uma opção de modelo do helper.
  Use seleção explícita de Luna/Terra quando a ferramenta disponível permitir; informe qualquer substituto.
- Orquestrador roteia, filho avisa: filha com `start_session`; aviso ao pai por `SendMessage` para o id
  em `startedBy` (`list_sessions` com `linked: true`).
- Caixa de decisões (B22): página fixa em `~/.claude/decisions/config.json` (`page_url`). Para atualizar a
  página: `python -I ~/Codes/superego/tools/decisions.py html > <arquivo>.html` e publique com a
  ferramenta `Artifact` passando esse `url`. Sessões do Claude arquivam com `archive_session`.
- Hooks ativos: `hook-prompt-guard.py` (segredo no prompt), `hook-bash-guard.py` (nega `find`, `grep -r`,
  `rg`, `ls -R`, `du` e `tree` a partir de `/`, `/proc` ou do disco inteiro; corpus em
  `test_hook_bash_guard.py`) e `index_hook.py` (refaz o índice de busca quando uma memória, regra ou skill é
  gravada). O job de hora em hora roda `tools/machine_guard.py hourly` (mata busca órfã, alarme de handles).
- Memória: o próprio harness carrega o `MEMORY.md` do projeto; para gravar, siga a skill `context-ingest`.
- Jobs: `ClaudeContextSync` (de hora em hora) e `ClaudeContextWeekly` (segunda 09:00) rodam com o
  login do Claude. Ver o README do repo meta.
