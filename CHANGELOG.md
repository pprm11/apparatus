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
  without `--apply`; repo URLs change only with `--repos`, after the new repository exists.

### Pre-1.0 rename map

| Kind | Old | New |
|---|---|---|
| repo | `psique` | `self` |
| repo | `id-context` | `id` |
| repo | `superego` | `apparatus` (new repository, fresh history) |

Later stages add file and skill rows to `tools/renames.json` and to this table.

- Configurable layers root: `--root DIR`, the `PSIQUE_ROOT` environment variable, or the folder that holds the
  superego checkout (`tools/roots.py`). The manifest defaults to `<root>/psique/manifest.json`; layer paths in a
  manifest may be relative to the root. Existing manifests with absolute or `~/Codes/...` paths keep working.
- `GOVERNANCE.md`: what belongs in superego, semantic versioning, the deprecation window and the change bar.
- `docs/contract.md` and `ci/contract.json`: the public contract and its machine-readable snapshot.
- `tests/test_contract.py`: fails on a removed or renamed contract item, and on a person or company identifier in
  tracked files. `ci/contract_snapshot.py` builds and checks the snapshot.
- `docs/release.md`: release steps and the rule for consumers that follow `main`.

No release has been tagged yet. The first tag, `v1.0.0`, declares the contract stable.
