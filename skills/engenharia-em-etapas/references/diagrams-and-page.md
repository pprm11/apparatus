# Diagramas e página de leitura

Pesquisa com fontes: `frontend-research.md` (recursos de leitura de documentação) e `frontend-research-2.md` (visualizadores de OpenAPI como Redoc, Scalar, Stoplight Elements, RapiDoc e plugins do Swagger UI, e UX de diagramas: Mermaid, Structurizr, IcePanel, D2).

## Cada diagrama (mermaid)

- Linha de legenda logo antes: `**Figure: <título curto>.** <o que mostra e onde olhar>`. A página usa esse texto como título da figura, no índice de figuras e na tela cheia. No as-is a legenda é a pergunta `**D1 ...**`.
- Só fatos do documento: mesmos participantes, arestas, direções e grupos. Redesenhar não pode mudar o que o diagrama afirma.
- Direção que dá arestas curtas (LR ou TB). Subgraph onde o texto já agrupa. Diagrama em que as arestas cruzam a figura inteira vira dois (ex.: o que passa pelo roteador e o que passa por fora).
- Quebre rótulos com `<br/>` (limites na regra de medida abaixo). `autonumber` em todo diagrama de sequência, para o texto citar o passo.
- `classDef` por papel (roteador, Variant v1, Variant v2, sistema externo, banco, pessoa), com traço de tom médio que lê no claro e no escuro, e a legenda das cores na linha de legenda.
- Mantenha IDs (R12, ADR-4, AS3) e termos do glossário nos rótulos dos nós: a página mostra a definição ao passar o mouse e leva até ela no clique.
- **Meça antes de publicar.** Um diagrama largo demais é encolhido para caber na coluna e vira caixas pequenas num fundo vazio (caso real de 28/10/2026: 2.000 a 2.800 px mostrados em 631 px, texto a 6 px, caixas em 5 a 15% da área). Meta: largura até 1.250 px e altura até 1.400 px renderizado, no máximo 14 nós e 3 subgraphs por figura; passou disso, divida em duas figuras. Rótulo de nó até 26 caracteres por linha e 2 linhas; rótulo de aresta até 16. Comece todo flowchart com `%%{init: {"flowchart": {"nodeSpacing": 22, "rankSpacing": 30, "padding": 6, "diagramPadding": 4}}}%%`. TB para cadeias e camadas; LR só com até 4 níveis.
- Como medir: `python scripts/mermaid/extract.py <arquivos.md>`, sirva a pasta `scripts/mermaid` (`python -m http.server`), abra `measure.html` no navegador e rode `await measure({tight: true})` (largura e altura de cada bloco) ou `await best(1000, 1300)` (melhor direção por flowchart). Encurtar rótulo ganha uns 20%; o resto vem de estrutura.
- Valide: `cd scripts/mermaid && npm install` (uma vez), depois `node check.mjs <arquivo.md>`; todos os blocos precisam passar. Sem nó com id `end` ou `in`, sem ponto e vírgula em mensagem de sequência.

## O que a página faz com os diagramas (`assets/page/reader.js`)

- Barra "Figure N · legenda" com Expand (tela cheia com zoom pela roda, botões e arraste; Esc fecha; duplo clique no diagrama também abre), Copy link e o aviso "Text is small: expand to read" quando o diagrama encolhe abaixo de 65%.
- Hover ou foco num nó com ID ou termo abre o popover da definição; clique vai até ela. Hover num nó de flowchart destaca as arestas ligadas e esmaece o resto.
- Índice "Figures" no fim do sumário lateral.
- O runtime de mermaid do artefato roda com `securityLevel` estrito: `click` e `tooltip` dentro do diagrama são ignorados, por isso tudo é feito depois da renderização, em cima do SVG.

## O que veio dos visualizadores de API e entrou na página

- Link e cópia de link por elemento (títulos, figuras), como os deep links do Redoc e do Swagger UI.
- Filtro no sumário (o `filter` do Swagger UI) e busca com `/` ou Ctrl+K.
- Popover com definição e usos, no lugar de schema expansível.
- Ficou para depois, por custo: painel de contexto à direita em telas largas (três painéis do Redoc e do Stoplight Elements), "copiar seção como Markdown" e controle de nível de expansão por seção.

## Evidência no as-is

- Tags `[FILES prefix:path:lines]` viram links para a linha no commit do prefixo (GitHub para `v2:`, Gitea para `v1:` e `deploy:`); `[LIVE ids]` vira um chip com o que é a checagem e o link para o relatório as-is completo. A tabela de prefixos fica em `assets/page/refs.py` (`PREFIXES`): projeto novo, prefixos novos.
- A conversão roda no Markdown, antes da renderização (`link_tags_md`), porque `__init__.py` viraria negrito.
