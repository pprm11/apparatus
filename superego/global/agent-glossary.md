# Agent glossary (superego level)

Version: v2.0, 2026-11-01. Every layer has a glossary in this format (the `glossary` field of `layer.json`),
loaded in the order superego, persona, collective, ego, id. On conflict the more specific layer wins.

## Rules of use

1. Use the standard term of the glossary, even when the user writes another one.
2. Correct only if the term, read two ways, would change the action.
   - At the start: "You said X; I understood Y (standard: Z)." One per answer.
   - If the action is irreversible or external, ask first.
3. Do not correct a harmless synonym, accent, case, typo, nickname or pasted text.
4. Identifiers stay as they are: branches, repos, tools, cloud profiles, code.
5. A new concept or a changed term: ask "Add/change X in the glossary?"; edit after the yes, with a new version.

## Collisions (same word, different things)

| Word | Senses | Standard term |
|---|---|---|
| harness | the gates, guides and sensors of a repo · the coding agent that runs the session | **repo harness** · **harness** |
| agent | a coding agent (Claude Code, Codex) · an agent a session launches · an agent inside a product | **harness** · **subagent** · **agent** |
| dev | an environment · a machine · a person | **dev** · **local** · **developer** |
| rule | an engineering rule (lint, CI, review) · a business rule of a product | **engineering rule** · **business rule** |

## Standard terms

### Context layers
- **superego**: general agent rules, the same for anyone; norms internalized from the culture. **persona**:
  one person's opinionated, public, opt-in practices; the public face. **collective**: what a team shares, the
  only shared content layer (shared consciousness of a group, in the sense of Durkheim, not Jung's collective
  unconscious). **ego**: one person's application of a collective, such as a company, which mediates with
  reality. **id**: the person, private. **self**: the repo that holds the **manifest** (`manifest.json`) listing
  the layers and generating `CLAUDE.md`; the whole system is the **psique**. **layer**: one of these repos.
  **level**: the `level:` of a memory or skill, which names its layer. Precedence, strongest first: id, ego,
  collective, persona, superego.

### Work and decision
- **task** (T#): a unit of work. **card**: the text of a task. **ticket**: the record of a task in the tracker.
- **wave**: a batch of tasks by dependency, without a date. **round**: one review pass of a wave. **run**: one
  execution of a workflow. **plan**: a document with what, why and waves. **backlog**: tasks outside any wave.
- **acceptance criterion**: an observable sign of done. **blocker**: depends on another person or system.
  **open item**: something still pending.
- **Q# / D# / I#**: open question / decision / idea. **decision matrix**: options against criteria (includes 1-3-1).
- **Ishikawa**: causes of a problem in six categories, with whys down to a proven root. **root cause**: the cause
  whose removal keeps the problem from returning. **containment**: a patch on the symptom until the root is out.
  **guard**: a lint, test or rule that keeps the problem from returning.

### Test and quality
- **test**: offline, no model. **eval**: a suite with a real model. **eval gate**: the subset of the eval that
  blocks a PR. **gate**: a check that blocks a merge. **judge**: an LLM that scores an answer.
- **TDD**: a failing test first, the smallest change that passes, then refactor. **CRAP**: CC² × (1 − coverage)³
  + CC per function, ceiling 10. **surviving mutant**: a mutation of the code that no test catches.

### Sessions and deliverables
- **session**: one conversation in Claude Code or Codex. **subagent**: an agent a session launches.
  **handoff**: text to continue in another session. **compact**: `/compact`. Models are always named.
- **artifact**: a page published on claude.ai. **report**: a written analysis, publishable as an artifact.
  **widget**: an inline visual answer.

## How to read requests
- **deploy**: take a version to an environment. **run local**: start a server on the machine. **run**: execute a
  test or script. **publish**: an artifact or document.
