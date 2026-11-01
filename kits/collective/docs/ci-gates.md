# CI gates of the collective ({{team}})

Same runner as the other agent-context repos: `python -I ci/gates.py` (`--list`, `--only a,b`, `--staged`,
`--strict`). Settings are in `ci/config.json`; the collective-only gates are in `ci/repo_gates.py`, with tests in
`ci/test_gates.py`. Install the local hooks with `python -I ci/install-hooks.py`.

This repo is read by several people's agents and crosses a company boundary, so the gates guard four things:
nothing personal or confidential gets in, nothing from another company or its clients gets in, nothing in it can
steer an agent behind the user's back, and what is always loaded stays small.

## Collective gates

### `registry`

- Checks: every file under `global/` and `rules/` and every skill folder has an entry in `registry.json`
  with `owner`, `source`, `created`, `review_by` (ISO date), `status` (`draft`, `stable`, `deprecated`) and
  `locked` (true or false); a deprecated entry has `superseded_by`; skill folders are `collective-<name>` with
  `name:` equal to the folder and `level: collective`; no entry points at a missing file.
- Why: an item with no owner and no review date cannot be revalidated, so stale rules stay forever.
- Waive: none. Fix the registry.

### `injection`

- Checks: no invisible Unicode, no base64 blob of 120 characters or more, no download-and-run line
  (`curl | sh`, `Invoke-Expression`), no phrase that hides things from the user ("do not tell the user",
  "ignore previous instructions") in `global/`, `rules/` or `skills/`.
- Why: every agent loads this text. Studies of public skill registries found malicious skills and prompt
  injection (arXiv 2602.06547; Snyk ToxicSkills); a private repo has the same exposure through one careless
  PR.
- Waive: none. A real command belongs in a script under the skill, reviewed line by line by the skills owner.

### `redaction`

- Checks: e-mail addresses, IPv4 addresses (except loopback and the documentation ranges), CPF, CNPJ,
  Brazilian phone numbers and ids of 32 or more hex characters in any tracked file outside `ci/`.
- Why: these are the identifiers `redact.py` removes before text leaves a person's context. They show up when a
  memory or a transcript is copied in.
- Waive: rewrite the example (`user@example.org` is still an e-mail: use a description instead).

### `no-personal-data`

- Checks: none of the terms in the private list of people and chats appear in any tracked file outside `ci/`
  (whole words only). The list comes from the repository variable `COLLECTIVE_DENY_TERMS` (comma separated) in
  CI and from `.denylist.local` (one term per line, git-ignored) on a machine. A match prints the file, never
  the term.
- Why: names cannot be a pattern in the repo, because the pattern would be the leak.
- Waive: none. In CI without the variable the gate warns.

### `no-company-data`

- Checks: none of the terms of the other companies and their clients, products, internal repositories and
  domains appear in any tracked file outside `ci/`. The list comes from the repository variable
  `COLLECTIVE_DENY_COMPANIES` in CI and from `.denylist.companies.local` (git-ignored) on a machine. Whole words,
  case-insensitive; a match prints the file, never the term.
- Why: this collective is shared with people who work for another company. Material from that company must not
  cross. The list is not in the repo for the same reason.
- Waive: none. In CI without the variable the gate is an error, because without the list it checks nothing.

### `generated-files`

- Checks: no `AGENTS.md`, `CLAUDE.md`, `MEMORY.md`, `*.age`, caches, lint reports or decision files, no folder
  such as `memory/`, `projects/`, `sealed/`, and no file whose first lines carry a generator marker.
- Why: generated output is rebuilt from sources and, copied in, is loaded twice or carries another layer's data.

### `budget`

- Checks: `global/` plus `rules/` markdown is at most `collective.budget_bytes` (3,600) in total.
- Why: those files load into every session and are inlined into the Codex `AGENTS.md`, which Codex stops
  reading at 32 KiB and which every layer shares. Detail goes in a skill, which loads on demand.
- Waive: raise the number in `ci/config.json` only after the owner of another layer moves the same amount out.

### `glossary-format`

- Checks: `global/glossary.md` starts with `# Glossário compartilhado (nível collective)`, has no
  frontmatter, only `#` and `##` headings, a collisions table with the 3-column header
  `| Palavra | Sentidos | Termo padrão |`, rows with exactly 3 columns, every list item defines a **term** in bold,
  no term is defined twice, and the file ends with a newline.
- Why: the glossary is imported as plain text by Claude Code and inlined for Codex. A broken table or a duplicated
  term makes the ubiquitous language ambiguous, and it is the same format as the glossaries of the other layers.

## Shared gates

`eol`, `size`, `paths`, `text`, `exec-bit`, `tests`, `python`, `shell`, `md-basic`, `links`, `mdlint`,
`skill-schema` (skills only), `secrets`, `deny` (machine paths, private workspace URLs) and `commit-title` come
from `ci/gates.py` and are described in the psique repo's `docs/ci-gates.md`. `memory-schema` is disabled: the collective has no memories.

## Jobs

`gates` (all gates, strict), `gitleaks` (whole history, pinned binary), `pr-title` (Conventional Commits) and
`windows` (the gates that must hold on Windows). Turn on branch protection with required reviews from code
owners and these four checks before inviting anyone with write access.
