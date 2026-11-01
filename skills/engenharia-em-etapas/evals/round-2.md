# Round 2 of the skill evals (28/10/2026)

Grades: `ariadne/.claude/worktrees/agent-a808f2010469de75a/skill-test/grade.md` (run A2) and `ariadne/.claude/worktrees/agent-ae1ff9463d6afcd42/skill-test/grade.md` (run B2). Rubric: `evals/rubric.md`. The runs used the skill as edited after round 1 (snapshot `6ad18f5` of the skills repo); the skill was edited again after they ran. A lost point that the current skill already prevents is classed "skill defect, fixed since round 2" and gets no edit here.

## Totals

| Run | Seed | Round 1 | Round 2 | Change | Result |
|---|---|---|---|---|---|
| A | outbound message queue | 63.5 | 87.5 | +24.0 | Pass |
| B | LLM gateway with model A/B | 87.5 | 85.0 | -2.5 | Pass (at the threshold) |

Run A gained on every check that failed in round 1: the cost table now matches the price files SKU by SKU, the draft before the answers is saved with its time, and every POC has a control. It still lost 2.5 points in C10: POC3 claims a control for all 11 checks and has one for 6. Run B lost points spread across the series: no acceptance check for BR4 and BR5, an unused benchmark kept, option A's cost figures not produced by the cited script, and an invented NAT ceiling. All of these are execution defects. No skill defect is blocking.

Points lost by class, both runs: execution 22.5 (A 9.0, B 13.5), skill defect open 2.5 (A 1.5, B 1.0), skill defect fixed since round 2 2.5 (A 2.0, B 0.5), seed limit 0. Total lost 27.5.

## Open skill defects, merged and ordered by points lost

| # | Defect | Points lost | Runs | Exact edit |
|---|---|---|---|---|
| 1 | "Every POC has a negative control" reads as one per POC file. Run A put 11 checks in one POC, gave 6 a control and reported all 11 as controlled; its log check used keys in a format other than the HLD's, so it passed by construction. | 1.0 (A, C10; the other 1.5 of that finding is execution) | A | `references/6-hld.md` line 30, append: "Um POC com vários checks tem um controle por check, e o resumo diz quantos checks têm controle. Os dados sintéticos seguem os formatos do HLD (chave, id, linha de log); com outro formato o POC prova outra coisa." |
| 2 | The solution-domain template heading `## Decision: placement (A#)` uses the assumption prefix. Run A copied `(A#)` literally; run B wrote `(A1)`, the id of an assumption. | 1.0 (A 0.5, B 0.5, C12) | A, B | `references/4-solution-domain.md` line 19: `## Decision: placement (ADR-# or D#)   options A to E with pros and cons; the decision and why; Background: the options compared` |
| 3 | The HLA skeleton has no technology heading, and the instruction heading `## Escolha de tecnologia` reads like a section. Run B shipped it as a Portuguese heading. | 0.5 (B, C1) | B | `references/5-hla.md`: after line 20 add `## Technology choices (summary)   language, runtime, IaC, test tools: options, criteria, decision; detail in the HLD; each decision becomes an ADR`. Rename line 32 to `## Como escolher a tecnologia (vai para a seção Technology choices)`. |
| 4 | The as-is drift ids `D-xx` (`references/2-as-is.md` line 14) collide with team decisions D#, and the prefix list in SKILL.md line 35 has no drift prefix. Both runs used D-01 next to D1. | 0 (inside C12 judgement) | A, B | `references/2-as-is.md` line 14: replace `linhas D-xx` with `linhas DR-xx`. SKILL.md line 35: add `DR (as-is drift)` to the prefix list. |
| 5 | moto is named for DynamoDB (`references/6-hld.md` line 31) without saying it cannot prove atomicity. Run A measured up to 37 winners on one key under moto and moved the proof to SQLite. | 0 (handled by the run) | A | `references/6-hld.md` line 31, append: "moto prova a forma da chamada, não a atomicidade: escrita condicional concorrente vai em DynamoDB Local, ou num banco local declarado como substituto." |
| 6 | The page build needs a `markdown` package that the skill does not ship (`assets/page/build.py` line 8 looks for `assets/pylib`). Run A could not build. | 0 | A | SKILL.md line 54, append: "O build precisa do pacote `markdown`: `pip install --target assets/pylib markdown` uma vez." |
| 7 | Nothing says how to treat a reference to another series or document (run B: D3 points at "the router canary"). | 0 | B | `references/cross-cutting.md` line 8, append a bullet: "Referência a outra série ou documento fora desta série: link com data; se o conteúdo não estiver acessível, Q# com dono." |
| 8 | Without subagents, nothing says what replaces the cold reader and the final read (SKILL.md line 63 only asks to declare "sem subagentes"). | 0 | A, B | SKILL.md line 63, after "(ou \"sem subagentes\" quando rodar sozinho)", insert: "Sem subagentes, o leitor frio e a leitura final viram L# no README, com o que o autor checou no lugar." |
| 9 | `permalinks.py` reports the skill's own `scripts/privacy_scan.py` as NOT IN TREE when the repo has a top-level `scripts/`. | 0 | A | SKILL.md line 38, append: "No texto das etapas, cite os scripts da skill só pelo nome (`privacy_scan.py`), sem `scripts/`, para o `permalinks.py` não tratá-los como arquivo do repo." |
| 10 | No time cap for a POC (run A: POC1 took 129 to 205 seconds on SQLite). | 0 | A | `references/6-hld.md` line 32, append: "Teto de 5 minutos por POC; passou, reduza a carga e diga quanto." |
| 11 | Price tier choice is not stated (`references/5-hla.md` line 29). | 0 | A | `references/5-hla.md` line 29, append: "Use o primeiro tier on-demand, sem free tier, e diga se o volume alvo passa de um tier." |
| 12 | A fact read only from a file has no state word, and nothing says so. | 0 | A | `references/2-as-is.md` line 9, append: "Fato lido só em arquivo não leva palavra de estado: leva a tag `[FILES]` e, quando o estado em execução importa, um NV#." |
| 13 | `privacy_scan.py` and `preserve.py` print a traceback on `--help`. | 0 | A | `scripts/privacy_scan.py` line 24 and `scripts/preserve.py` line 33: print the usage line and exit 0 when `sys.argv[1:]` is empty or starts with `-h`. |

Optional edit, not a defect: both runs wrote cost figures by hand next to a cost script (A2 matched its script, B2 did not). `references/5-hla.md` line 29 could append "Os totais da tabela saem do script de custo salvo, sem conta à mão." This would have caught B2-F4.

## Defects fixed since round 2 (no edit)

| Defect | Points | Runs | Fixed by |
|---|---|---|---|
| Owner answer that contradicts its cited source (3,250 against 1,310 leads a day in `docs/capacidade-e-rollout.md:30-35`). A2 did not open a Q#; B2 did (Q15) | 1.5 | A | SKILL.md line 33 |
| Recheck in a one-day run | 0.5 | A | `references/2-as-is.md` line 33 |
| Prefix collisions N# (non-goal, NOT VERIFIED) and C (command, constraint) | 0.5 | B | SKILL.md line 35 |
| WebFetch summaries labeled search-only | 0 | A, B | `references/3-market-study.md` line 25 |
| NAT price list code | 0 (B's invented ceiling is execution) | A, B | `references/5-hla.md` line 29 |
| Wrong ranges that `--check` passes | 0 (A's wrong range is execution) | A, B | SKILL.md line 36 (`--show`) |
| Conditional decision D4 | 0 | B | SKILL.md line 34 |
| Questions in an autonomous run | 0 | B | `references/1-problem-domain.md` line 37 |

## REPORT.md complaints valid and not yet fixed

| Run | # | Complaint | Open defect |
|---|---|---|---|
| A | 1 | Build needs a markdown package not shipped | 6 |
| A | 3 | No state word for a file fact (partly valid) | 12 |
| A | 7 | No rule for choosing a price tier (partly valid) | 11 |
| A | 9 | moto is not atomic | 5 |
| A | 10 | `permalinks.py` flags the skill's own script | 9 |
| A | 11 | Traceback on `--help` | 13 |
| A | 12 | What to record without subagents (partly valid) | 8 |
| A | 13 | No POC time cap | 10 |
| B | 3 | Reference to another series | 7 |
| B | 10 | Portuguese heading in the stage 5 reference (partly valid) | 3 |

Valid and fixed since round 2: A 2, 4, 5, 8; B 1, 2, 4, 5, 6, 7, 8, 9, 11, 13. Not valid: A 6 (a decision owner is an owner), B 12 (seed date), B 14 (shell). Complaint raised by both runs: a summarizing fetch makes every source search-only (fixed).

## For round 3

Edits 1 to 3 are the ones that cost points. Run A's remaining losses are execution: a false claim about controls, a key that carries the phone into the table, logs and traces, and an unpriced Secrets Manager line. Run B's are execution too. A third run per seed would show whether B's 85 is noise or a trend.
