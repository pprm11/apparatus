# Public contract

What other layers, installers and the psique manifest rely on. Anything not listed here is internal and may change
in any release. Every item below is pinned in `ci/contract.json` and checked by `tests/test_contract.py`. Removing,
renaming or changing the meaning of an item is a breaking change: [GOVERNANCE.md](../GOVERNANCE.md) applies.
Adding an item is a minor change.

Regenerate the machine-readable snapshot after an additive change with `python -I ci/contract_snapshot.py --write`.

## 1. `layer.json` schema

The v1 layout keeps the superego layer in `superego/`, with `superego/layer.json`.
Persona, collective, ego and id keep `layer.json` at their repo root.
Keys (the set accepted by the `layer-contract` gate in
`ci/repo_gates.py`): `level`, `name`, `globals`, `rules`, `dirs`, `files`, `sealed`, `glossary`, `inbox`, `mode`,
`company`, `install_exclude`. Meaning and types are documented in the header of `tools/layers.py`. `level` is one
of `superego`, `persona`, `collective`, `ego`, `id`.
Superego globals live in `superego/global/`, and rules in `superego/rules/`.
Other layers keep `global/` and `rules/` at their repo root. Descriptor paths are relative to the layer folder.

## 2. Manifest (`templates/psique/manifest.json`)

Top-level keys: `id`, `default_level`, `claude_home`, `runner`, `layers`. Each entry of `layers` may carry `level`,
`path`, `repo`, `active`, `mode` and `ref`. The per-layer byte budgets live under `budgets`, keyed `superego`, `persona`,
`collective`, `ego`, `id`, `adapter`, `root` (`tools/context_budget.py`).

The superego layer path is `<apparatus>/superego`.
Old manifests pointing at the repo root still work. The loader finds the nested folder.

## 3. Template layout

The files under `templates/` listed in `ci/contract.json` (`template_files`): the four layer templates
(`collective`, `ego`, `id`, `psique`), their `layer.json`, `README.md` and starter files. Placeholders are
`<company>`, `<team>` and `<project-key>`, each documented in the template README. A template file may be
added; moving or deleting one breaks the installer.

## 4. Installer and tools: commands and flags

Entry points run as `python -I tools/<name>.py`. The command and flag lists below are the contract; defaults and
output text are not, except where stated in `--help`.

| Tool | Commands | Flags (top level) |
|---|---|---|
| `onboard.py` | `init`, `restore`, `update`, `doctor`, `jobs`, `vault`, `contribute`, `uninstall` | `--claude-home`, `--codex-home`; each command has its own flags (see `ci/contract.json`) |
| `layers.py` | `plan`, `export`, `unlabeled`, `pull` | `--manifest`, `--claude-home`, `--level`, `--all`, `--dry-run` |
| `compose.py` | | `--manifest`, `--claude-home`, `--codex-home`, `--dry-run`, `--company`, `--out`, `--companies`, `--codes` |
| `context_budget.py` | | `--manifest`, `--claude-home`, `--json`, `--inbox`, `--repo`, `--base` |
| `render_harness.py` | | `--claude-home`, `--codex-home`, `--dry-run`, `--max-bytes`, `--manifest`, `--company`, `--companies`, `--codes` |
| `privacy.py` | `scan` | `--allow-word`, `--json` |
| `bootstrap.py` | | `--psique`, `--manifest`, `--dry-run`, `--step`, `--with-jobs`, `--json` |
| `doctor.py` | | `--manifest`, `--json` |
| `roots.py` | | `--root` |
| `migrate.py` | | `--root`, `--manifest`, `--claude-home`, `--apply`, `--repos` |

Exit codes: `0` success; non-zero failure. `doctor.py --json` and `bootstrap-state.json` carry `schema_version`;
a field of those documents is removed only in a major release.

Layers root: every tool that reads the manifest resolves the folder that holds the layer repos in this order:
`--root DIR`, the `PSIQUE_ROOT` environment variable, the parent of the superego checkout. A layer `path` in a
manifest may be absolute, `~/...`, or relative to that root. `sync.sh` follows the same order (`SYNC_MANIFEST`
overrides the manifest path).

## 5. Paths other layers read

In v1, layer files are `superego/layer.json`, `superego/harness/skills.json`,
`superego/harness/claude.md`, `superego/harness/codex.md`, and the files named in `superego/layer.json`
(`superego/global/*.md`, `superego/rules/*.md`, `superego/scripts/*` listed under `files`).
`ci/privacy-terms.json` and the tool entry points of section 4 stay at the repo root.
The full list is `read_paths` in `ci/contract.json`.
Old manifests pointing at the repo root still work. The loader finds the nested folder.

## 6. Rule and skill identifiers

Other layers cite superego rules by file name (the `globals` and `rules` entries of `superego/layer.json`) and skills by
directory name under `superego/skills/` (the `skills` list in `ci/contract.json`). These names are stable. Rewording a rule
is not a contract change; renaming or deleting its file or skill is.

## Not part of the contract

Everything under `tools/` that is not listed in section 4, helper modules, the exact text of rules and skills,
`ci/` internals, `docs/` other than this file, and the contents of `evals/`.
