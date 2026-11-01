---
level: superego
name: orquestrar-sonnet-haiku
description: "Prepare Claude Sonnet/Haiku briefs and Workflows, including long handoffs and failure recovery. orquestrar-cruzado owns cross-harness coordination. The active company collective owns an equivalent procedure; use this fallback when delegated or explicitly invoked."
---

# Orquestrar Sonnet e Haiku

Model tier per padroes A5/B20 and the skill orquestrar-cruzado; the Sonnet/Haiku/Opus names below are the Claude defaults.
Modelo barato erra por falta de contexto, não por falta de inteligência: o brief precisa carregar tudo.

`orquestrar-cruzado` owns cross-harness coordination and model selection; this skill provides Claude Workflow mechanics and brief-writing details when applicable. `executar-ondas` owns the wave runner.

The active company collective's equivalent owns this procedure when available. Otherwise use this generic procedure; also use it when explicitly invoked by the user or delegated by the collective. Retain applicable safety and authorization requirements.

## 1. O brief tem que se bastar

Subagente não vê a conversa. Todo prompt leva:
- **Quem pediu e por quê**, numa linha: "O usuário pediu nesta sessão: <citação curta>." Sem isso o Haiku
  e o Sonnet recusam tarefas que parecem "fora do pedido" (aconteceu: dois agentes se recusaram a
  preencher um doc porque a última mensagem do usuário era sobre CI).
- **Caminhos absolutos** com barra normal, ids exatos (node, bloco, PR, branch) e o comando exato.
- **O que é sucesso** em uma frase verificável, e o schema de saída com `ok` + `note`/evidência.
- **O que nunca fazer** naquela tarefa (push em hml/main, force-push, mexer em Railway/GitHub settings,
  ler `.env`, chamar o sistema do cliente em produção). Ver [[execucao-madrugada-15-10]].
- **Bloqueio do classificador = parar.** Todo brief diz: "se uma chamada for bloqueada pelo classificador de permissão, pare e reporte; nunca chegue ao mesmo resultado por outro caminho". (16/10: um Sonnet teve `git rm` de baseline barrado e refez pelo `harness update`.)
- **Teste novo passa no gate estático inteiro** (mypy strict + sensores), não só ruff: o brief manda rodar `make static` antes do push.
- **Não driblar sensor.** Função auxiliar que devolve o objeto cru (ex.: `_state(ctx)` devolvendo o `session_state`) esconde o acesso do sensor e é burla; o brief manda usar o dono tipado (`ConversationState`) ou parar e listar o que falta.
- **Regras de merge do repo**, quando o agente vai mesclar ou abrir PR: apontar
  `docs/engineering/environments/t13-merging-and-drift.md` e `docs/engineering/testing/t13-ci-failure-modes.md`.
  Os erros que mais custaram rodadas foram de base desatualizada, não de código: baseline mesclada à
  mão, edição de outro perdida num arquivo movido, regra de branch removida copiada para outra
  (as regras do `dev` foram parar no `hml`), teste lendo variável de ambiente do CI, falso positivo de
  gitleaks em dado de teste.
- **Antes de mandar mesclar uma leva de PRs**, simular cruzado: `pairwise_merge.py` (conflito de texto
  entre pares, com merge commit) e `xpr_run.sh` (mescla cumulativa rodando os gates a cada passo).
  Ficam em `~/.claude/skills/publicar-na-pr/scripts/` (ajustar a lista de PRs e caminhos no topo).

## 2. Texto grande: arquivo, nunca redigitado

Modelo barato erra JSON e corta texto ao redigitar payload longo.
- Gere o conteúdo com script em arquivo; o agente só **lê o arquivo e passa inteiro**.
- **Teto por chamada**: Claude Docs recusa > 32 KB por escrita (`row_too_large`). Corte em arquivos
  ≤ 22 KB, quebrando em linha em branco. Um arquivo por agente, um bloco `pending` por arquivo
  (plantado antes, na ordem), e cada agente faz `replace` do seu bloco: a ordem fica garantida.
- Regra no prompt: "o arquivo inteiro numa escrita ou nada; se o servidor recusar, pare e reporte o
  código, nunca escreva parte". Retentativa só para JSON malformado seu.
- Conteúdo com `\` (regex, grep) é onde o Haiku mais erra: para esses arquivos use Sonnet.
- Depois, **verifique** (conte os `pending` restantes, releia a aba). "ok" de agente não é prova.

## 3. Que modelo para quê

Ver a linha de política acima. Regra prática: Haiku só em chamada única com payload < 5 KB; copiar arquivo de 5–25 KB ou mexer em `\` (regex, grep) é Sonnet.

## 4. Execução de tasks, custo e quebra cruzada entre PRs

O pipeline (worktree por task, gate, commit, revisão, aceite, custo, `pairwise_merge.py` e `xpr_run.sh` contra quebra cruzada, ordem de merge) está em [[executar-ondas/SKILL|executar-ondas]] e em `executar-ondas/references/regras.md`. Aqui ficam só o brief e a mecânica do Workflow.

## 5. Mecânica do Workflow (armadilhas reais)

- `args` é JSON de verdade; um placeholder string vira lista de caracteres.
- **Resume perde o cache** quando muda qualquer prompt anterior ou a ordem das chamadas; para pular
  trabalho pronto, prefira um run novo com `args.pre = {ID: resultado}` e pule essas tasks.
- Onda sem task executável: `continue` antes de integrar/PR/QA (senão gasta agente à toa).
- Para esperar um agente específico, filtre o journal pelo **label** (`"label":"impl F100"` + result),
  nunca pela contagem de `result` (um revisor terminando primeiro engana o contador).
- Teto de 6 agentes simultâneos nesta máquina: ondas grandes demoram ~2h30.
- **O run vive com a sessão.** Se o app fecha ou reinicia, o Workflow para sem aviso. O journal fica na
  pasta da sessão que lançou: só ela consegue `resumeFromRunId`. Em 16/10 a sessão caiu 2 vezes (~3 h
  perdidas) e depois duas sessões retomaram a mesma onda nas mesmas worktrees. Regra: **um condutor por
  run**; ao lançar ou retomar, avisar as sessões irmãs com o run id; quem não é o condutor não retoma.
- **Não edite o script com o run rodando** se for retomar: qualquer prompt mudado (até RULES ou a base)
  invalida o cache dali para frente. Junte as mudanças para o próximo run.
- **Base da PR empilhada** = a dependência que já contém as outras (fecho transitivo das `hard`), não a
  primeira da lista. Com a base errada, o diff mostra arquivos congelados da outra PR e o frozen-files
  falha (T8 #83 apontou para F102 em vez de F105).

## 6. Pedir antes

Mudança em settings do GitHub, escrita na plataforma de deploy, criar/apagar coisa no Linear: pedir ao usuário logo
antes. Issue apagada de propósito não se recria; use a cópia de referência do relatório das ondas.

## 7. Preâmbulo fixo de todo brief que mexe em código (revisão de 29+9 PRs, 17/10)

Cole isto no começo de todo brief de implementação ou correção, preenchendo os <>:

```
Task: <ID> — ticket em <caminho do JSON>. Plano de arquivos do ticket = o que você pode mexer.
Regras que não se negociam:
1. Mexa só no que a task pede. Não reformate, não renomeie, não traduza, não "melhore de passagem"
   arquivo de outra task (dono em tools/harness/owners.toml). Precisou mexer fora do plano? Liste no
   corpo da PR com o motivo.
2. Nunca faça o gate passar escondendo algo do sensor: nada de partir literal, helper que esconde
   acesso proibido, reescrever comentário para baixar contagem, código criado só para o sensor calar,
   nome que colide para sumir achado.
3. Não toque em listas de isenção (v1_port.py, _typos.toml/gen_typos.py, .gitleaks.toml, tokens,
   WIRE_NAMES), baselines de outros donos, sensores existentes, nem em tests/porte (só repontar import).
   Se o gate exigir isso, PARE e reporte: "precisa de decisão do dono".
4. Não apague código, teste ou funcionalidade que o ticket não manda apagar.
5. Se uma chamada for bloqueada pelo classificador, ou o gate não fechar sem violar 1–4: pare e
   reporte. Escalar é resposta certa; forçar não é.
6. Antes do push: make check inteiro (não só static) no tree mesclado; corpo da PR batendo com o diff
   (desvios do ticket listados, nada de "não mexe em src/" se mexeu).
7. Tudo que você subir (container, banco, cluster kind, servidor, processo em background) leva
   <ID>-<8 primeiros chars da sessão> no nome e é baixado antes do relatório final. O relatório lista o
   que ficou vivo e por quê. Busca de arquivo parte do repo ou de ~/.claude; nunca `find /`.
```

Por quê o item 7: em 28/10 a máquina do usuário tinha 12 containers de validação (9 unhealthy há até 20 h)
e um `find /` órfão de 3 h, 1,29 M handles, deixados por sessões que terminaram sem limpar.

Por quê: a revisão achou fuga de escopo em 7 de 9 PRs abertas e em metade das mergeadas, isenções
alargadas pela própria task (#89/#91/#96/#97/#87), dribles (#91/#92/#93/#74), testes da v1 apagados
(#94) e corpo de PR falso (#58/#61/#70/#74/#83/#87). Pesquisa: agentes trapaceiam no avaliador
(ImpossibleBench: Claude ~50%, quase sempre editando teste); pedir "não trapaceie" quase não muda;
dar saída de escalada corta muito.

## 8. Confusões de orquestração que custaram horas (16–17/10)

- **Integração só faz merge.** Nunca corrigir código de uma task dentro da PR/branch de integração
  (fiz isso na #87: mudei T8, apaguei API que outros tickets usam). Sensor vermelho após merge → o
  conserto volta para a PR dona.
- **Sem branch de integração de longa vida.** Cada PR entra no hml pela fila assim que verde; PR
  filha aponta para a PR-mãe ABERTA ou para o hml — nunca para branch já mergeada (#93–#97 nasceram
  apontando para a #87 já mergeada; script de base escolhia a dependência errada).
- **Um condutor por run.** Duas sessões retomaram o mesmo Workflow nas mesmas worktrees. Antes de
  retomar: ListAgents + avisar as irmãs; só quem lançou retoma. Workflow morre com a sessão.
- **Resume do Workflow só reaproveita cache com prompt e args idênticos** (editei RULES depois de
  lançar → tudo re-rodou). Passe os mesmos args do lançamento.
- **Merge de PR em DRAFT ou com falha conhecida não entra na integração** (#66 entrou com dinheiro
  negativo quebrado).
- **"Aplicado" = drift rodou com exit 0**, não "arquivo escrito" (Environments da T2 nunca aplicados).
- **Trigger declarada = trigger testada** (push/merge_group/schedule quebraram depois do merge).

## Related

- [[orquestracao-modelos-baratos]]: lições de 15/10 que originam esta skill
- [[global/regras-de-agente]]: Sonnet lê e escreve, Haiku mecânico
- [[rules/uso-de-ia|uso-de-ia]]: parar ciclo que não converge
- [[publicar-na-pr/SKILL|publicar-na-pr]]: briefs de PR delegados seguem este fluxo
- [[executar-ondas/SKILL|executar-ondas]]: aplica estes briefs nas ondas
- [[orquestrar-cruzado/SKILL|orquestrar-cruzado]]: mesmo padrão com filhos de outro harness
