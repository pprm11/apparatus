# Etapa 2: as-is

Leitor: engenheiro ou tech lead que precisa saber onde cada peça roda hoje antes de ler o design. Registra fatos com prova e não decide nada. Vem logo depois do domínio do problema porque confirma ou derruba as suposições dele.

## Coleta (só leitura)

- Nada de deploy, recurso novo, mudança de config, mensagem ou segredo impresso. Cada checagem é um comando de leitura com id (`[LIVE X1]`), hora e saída guardada em `evidence/`.
- Código e manifestos num commit fixo por repo, com prefixo (`v2:` = repo X no commit Y). Tabela de prefixos no começo.
- Palavras de estado com um sentido só: **LIVE** (respondeu uma sonda ou status SUCCESS/Healthy na data; não diz nada sobre tráfego), **STALE** (presente, mas não serve direito ou parado desde uma data), **ABSENT** (declarado e não presente, ou presente e nunca rodou), **NOT VERIFIED** (nenhuma checagem chegou; diga o que verificaria e quem destrava). Fato lido só em arquivo não leva palavra de estado: leva a tag `[FILES]` e, quando o estado em execução importa, um NV#.
- Tags: `[LIVE id]`, `[FILES prefix:path:lines]` (no texto das etapas da série, cite o código como `path:lines` em crase, que o `permalinks.py` transforma em link; o prefixo fica só na tabela de prefixos), `[RENDER ref overlay]`, `[PLATFORM <data>]` (declaração de time, não verificada por comando), `[NOT VERIFIED: ...]`.

## Relatório completo (artefato próprio, partes A1 a A7)

A1 estrutura (C4 contexto e containers) · A2 deploy e ambientes · A3 pipelines · A4 caminho de uma requisição · A5 flags e alavancas · A6 dados · A7 drift (linhas DR-xx em DECISION, CANARY, INFO; D# fica para decisão do time) e perguntas. Cada parte tem um gabarito (perguntas que um leitor frio precisa responder) e passa pelo loop leitor frio → revisor até zero bloqueante.

## A etapa na série (resumo)

```
# <Topic>: as-is of <systems> (<snapshot date>)
Series: ...
<one paragraph: what this stage records, link to the full as-is report>
## In one minute            4 to 6 sentences, answer first, the ask (who confirms which NOT VERIFIED item), with tags
## What changed in revision N
## What the as-is means for <the design>   AS1, AS2...: one constraint each, with the fact's tag and the BR#/R#/A# it touches
## 1 Orientation · 2 Product by environment · 3 Facts that most change decisions · 4 Top risks, stated as facts
## 5 Questions for <owner> · 6 Not verified · 7 Recheck of <date> · 8 How to read the full report · 9 More views (diagrams)
```

Os ids do as-is (A1, P2, X1...) colidem com os da série: o build não faz auto-link nesta etapa. As restrições AS# são o que as etapas seguintes citam.

## Sem acesso ao vivo

Quando não há permissão para checagem ao vivo: `evidence/` guarda as leituras de arquivo (comando `git show` e trecho) e a lista NOT VERIFIED, cada item com o comando de leitura que verificaria e quem pode rodá-lo; o relatório A1 a A7 e o recheck ficam como limite aceito L# no README. Numa execução de um dia só, o recheck é uma releitura dos arquivos no fim do dia, registrada como tal. As seções 1, 2 e 7 continuam, com o que os arquivos mostram e NOT VERIFIED no resto.

## Pronto quando

Cada suposição A# e cada requisito que depende do estado atual tem um fato que confirma, contradiz ou fica NOT VERIFIED com quem destrava; cada fato tem tag; um recheck curto dos fatos principais em outra data não mudou nada (ou o que mudou está registrado).
