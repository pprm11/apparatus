---
level: superego
name: orquestrar-cruzado
description: "Coordinate parallel work or second opinions across Claude Code and Codex, with model selection, self-contained briefs, isolated writers and a budget ceiling. Use for portable or cross-harness orchestration; orquestrar-sonnet-haiku supplies Claude Workflow mechanics."
---

# orquestrar-cruzado (B20)

The orchestrator plans, briefs, checks and integrates. Children do the work. Choose the model and harness
for the task, availability and approved budget. Balance Luna, Terra and Claude; there is no requirement
to use the other harness, send every task to Claude, or use every model. The user authorized this standing
choice. An explicit request for a model still applies. Independent review should use a
different model when that adds useful independence.

## Steps

1. **Split** the task into pieces that touch disjoint files and need no result from each other. Pieces that
   depend on each other run in sequence. Two children never write the same file.
2. **Brief** each piece in a file. A child knows only the brief:
   - Goal: what changes when it is done (one sentence).
   - Where: repo, branch, files to read and files allowed to change.
   - Acceptance: the command or observable signal (`make check`, a test name, "34 of 35").
   - Out of scope, and what to do when blocked (stop and report, do not improvise).
   - Facts it cannot rediscover cheaply: decisions, ids, constraints, with sources.
   For long briefs follow the `orquestrar-sonnet-haiku` rules when that skill is available.
3. **Pick the model and tier** (A5, B20): Luna for mechanical and cheap work (run, rename, collect), Terra
   for implementation and technical review, Claude when useful for a second opinion. Use `cheap` / low
   for mechanical work, `mid` / medium to read and write, and `top` / high or xhigh for final judgement.
   Say the actual model and effort. If unavailable, report the substitute. Writers need their own
   worktree; the CLI's `--write` creates one on branch `delegate/<run-id>`.
4. **Run** with the harness's native child tool when it exposes the chosen model, or use the CLI below
   for cross-harness work. In Codex, use native subagents for task pieces; `create_thread` is only for a
   separate user-requested session. Explicit model selection may require a self-contained, no-history
   child (`fork_turns="none"`). Never assume a helper option exists without checking its help.
   ```bash
   python -I ~/Codes/superego/tools/delegate.py run --brief-file brief.md --cwd <repo> --tier mid --write --background
   python -I ~/Codes/superego/tools/delegate.py status <run-id>
   ```
   `--to` defaults to the other harness; pass `--to claude` or `--to codex` deliberately. This helper's
   Codex tier changes reasoning effort on its configured model; it does not select Luna or Terra.
   Verify the recorded command before naming the model. Claude children
   stop at `--budget` (default by tier); Codex children stop at `--timeout` minutes. Use `--background`
   for anything over a couple of minutes, and do not poll in a tight loop: check when you have nothing else
   to do, or once per few minutes.
5. **Verify** before reporting. The child's final message is a claim, not proof: read the diff in its
   worktree, run the acceptance command yourself, and say what you checked.
6. **Integrate**: merge or cherry-pick the child's branch into the working branch only within what the user
   allowed. Follow global rules for local commits; push and publication require authorization. Follow global
   controls for PR and merge. Remove finished worktrees
   (`git worktree remove`).

## Limits

- Depth 1: children cannot delegate. The CLI enforces `DELEGATE_DEPTH`; native-child briefs must prohibit
  further delegation explicitly.
- Teto (C): at most 10 children per task unless the user sets another number. Say up front how many children
  will run, in which harness and tier, and what the user gets at the end (B4).
- Switching model or harness does not reset or increase an approved child, cost or time ceiling.
- If two rounds of child fixes do not reduce the open problems, stop and ask (rule `uso-de-ia`).
- Runs are kept in `~/Codes/superego/runs/<run-id>/` (brief, command, log, final message, changed
  files), never committed. They may hold code and client data.

## Regras de orquestração e sessões

Regras sempre válidas (antes ficavam em `rules/agentes-e-sessoes.md`; a regra curta aponta para cá).

## Orquestração e sessões

- Um condutor por execução de ondas ou workflow; passe o id às irmãs ao lançar/retomar. Quem não conduz não retoma nem sobe nas branches da onda.
- Execução longa: app aberto; não edite o script com ela viva.
- O orquestrador delega: CI, conflito e comentário vão à sessão dona da branch.
- Arquive a filha terminada sem perguntar (pedido do usuário, 30/10/2026). A cada aviso de filha, liste as sessões ligadas e arquive as que terminaram. Terminada é a filha com a PR mergeada ou fechada, a pergunta respondida, ou que só espera um evento externo que uma sessão nova pode retomar.
  - Antes de arquivar, confira a worktree: `git status` só com saída de build sem rastreio e nenhum commit faltando no upstream. O que valer guardar é copiado antes, porque arquivar apaga a worktree.
  - Não arquive filha que espera o usuário nem filha com trabalho não salvo. Filha de outra sessão é arquivada pelo pai dela: repasse o pedido.
  - Informe cada arquivamento numa linha.
  - No Claude Code use `archive_session`. Em harness sem ferramenta de arquivar, como o Codex, liste ao usuário as threads terminadas para ele arquivar.
- Antes de editar repo compartilhado: git status e liste sessões; um escritor por arquivo.

## Push e aprovação

- Gate otimista: checagem estática e testes da área; CI é o gate real.
- Proteja o CI: poucos pipelines, um push por rodada, sem CI repetido sem mudança, corpo editado em lote.
- Para push após aprovação válida, siga os controles globais de aprovação e de PR empilhada.

## Qualidade de código

- Comentário de revisão ou achado recorrente vira lint ou teste.
- Devolva cada ponto com id, commit e caminho do lint ou teste.
- Não contorne bloqueio nem sensor: pare e rode make check.
- Simule a leva de PRs antes do merge.

## Modelos e custo

- Barato no mecânico, médio no código, topo na 1ª revisão.
- Brief autossuficiente: pedido do usuário e instrução de relatar o lido e o omitido.
- Critério de aceite fixo antes de soltar; após mudar o prompt, sem resume.
- Falha de base não derruba as dependentes; sem bloqueante após 3 rodadas, PR com checklist.
- Uma sessão por fase; status curto por subagente.

## Related

- [[orquestrar-sonnet-haiku/SKILL|orquestrar-sonnet-haiku]]: briefs autossuficientes para os filhos
- [[rules/uso-de-ia|uso-de-ia]]: para o ciclo de revisão que não converge
- [[global/regras-de-agente]]: model explícito e teto de custo
- [[global/regras-de-agente]]: regra vale nos dois harness
- [[orquestrador-nao-toca-codigo]]: quem orquestra delega e verifica
