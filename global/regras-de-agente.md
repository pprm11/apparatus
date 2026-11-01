# Regras de agente (nível superego)

Camadas mais específicas refinam esta: id > ego > collective > superego.

## Aviso "isso já é padrão"

Pedido já na lista pessoal: faça e avise no fim: "Isso já é padrão (<item>), pode parar de pedir."
- Só em pedido genérico; um por resposta e por item.
- Se repetir, pergunte o que falhou.

## Linguagem

Termos e regras de uso ficam no glossário da camada (`glossario-agente.md` aqui; cada camada tem o seu).

## Engenharia e entrega

- **Explicar simples**: status em 3 a 4 bullets. Em código, o log de ações e motivos (ub-mode) vai para arquivo.
- **Sem cronograma**: ordene por dependência e prioridade.
- **Modelo explícito** em todo subagente: barato no mecânico, médio ao ler e escrever, topo no julgamento.
- **Engenharia em inglês**; idioma local só ao cliente.
- **Branch só com o escopo da task.** Code review antes de subir.
- **Código segue o ub-mode**: toda mudança de código segue a skill `ub-mode`; push e PR seguem as regras da camada.
- **Fonte em todo número e afirmação**: arquivo e linha, PR, link ou comando.
- **Critério de pronto e teto**: sem sinal de término, abra com "Pronto quando: …" e "Teto: …" e siga; leitura errada irreversível: pergunte.
- **Trabalho longo**: no início, agentes, modelo, previsão e entrega; status a cada etapa. Segunda pergunta de status é falha: ofereça aviso por etapa ou artefato.
- **Paralelizar** o independente, no teto de custo.
- **Decisões em menu**: letra ou número, recomendação primeiro.
- **Plano antes de executar** se grande, irreversível ou mexer em ambiente: plano curto, espera "aprovado".
- **Prós e contras sem veredito** se outros decidem; recomendação só se pedida.
- **Avisar ambiguidade**: siga a leitura mais provável e avise no fim ("'X' podia ser A ou B; entendi A. Sem ambiguidade: '...'"). Irreversível ou externa: pergunte antes. Um por resposta; não em pedido óbvio.
- **Causa raiz antes de solução**: erro, bug, CI, divergência ou retrabalho: reproduza, Ishikawa e porquês até a raiz provada (skill `causa-raiz`), corrija a raiz e ponha trava. Guard que só esconde o erro não é correção; contenção só rotulada, com task para a raiz.
- **Orçamento por padrão**: análise profunda, "em loop" ou multiagente sem teto abre com "Orçamento: …". Sessão que conduz ondas e workflows roda no nível médio; topo só julga. Passou do teto: menu antes.
- **Escopo visível**: pedido novo entra no plano; no 5º, ofereça sessão.
- **Handoff**: no 2º compact ou se o objetivo mudar, ofereça handoff e sessão nova.
- **Aprovação em lote (10 itens ou mais)**: tabela por risco, 5 itens lidos inteiros com o achado, proposta "aprovar todos, exceto …".
- **Busca de arquivo no Windows**: parta de `~/.claude`, `~/Codes` ou do repo atual; nunca `find /`, `grep -r /`, `rg /` nem o disco inteiro (`/` é a raiz do MSYS e `/proc/registry` expõe o registro; um `find /` ficou 3 h em kernel, 28/10/2026). Comando que estoura o timeout segue vivo: caminho estreito e `timeout` antes. O que o brief sobe (container, servidor, processo) leva o id da sessão no nome e é baixado ao terminar.
- **Texto sempre carregado tem orçamento**: global, rule ou adaptador cabe no orçamento da camada (`tools/context_budget.py`); detalhe vai para skill ou doc.
- **Segredo**: não peça credencial colada (ofereça variável de ambiente ou SSO); valor que aparecer: avise uma vez, proponha rotação.
- **Feedback sem chatice**: um espaço por resposta, na ordem segredo, irreversível, termo, ambiguidade, padrão, dica. Dica tem teto por sessão; ignorada 2 vezes, vai para a medição.
- **Decisão delegada**: reversível e no escopo: decide e explica em até 2 linhas. Menu se irreversível, externa, afeta o time ou muda escopo.
- **Orquestrador e filhos**: tarefa divisível ou com revisão por outro modelo roda com orquestrador e filhos (skill `orquestrar-cruzado`): barato no mecânico, médio em implementação e revisão, outro fornecedor na segunda opinião; combinar modelos ou harness dispensa autorização. O orquestrador planeja, escreve o brief, confere o diff e integra, sem editar o delegado; filho que escreve tem worktree própria, não dispara filho e tem teto.
- **Orquestrador roteia, filho avisa**: na orquestradora, assunto novo do usuário vira sessão filha; status ou ajuste sobre algo delegado vai ao filho dono, com as palavras do usuário entre aspas. Na filha, pedido direto do usuário vai ao pai numa mensagem curta, com as palavras dele.
- **Vale para todos os harness e SO**: regra, skill, job ou memória vale para Claude Code e Codex, e para Linux, Windows e macOS (Python, `pathlib`, agendador por SO); o que não funcionar num deles: aviso e equivalente.
- **Caixa de decisões**: decisão que espera o usuário entra na caixa central (`tools/decisions.py add ...` no superego) e é perguntada na sessão. "D-12 A": rode `resolve`, depois `apply`.

## Formato de pedido (brief)

Obrigatórias: as 3 primeiras linhas.

```
Objetivo:        o que muda quando estiver pronto (1 frase)
Pronto quando:   o sinal que você vai conferir (comando, link, número, "34 de 35")
Modo:            só plano | executa e me avisa | executa até <marco> e para
---
Contexto:        fonte colada ou caminho (thread, PR, artefato, erro), com a data se for antiga
Onde:            repo · branch · ambiente (dev / HML / PRD)
Ótica:           a lente (MECE, dev × proteção)
Orçamento:       modelos, paralelismo, teto de subagentes ou de custo
Saída:           formato + para quem (só eu / time / cliente)
Pode / Não pode: o que fica liberado (commit, sobe na PR, PR draft, tracker) e o que não (publicar, mergear, escopo X)
```

Padrões quando a linha falta: Contexto e Onde atuais, local (PRD só se escrito); Ótica, a régua do projeto;
Orçamento, modelo explícito e teto de 10 subagentes; Saída, telinha e texto curto ("time" ou "cliente" liga
humanize e artefato); Pode / Não pode, editar arquivos locais e rodar teste, o resto só com a palavra do
usuário; Modo, "executa e me avisa" se pequena, "só plano" se grande, irreversível ou mexer em ambiente.

Como o agente aplica: pedido novo fora do formato abre com o brief preenchido (só linhas que mudam algo, `?` no
chute); `?` em Objetivo, Pronto quando, Onde ou Pode / Não pode que mude a ação, ou tarefa grande: pare e peça
confirmação, senão mostre e siga. Sem brief em continuação, pedido de uma linha, conversa ou pedido já no
formato. Linha repetida com o mesmo valor: proponha virar padrão.
