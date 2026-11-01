# Changelog

All notable changes to the public contract and to superego itself are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) over the contract in [docs/contract.md](docs/contract.md).
Process: [docs/release.md](docs/release.md).

## [Unreleased]

### Added

- `persona` level: opinionated, opt-in practices that load after `superego` and before `collective`
  (`templates/persona`, `layers.LEVELS`, compose order and titles, glossary lint order). Precedence, strongest
  first: `id`, `ego`, `collective`, `persona`, `superego`. A manifest `budgets.persona` key bounds its
  always-loaded files.
- `tools/migrate.py` and `tools/renames.json`: the old to new map of the pre-1.0 rename (below) and a one-time,
  idempotent migration of file names, skill folders, `@imports` and manifest repo URLs. It writes nothing
  without `--apply`; repo URLs change only with `--repos`, after the new repository exists. `--prune` also deletes
  retired files and stale duplicates. The installer (`init`, `restore`, `update`) runs it with pruning before every
  compose, so an install made before the rename migrates itself and prints each step.

### Changed (pre-1.0 rename, stage 2)

- The superego layer now holds only universal text, in English: `global/agent-rules.md` (was `regras-de-agente.md`),
  `global/agent-glossary.md` (was `glossario-agente.md`), `rules/context-map.md` (was `mapa-do-contexto.md`).
  `harness/claude.md` and `harness/codex.md` are generic; personal model names and standards moved out.
- `tools/lint_glossary.py` accepts English headings and ISO dates next to the Portuguese ones, so layers that have
  not been translated yet still pass.

### Changed (pre-1.0 rename, stage 3: English tree)

- All text, comments, messages, prompts, hook output, docs and tests are English. Portuguese stays only as data
  the tools need (keyword lists that match what users type, legacy names the migration maps). `tests/test_english_only.py`
  fails on Portuguese in file names or text, with a short, reasoned allowlist.
- `docs/instalar.pt-BR.md` is now `docs/install.md` (English). The README is a five-minute overview and every top
  folder has a README; the long operations text moved to `docs/operations.md`.
- Template files and placeholders: `glossario-empresa.md` to `glossary-company.md`, `regras-empresa.md` to
  `rules-company.md`, `padroes-do-usuario.md` to `preferences.md`, `linguagem-do-usuario.md` to `personal-glossary.md`,
  `chave-do-projeto` to `project-key`. A new ego layer is written as `glossary-<team>.md` and `rules-<team>.md`.
- The generated `CLAUDE.md` header and layer titles are English. The installer still recognizes the old header, so
  an install made before the rename does not back up its own generated file as a foreign one.
- The collective kit's glossary gate expects the English title and table header.

### Deprecated

- The `#segredo-ok` override of the prompt guard still works and is removed in the next major; use `#secret-ok`.

### Changed (pre-1.0 rename, stage 4: nested layer)

- The superego layer moved into `superego/` (`layer.json`, `global/`, `rules/`, `harness/`, `skills/`, `scripts/`);
  the repo root keeps the program. This is the layout the v1 contract describes.
- A manifest from before the move, whose superego `path` is the repo root, still works: the loader finds
  `superego/layer.json`. New manifests and `onboard.py init` write `<apparatus>/superego`.
- `layers.repo_root()` finds the git checkout of a layer, so pulls and `contribute` work from the nested folder.
- Owner's note: set the superego layer to `"mode": "readonly"` in the manifest so the hourly export never writes
  into it; the generic text then changes through pull requests only.

### Removed (pre-1.0 rename, stage 2)

- Skills that are opinionated practices moved to the opt-in `persona` layer, translated and renamed:
  `causa-raiz` to `root-cause`, `code-review-critico` to `critical-code-review`, `orquestrar-cruzado` to
  `cross-harness-orchestration`, `orquestrar-sonnet-haiku` to `claude-workflow-orchestration`, `telinhas` to
  `inline-widgets`, `engenharia-em-etapas` to `staged-engineering`; `humanize` and `ub-mode` keep their names.
- `rules/agentes-e-sessoes.md` and `rules/uso-de-ia.md`: their content is in persona `practices.md`.
- `skills/neon` and `skills/neon-postgres`: third-party text; install the Neon plugin instead.
- `tools/migrate.py --apply` renames the files and skill folders in an existing install and removes the retired
  ones once the persona layer is active; the full table is in `tools/renames.json`.

### Pre-1.0 rename map

| Kind | Old | New |
|---|---|---|
| repo | `psique` | `self` |
| repo | `id-context` | `id` |
| repo | `superego` | `apparatus` (new repository, fresh history) |
| file | `regras-de-agente.md` | `agent-rules.md` |
| file | `glossario-agente.md` | `agent-glossary.md` |
| file | `rules/mapa-do-contexto.md` | `rules/context-map.md` |
| skill | `causa-raiz` | `root-cause` |
| skill | `code-review-critico` | `critical-code-review` |
| skill | `orquestrar-cruzado` | `cross-harness-orchestration` |
| skill | `orquestrar-sonnet-haiku` | `claude-workflow-orchestration` |
| skill | `telinhas` | `inline-widgets` |
| skill | `engenharia-em-etapas` | `staged-engineering` |

Later stages add rows to `tools/renames.json` and to this table.

- Configurable layers root: `--root DIR`, the `PSIQUE_ROOT` environment variable, or the folder that holds the
  superego checkout (`tools/roots.py`). The manifest defaults to `<root>/psique/manifest.json`; layer paths in a
  manifest may be relative to the root. Existing manifests with absolute or `~/Codes/...` paths keep working.
- `GOVERNANCE.md`: what belongs in superego, semantic versioning, the deprecation window and the change bar.
- `docs/contract.md` and `ci/contract.json`: the public contract and its machine-readable snapshot.
- `tests/test_contract.py`: fails on a removed or renamed contract item, and on a person or company identifier in
  tracked files. `ci/contract_snapshot.py` builds and checks the snapshot.
- `docs/release.md`: release steps and the rule for consumers that follow `main`.

No release has been tagged yet. The first tag, `v1.0.0`, declares the contract stable.
