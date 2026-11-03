# Changelog

All notable changes to the public contract and to superego itself are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) over the contract in [docs/contract.md](docs/contract.md).
Process: [docs/release.md](docs/release.md).

## [Unreleased]

### Added (local search)

- Reviewed auxiliary sources through optional per-home `search-sources.json` and layer-owned fragments: root guidance and skill
  references join the lexical index, invalidate its cache on configuration changes, and reject stale or
  escaping references. Search evaluation supports exact source paths and reports missing gold separately.
- Source discovery and local index I/O reach Windows directories beyond MAX_PATH, including a long selected home.

### Fixed (sync)

- `pull` skips a readonly layer whose checkout is not on its default branch (for example a review worktree) with a
  one-line warning instead of aborting the whole sync; other layers still sync. It never switches branches.

### Fixed (migrate)

- `tools/migrate.py` no longer renames or prunes a skill whose own `level:` is ego, id or collective (a person's
  skill of the same name as a renamed shared one), nor a retired rule that a layer of the person lists in its
  `layer.json`. The two retired rules now point to "your own layer", since persona does not ship them.
- The live-home budget test ignores pending repository rows (they depend on the remote, not on the home).

### Changed (pre-1.0 rename, stage 5: public name)

- The public mirror repository is `apparatus` (was `superego-public`); install and mirror docs use it. The private
  working repo keeps the name `superego`. The migration map already sends `superego` to `apparatus`.
- `docs/public-mirror.md` no longer points at the removed Portuguese install guide.
- Default names of a person's repos are `self` (the manifest repo, was `psique`) and `id` (was `id-context`);
  `templates/psique` is now `templates/self`. Flags `--self-repo` and `--self` replace `--psique-repo` and
  `--psique`; the old flags still work, hidden, for one minor release. The default manifest path is
  `<root>/self/manifest.json` and falls back to `<root>/psique/manifest.json` when only that exists
  (`roots.default_manifest`, shell `default_manifest`). `~/.config/id-context` keeps its name so existing
  recipients keep working.

### Fixed (artifact-routing skill)

- The repository privacy gate (`tests/test_onboard.py`) failed on the skill's own synthetic fixtures in
  `tests/test_privacy_scan.py` and on an example in `scripts/privacy_scan.py`; the fixtures are now built from
  pieces at run time and the example is described in words, so `main` is green again.
- `reader.js` no longer scrolls the page to the tab bar on load (it scrolled when the default tab was not
  visible); the tab bar now scrolls only sideways.
- `reader.js` UI text follows the page language: `pt*` gets Portuguese, anything else English, and
  `data-reader-strings` overrides. Figure captions may start with `Figure:` or `Figura:`. New test
  `tests/test_reader_i18n.py`.
- The default tab is the one marked `aria-selected="true"`, wherever it sits in the bar (`SKILL.md`,
  `reader-page.md`, `shell.html` said both "first tab" and "keep the Diataxis order").
- `scripts/svg_gate.py` and a "Hand-drawn SVG figures" section in `diagrams.md`, ported from the personal
  skill this one replaces: a label that runs past its box or the viewBox fails the gate. New test
  `tests/test_svg_gate.py`.
- `quality-gates.md` adds a Complete check: each tab is walked through its type's Content depth list, because a
  cold reader and an adversarial reviewer both pass a page that is right but thin.

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
# Changelog

All notable changes to the public contract and to superego itself are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) over the contract in [docs/contract.md](docs/contract.md).
Process: [docs/release.md](docs/release.md).

## [Unreleased]

### Contract change: schema 2

- Core now supplies the runtime, while readonly persona supplies the reusable `context-ingest`, `context-recall` and `secret-backup` procedures. In a composed home the first two canonical invocations remain available and `vault` routes to `secret-backup` through private alias configuration. This moves the schema 1 core-directory contract to the `composed_skills` contract and requires a coordinated release; a missing persona target is rejected.

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
