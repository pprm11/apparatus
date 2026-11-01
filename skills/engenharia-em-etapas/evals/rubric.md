# Rubric for a test run of engenharia-em-etapas (100 points)

The grader reads the seed, the simulated answers, every file the run wrote under `skill-test/`, its `REPORT.md`, and the skill (`SKILL.md` and `references/`). Each check scores full, half or zero points, with the quoted evidence (file and line). Half means present but with a defect a reviewer would send back.

| # | Check | Points |
|---|---|---|
| C1 | Six stage documents plus a README exist, in the series order, each with a `Series:` line, written in English only (code and quoted product strings excepted) | 5 |
| C2 | Every document opens with "In one minute" that states the answer and the ask first, and has "What changed in revision N" when revised | 6 |
| C3 | Problem domain: market-standard glossary, BR#, R# in EARS with BCP 14 keywords, QS# with a sourced measure, AC# per BR, every R traces to a BR or goal, open Q# each with owner and effect of the answer | 12 |
| C4 | Questions for the owners were listed before reading the answers, and the answers are applied as "Team decision, DD/MM/YYYY" in a decisions file and in the documents; unanswered items stay Q# with owner | 6 |
| C5 | As-is: state words LIVE, STALE, ABSENT, NOT VERIFIED used in their sense; every fact tagged with a file at the commit or a NOT VERIFIED with the verifying command; constraints AS# that later stages cite; no live system was touched | 10 |
| C6 | Market study: prior art with title, publisher, URL, access date and a label (independent, vendor claim, search only); adopted/adapted/rejected table; every benchmark row used by a decision | 8 |
| C7 | Solution domain: contexts, aggregates, testable invariants I#, commands with who may issue them, policies as WHEN/IF ... THEN, a trace of every R# and AS# to a model element | 10 |
| C8 | HLA: ADRs as "We will ..." with the strongest alternative and negative consequences; cost 1-3-1 with the price list file and date and a sourced volume basis, decided; observability (logs without PII, metrics, alarms, traces); what passes and does not pass through the component | 12 |
| C9 | HLD: routes or interfaces with full request and response, data items, algorithms with exact conditions, failure modes with detection and recovery, technology choices compared and decided, a coverage table from R#, AC#, I# to a test or POC | 12 |
| C10 | POCs: each states a hypothesis and pass criterion before the result, runs locally with mocks and synthetic data, reports the measured number and the command to reproduce, and says what it leaves open | 7 |
| C11 | Sources: every number has a source in the series, a file at the commit, a price list or a dated link; code references are permalinks to lines at the commit; no invented numbers | 8 |
| C12 | Hygiene: no private conversation cited, no real personal data, no em or en dash used as a pause, one term per concept | 4 |

Pass: 85 or more, and no finding classed as a skill defect with severity blocking.

## Classifying each lost point

- **Skill defect**: the skill's instructions are missing, ambiguous or wrong for this case (name the file and line of the skill and propose the edit).
- **Execution defect**: the skill says it, the run did not do it.
- **Seed limit**: the test setup made it impossible (for example no live checks).

## Grader output (`grade.md` next to the run)

1. Score table: check, points, evidence.
2. Total and pass or fail.
3. Findings: id, check, class, severity (blocking or minor), evidence, proposed skill edit when it is a skill defect.
4. The run's own REPORT.md complaints about the skill, each judged valid or not.
