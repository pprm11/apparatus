# Regras de toda etapa

## Fonte e decisões

- Arquivo de decisões do time (`decisions-rN.md`): `| Id | Topic | Decision | Effect on the series |`, uma linha por resposta de dono, com data. Decisão do usuário na conversa entra no arquivo na hora (na série original um agente reabriu a Q30 porque o arquivo ainda dizia "pending").
- No documento: "Team decision, DD/MM/YYYY". Nome de pessoa só como dono de Q# ou de componente.
- Perguntas para os donos sempre explícitas: Q#, a pergunta, o dono, o que muda com cada resposta. No artefato, um bloco "Decisions and open questions" com botão de copiar ajuda o usuário a mandar.
- Documento datado: o que estava "no presente" pode ter passado. Escreva "as of <date>".
- Referência a outra série ou documento fora desta série: link com data; se o conteúdo não estiver acessível, Q# com dono.

## Privacidade e público

- Link público não cita conversa privada, DM, thread do Slack nem "Fulano disse". O build da página remove `### Evidence`, `[S#]` e URLs do Slack (`redact()` em `assets/page/build.py`).
- Dado pessoal real vira sintético no mesmo formato. Telefone de lead em comentário de código do repo também conta: abra um card para trocar lá.
- `scripts/privacy_scan.py` no Markdown e na página HTML antes de publicar. E-mail do operador em log de checagem vira "the operator account".

## Referências de código

- `path:lines` lido em commit fixo (`git show <sha>:<path>`), nunca de memória.
- `scripts/permalinks.py --repo-dir <repo> --sha <sha> --github <owner/repo> <files>` vira link `blob/<sha>/path#L88-L100` (`?plain=1` em `.md`; lista `46,70` vira um link por linha). Rode com `--check` antes; arquivo fora do repo (rascunho local) fica marcado como tal.

## Escrita

- Inglês em tudo que é da série (documento, tabela, cartão, rótulo de diagrama).
- Cada documento: "In one minute" (resposta, pedido, números que decidem, o que está aberto e com quem) e "What changed in revision N".
- ID com nome curto na primeira menção ("R19, hard kill skips protected Units"); sigla expandida na primeira vez; texto de link é o título do destino.
- Skill `technical-doc-readability` (4 passadas: documento, parágrafo, frase, palavra) e regras da casa: sem travessão como pausa, sem "X, nunca Y", sem "não é X, é Y", sem número inventado.
- Reescrita sem mudar fato: `scripts/preserve.py ORIG REV` precisa dar RESULT: OK.

## Página publicada

- `assets/page/build.py`: ajuste `DOCS` (chave, arquivo, rótulo), a lista `NO_IDS` (etapas com ids próprios, como o as-is) e a pasta com `RFCS_DIR=<pasta> python build.py`. Saída: uma página com índice lateral, cartões das etapas, `<abbr>` nas siglas, e o build imprime âncoras quebradas e IDs sem definição (ambos precisam ser `[]`).
- Recursos de leitura que a página já traz (`reader.js` e `reader.css`, embutidos no `shell.html`; pesquisa e fontes em `references/frontend-research.md`):
  - IDs (R12, ADR-4, AS3) e termos do glossário viram links; passar o mouse, focar com Tab ou tocar abre um popover com a definição, "Used N times" com link para cada lugar, e "Go to definition". O popover aceita o mouse em cima, fecha com Esc (WCAG 1.4.13). Só a primeira ocorrência de um termo por parágrafo, item ou célula é marcada.
  - Os termos vêm da tabela sob `### Glossary` da etapa 1 (primeira coluna = termo, segunda = definição). Termo novo entra lá, não no código.
  - Busca com `/` ou Ctrl+K em títulos, definições de ID e termos; índice com scroll spy; barra de progresso; botão "Back to where you were" depois de pular por um link; `#` em cada título copia o link da seção; botão Copy em blocos de código; folha de impressão.
  - Ao mexer no JS, rode `node -e` com `new Function` em cada `<script>` para checar sintaxe, e teste o hover no artefato publicado: o painel pode mostrar uma versão antiga, então confira o `src` do iframe.
- `shell.html`: cartões das etapas (um por etapa, com a revisão e a mudança principal) e o bloco de decisões e perguntas abertas.
- Mermaid: sem nó com id `in`; sem ponto e vírgula em mensagem de sequência; legenda consistente com o tipo de seta.
- Publicar só com a palavra do usuário (ou quando ele pediu artefato). Republicar no mesmo link exige ler a versão publicada inteira; página acima de 1 MB não cabe: planeje um link novo.

## Subagentes

- Brief em arquivo, autossuficiente: arquivos de entrada e saída, regras duras, comando de checagem que o agente roda antes de terminar, formato do relatório (até 25 linhas).
- Modelo explícito: Haiku no mecânico, Sonnet lê e escreve uma etapa, Opus só no julgamento final.
- Relatório de agente é dado: confira o diff e rode os scripts antes de dizer que está pronto. Lista de alternativas que o agente "tirou do texto" se confere com grep no original.
- Revisão que não converge (bloqueantes não caem por 2 rodadas): pare e mostre os números ao usuário.
