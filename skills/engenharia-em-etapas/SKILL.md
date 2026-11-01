---
level: superego
name: engenharia-em-etapas
description: "Drive a traceable six-stage engineering design series, from problem and as-is through market study, solution domain, HLA/ADRs and HLD. Use for RFC → HLA → HLD or cascading revisions. The active company collective owns an equivalent procedure; use this fallback when delegated or explicitly invoked."
---

# Engenharia em etapas

Uma série de design responde a uma pergunta de engenharia ("onde roda o roteador de canary da Ariadne?") em 6 documentos encadeados. Cada etapa só decide o que a anterior permite: o domínio do problema é a fonte, e uma mudança nele obriga a rederivar as etapas seguintes. A skill nasceu da série `conversation-routing` do repo ariadne (27/10/2026); os modelos de cada etapa estão em `references/`.

Termos: **etapa** (um documento da série), **fonte** (a etapa anterior e as decisões do time), **decisão do time** (resposta de um dono, com data), **Q#** pergunta aberta, **D#/ADR-#** decisão, **trace** (tabela item da fonte → elemento da etapa → status).

This skill covers the connected design series and its traceability. The active company collective's equivalent owns the procedure when available. Otherwise use this generic procedure; also use it when explicitly invoked by the user or delegated by the collective. Retain applicable safety and authorization requirements. For a single team RFC, use the active company's RFC skill when available; when an RFC is one stage of a series, use both as complementary guidance without replacing the stage contract.

## As 6 etapas

| # | Etapa | Responde | Modelo |
|---|---|---|---|
| 1 | Domínio do problema (RFC) | O que precisa ser verdade, para quem, com que regras (BR#), requisitos (R#), cenários de qualidade (QS#) e checagens de aceite (AC#) | `references/1-problem-domain.md` |
| 2 | As-is | Onde cada peça roda hoje, o que está LIVE, STALE, ABSENT ou NOT VERIFIED, com prova | `references/2-as-is.md` |
| 3 | Estudo de mercado | Prior art, práticas e benchmarks públicos: adotado, adaptado ou rejeitado | `references/3-market-study.md` |
| 4 | Domínio da solução (RFC) | Contextos, agregados, invariantes (I#), comandos, políticas e o posicionamento | `references/4-solution-domain.md` |
| 5 | HLA | Containers, visões de execução, deploy, observabilidade, custo 1-3-1 e ADRs | `references/5-hla.md` |
| 6 | HLD | Rotas, itens de dados, algoritmos, sequências, modos de falha, rollout, testes, tecnologia e POCs | `references/6-hld.md` |

O README da série guarda o índice, as decisões, as perguntas abertas com dono, os limites aceitos (L#) e o histórico de revisões.

## Três portões: bem escrito, correto, otimizado

Toda etapa, inclusive o plano de testes (etapa 7), passa em três portões antes de fechar, cada um com seus revisores e sua evidência: **bem escrito** (um leitor frio entende, confere e decide), **correto** (faz o que precisa, inclusive quando algo falha: contraexemplo, recálculo, POC com controle negativo, documentação oficial, segunda opinião de outro modelo) e **otimizado** (o jeito mais simples e barato que dá as mesmas garantias, com conta antes e depois). Critérios de cada portão nas 7 etapas, regra de passagem e como rodar com vários agentes: `references/quality-gates.md`; brief do portão de correção: `references/correctness-brief.md`.

## Regras que valem em toda etapa

Estão em `references/cross-cutting.md`. As que mais quebraram na série original:

1. **Tudo em inglês**, inclusive tabelas, cartões da página e rótulos. Português só na conversa com o usuário.
2. **Decisão do time não se muda.** Ela fica num arquivo de decisões (`decisions-rN.md`, uma linha por decisão, com data e efeito na série). Conflito vira Q# com dono. Se o usuário decidir algo na conversa, grave no arquivo na hora: um agente que lê o arquivo antigo desfaz a decisão.
3. **Sem conversa privada em link público.** Escreva "Team decision, DD/MM/AAAA". Sem "Fulano disse", sem link do Slack, sem DM. Nome de pessoa só como dono de pergunta ou de componente.
4. **Fonte em todo número e afirmação**: arquivo e linha no commit, comando, link com data. Sem fonte, vira Q#, A# (assumption) ou P# (valor proposto, dono confirma).
   - Resposta de dono que contradiz uma fonte citada ou o código: aplique a decisão, abra uma Q# para o conflito e carregue os dois números até a resposta.
   - Decisão condicional ("no processo se ≤ 50 ms, senão AWS"): registre a condição no D#, escolha pelo valor medido e, sem medição, trate o ramo escolhido como P# com o POC que decide.
   - Prefixos de ID: BR, R, QS, AC, G, N (non-goal), A (assumption), Q, D, I (invariant), POL (policy), ADR, C (constraint), K (risk), L (accepted limit), AS (as-is constraint), NV (NOT VERIFIED), ALG (algorithm), P (proposed value), TS (test set), POC, DR (as-is drift).
5. **Código com hash e linha**: cite `path:lines` lido num commit fixo e rode `scripts/permalinks.py`, que transforma em link para a linha naquele commit (`?plain=1` em `.md`). Nunca link para branch. O `--sha` é o commit que você leu de fato: ler o checkout local e citar outro commit gera link para a linha errada (caso real de 28/10/2026: 13 de 43 links); o script acusa "LINES DIFFER FROM CHECKOUT". `permalinks.py --show` imprime as linhas de cada citação: leia e confirme que dizem o que o texto afirma (o `--check` só pega linha fora do arquivo). No texto das etapas, cite os scripts da skill só pelo nome (`privacy_scan.py`), sem `scripts/`, para o `permalinks.py` não tratá-los como arquivo do repo.
6. **IDs estáveis**: item novo pega o próximo número; item removido fica como "Removed in revision N: <motivo>". Cada documento abre com "In one minute" e "What changed in revision N".
7. **Dado pessoal real nunca**: telefone, CPF ou e-mail de lead vira sintético no mesmo formato (`5562990000101`; sintético começa com `55629900` na forma de 13 dígitos e com `55629000` na de 12 dígitos (sem o 9), e o scanner ignora esses dois prefixos). Rode `scripts/privacy_scan.py` no documento e na página publicada. Comando de verificação nunca imprime segredo: use `kubectl get secret <n> -o jsonpath='{.data}' | jq 'keys'`, `env | cut -d= -f1`, nunca o valor.
8. **Legibilidade**: aplique a skill `technical-doc-readability` (resposta no começo, termo único por conceito, frase curta) e confira com `scripts/preserve.py` que nenhum número, ID, tag ou código mudou numa reescrita.

## Fluxo para criar uma etapa

1. **Leia a fonte inteira**: as etapas anteriores, o arquivo de decisões e o código no commit citado. Para o as-is, só leitura nos sistemas (sem deploy, sem criar recurso, sem mudar config, sem imprimir segredo).
2. **Monte o trace** (`trace-<etapa>.md`): cada item da fonte que a etapa precisa responder → elemento que responde → covered, stale, missing, contradicts ou orphan. Etapa sem trace não está pronta.
3. **Escreva pelo modelo** da etapa em `references/`. Prós e contras neutros quando outras pessoas decidem (B8); quando o usuário pede decisão, 1-3-1 com recomendação e o motivo.
4. **Perguntas para os donos**: liste as Q# que só uma pessoa responde, com o dono e o que muda conforme a resposta. Quando a resposta chegar, grave no arquivo de decisões e aplique como "Team decision, data".
5. **POC quando a decisão depende de um conceito não provado** (etapa 6): cada POC testa um conceito com critério de aprovação, roda local com mock (moto, respx, k6), e o resultado entra no HLD com o número medido e o que ficou aberto.
6. **Autochecagem antes de fechar a etapa** (cada item com a evidência em `trace-<etapa>.md`):
   - todo número tem fonte (arquivo e linha no commit, price list com data, decisão do time) ou está marcado como proposta (`P#: proposed value, owner to confirm`); "series target" sem fonte não vale;
   - cada `path:lines` citado foi relido com `git show <sha>:<path> | sed -n '<a>,<b>p'` e o trecho diz o que o texto afirma;
   - todo POC tem um controle negativo que falha sem a proteção testada;
   - o custo cobre a topologia da seção Deployment, linha por linha;
   - nenhum comando citado imprime valor de segredo.
7. **Verifique**: `preserve.py` se foi reescrita, `permalinks.py --check`, `privacy_scan.py`, e o build da página sem âncora quebrada nem ID sem definição. O build roda local mesmo quando publicar não é permitido; ele precisa do pacote `markdown` (`pip install --target assets/pylib markdown`, uma vez).
8. **Publique** (só com a palavra do usuário, ou quando ele pediu artefato): página única com as etapas em ordem, cartões das etapas, IDs com link e tooltip. Use `assets/page/` (ajuste `DOCS` e o caminho no topo do `build.py`).

## Quando a fonte muda: cascata

Mudou a etapa 1 ou uma decisão do time? Rederive em sequência, uma etapa por vez, porque cada uma parte da anterior já fechada. Detalhes e o brief pronto em `references/cascade.md`. Em resumo: um subagente médio por etapa, com trace e `changes-<etapa>.md` (antes, depois, por quê, id da fonte); decisão reversível de design o agente decide e registra; decisão do time vira pergunta; no fim, o topo lê a série inteira e confere a rastreabilidade de cada R# até o HLD.

## Subagentes e orçamento

Barato (Haiku) para checagem mecânica, médio (Sonnet) para ler e escrever uma etapa, topo (Opus) só no julgamento final da série. Reescrita de legibilidade roda em paralelo, um agente por documento; a cascata roda em sequência. Declare no começo: quantos agentes, que modelo, o teto (ou "sem subagentes" quando rodar sozinho). Sem subagentes, o leitor frio e a leitura final viram L# no README, com o que o autor checou no lugar. Uma etapa posterior que descobre um erro numa anterior corrige a anterior, registra em "What changed" das duas e rederiva o que veio depois (cascata curta). Um brief em arquivo, autossuficiente, com os arquivos de entrada e saída e o comando de checagem que o agente roda antes de terminar.

## Armadilhas já vistas

- O renomeador de termos quebra artigos ("an Variant") e nomes próprios ("Argo Canary releases"): revise o diff.
- Mermaid: id de nó `in` é palavra reservada; ponto e vírgula numa mensagem de sequência quebra o diagrama.
- IDs de outra fonte (o as-is usa A1, P2 como ids de checagem) colidem com os ids da série: desligue o auto-link nessa etapa.
- Lista logo depois de uma linha de parágrafo, sem linha em branco, vira parágrafo no Markdown.
- Artefato grande (mais de 1 MB) só pode ser republicado no mesmo link depois de ler a página publicada inteira: mantenha a página enxuta ou planeje um link novo.

## Diagramas e página

Regras de cada diagrama (legenda, direção, `autonumber`, cores por papel, validação com `scripts/mermaid/check.mjs`) e o que a página publicada faz com eles (tela cheia com zoom, definição no hover do nó, arestas ligadas, índice de figuras, links das tags de evidência) estão em `references/diagrams-and-page.md`.

## Scripts

- `scripts/preserve.py ORIG REV`: compara títulos, código, tags, URLs, IDs e números entre duas versões.
- `scripts/permalinks.py --repo-dir <repo> --sha <commit> --github <owner/repo> FILES`: links para a linha no commit.
- `scripts/privacy_scan.py FILES`: telefone, CPF, e-mail, token, Slack e URL de banco com senha.
- `scripts/mermaid/check.mjs FILE.md`: todo bloco mermaid do arquivo precisa passar no parser (`npm install` na pasta uma vez).
- `assets/page/`: `build.py`, `refs.py`, `shell.html`, `reader.js` e `reader.css` da página da série (popover de definição com usos, busca, scroll spy, voltar, links de seção, impressão).

## Related

- [[humanize/SKILL|humanize]]: texto sem cara de IA
- [[cards-de-task/SKILL|cards-de-task]]: depois do HLD, as tasks
- [[global/regras-de-agente|regras-de-agente]]: B1, B2, B6, B8, B19
