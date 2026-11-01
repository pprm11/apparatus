# Round 1 of the skill evals (27/10/2026)

Grades: `ariadne/.claude/worktrees/vigilant-dubinsky-f33008/skill-test/grade.md` (run A) and `ariadne/.claude/worktrees/friendly-dewdney-b9b2e7/skill-test/grade.md` (run B). Rubric: `evals/rubric.md`.

## Totals

| Run | Seed | Total | Result |
|---|---|---|---|
| A | outbound message queue | 63.5 | Fail (below 85) |
| B | LLM gateway with model A/B | 87.5 | Pass (no blocking skill defect) |

Run A lost most of its points to execution: an incomplete cost table for the recommended option (C8, 6), invented "series target" measures (C3, 6), wrong citations (C11, 4), a verify command that prints secrets (C5, 5). Run B lost points to POCs that pass by construction, missing asks and two unsourced numbers.

## Skill defects, merged and ordered by points lost

| # | Defect | Points lost | Runs | Exact edit |
|---|---|---|---|---|
| 1 | A POC criterion does not have to be able to fail. Both runs shipped one: A's POC-4 (800 reservations can never break 1,000 a minute), B's race under one Python lock and its injection check on a one-element set. | 7.0 (A 3.5, B 3.5, C10) | A, B | `references/6-hld.md` line 29, after "escreva a hipótese e o critério de aprovação antes de rodar.", append: "O critério precisa poder falhar: rode um controle negativo que quebra sem a proteção testada (sem lock compartilhado no harness, sem resultado montado para passar) e uma carga que consiga passar do limite que o POC diz provar." |
| 2 | The ask is missing from three stage templates while `references/cross-cutting.md` line 24 requires it in every "In one minute". | 4.5 (B 3, A 1.5, C2) | A, B | `references/2-as-is.md` line 22: `## In one minute            4 to 6 sentences, answer first, the ask (who confirms which NOT VERIFIED item), with tags`. `references/3-market-study.md` line 10: `## In one minute            verdict, the ask, what the market covers, what it does not, the numbers that drive decisions`. `references/6-hld.md` line 10: `## In one minute (answer, ask to implementers and reviewers, numbers proven) · ## What changed in revision N`. |
| 3 | A# is the id of assumptions, and the HLD template gives algorithms no prefix, so both runs numbered algorithms A1 and up, colliding with assumptions. | 4.0 (A 2, B 2, C12) | A, B | `references/6-hld.md` line 14: `## Algorithms               one subsection each, id ALG# (A# is reserved for assumptions), pseudo-code in fenced blocks, conditions (e.g. DynamoDB ConditionExpression) written out`. |
| 4 | The order "questions before answers" leaves no trace and revision numbering of the draft is unspecified. Run A could not show the order and mislabelled its revision heading; run B invented the protocol and was the only one to prove it. | 3.0 (A, C4) | A (B passed by its own initiative) | `references/1-problem-domain.md` line 37, append: "Salve o rascunho com as perguntas como revisão 1 (`evidence/<etapa>-r1-before-answers.md`) e grave a hora em que as respostas foram lidas (`evidence/answers-read-at.txt`). Aplique as respostas como revisão 2 e liste cada D# em What changed in revision 2." |
| 5 | "Fornecedor falando de si é vendor claim" reads as overriding search-only, so A labelled summary-only pages as vendor claims. | 2.0 (A, C6) | A | `references/3-market-study.md` line 25, append: "Página lida só por resumo ou snippet é search-only, seja quem for o editor; vendor claim exige a página lida." |
| 6 | `scripts/privacy_scan.py` flags the synthetic number the skill prescribes (`SKILL.md` line 35), so a clean scan is impossible (A: FOUND 2 on `5562990000101`). | 0 (content was right) | A | `scripts/privacy_scan.py` line 12: skip matches that start with `556299000`. `SKILL.md` line 35, after the example: "Sintético começa com `556299000`; o scanner ignora esse prefixo." |
| 7 | The as-is tag `[FILES prefix:path:lines]` never matches `scripts/permalinks.py` line 18; both runs had to drop the prefix. | 0 | A, B | `references/2-as-is.md` line 10: ``Tags: `[LIVE id]`, [FILES `path:lines`] (prefix only in the prefix table), ...``. Or extend the regex at `scripts/permalinks.py` line 18 to accept `prefix:path:lines`. |
| 8 | The as-is assumes live checks: `evidence/` with command output, the A1 to A7 report, a recheck on another date. Nothing says what to write when no live check is allowed. | 0 | A, B | `references/2-as-is.md` line 33, append: "Sem acesso ao vivo: `evidence/` guarda as leituras de arquivo e a lista NOT VERIFIED; o relatório A1 a A7 e o recheck ficam como L# no README." |
| 9 | The page build is a verification step (`SKILL.md` line 45) but sits next to publishing (line 46); both runs skipped it. | 0 | A, B | `SKILL.md` line 45, append: "O build roda local mesmo quando publicar não é permitido." |
| 10 | Cost lines: the skill lists the lines (`references/5-hla.md` line 29) but not that the priced topology must match the Deployment table, nor what to write for an unpriced line. Run A's C8 loss is execution, this edit makes it detectable. | 0 (A's 6 points are execution) | A | `references/5-hla.md` line 29, append: "Cada linha tem preço ou NOT PRICED com teto e Q#. A topologia com preço é a da seção Deployment (número de tasks, load balancer, NAT, banco). Sem volume alvo dos donos, use 1×, 10× e 100× do volume de hoje." |

No skill defect was classed blocking.

## REPORT.md complaints judged valid

Run A (`vigilant-dubinsky-f33008/skill-test/REPORT.md`):

| Id | Verdict |
|---|---|
| S1 revision numbering of the draft | Valid (defect 4) |
| S2 FILES tag vs permalinks | Valid (defect 7) |
| S3 scanner flags the synthetic number | Valid (defect 6) |
| S4 database POCs, downloads | Valid |
| S5 negative controls | Valid (defect 1) |
| S6 price files, free tier, target volume | Partly valid (target volume; defect 10) |
| S7 compare premises with files | Partly valid (`2-as-is.md` line 33 covers A#) |
| S8 evidence with no live access | Valid (defect 8) |
| S9 single-agent declaration | Valid, trivial |
| S10 requirement found later | Partly valid |
| S11 D# closes which Q# | Valid, minor |
| S12 build when publishing is forbidden | Valid (defect 9) |

Run B (`friendly-dewdney-b9b2e7/skill-test/REPORT.md`):

| Id | Verdict |
|---|---|
| S1 decision contradicts its own source | Partly valid (SKILL.md line 30 covers conflicts in general) |
| S2 FILES tag vs permalinks | Valid (defect 7) |
| S3 checkout not at the fixed commit | Not valid (`cross-cutting.md` line 18 already requires `git show <sha>:<path>`) |
| S4 recheck with no live facts | Valid (defect 8) |
| S5 later stage revising an earlier one | Valid |
| S6 stand-in when mock tools are missing | Valid |
| S7 trace format vs HLD coverage | Valid, minor |
| S8 single-agent declaration | Valid, trivial |
| S9 build when publishing is forbidden | Valid (defect 9) |
| S10 production owner name | Not valid (SKILL.md line 31 allows a component owner) |
| S11 cost checklist | Valid (defect 10) |

Complaints raised by both runs: FILES tag vs permalinks, single-agent declaration, build when publishing is forbidden, cost checklist. These four plus defects 1 to 3 are the edits for round 2.
