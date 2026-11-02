# apparatus

The program for a layered agent context for Claude Code and Codex. Its superego layer lives in `superego/`
and holds universal agent rules, generic skills and harness adapters. The repository root holds the tooling,
templates for other layers and CI gates that keep company and personal content out.

Naming: this program is `apparatus`; the public repository has snapshot history (see
[Public mirror](docs/public-mirror.md)). The other repos were renamed too (`psique` to `self`, `id-context` to `id`);
`tools/migrate.py` maps every old name.

## The layers

An agent reads a stack of layers. Superego lives in this repo at `superego/`. Other layers have their own repos.
The `self` repo holds `manifest.json`, which lists the layers in load order. `tools/onboard.py` installs the stack.
`~/.claude` stays the source of truth; Codex gets a rendered copy.

| Level | What it holds | Who owns it |
|---|---|---|
| superego | universal rules, glossary, harness adapters and generic skills (`superego/` in this repo) | the maintainers |
| persona | opt-in working practices of one person, published on purpose | that person |
| collective | terms and rules one team shares, read-only for members | the team |
| ego | one company or project: memories, glossary, rules, plans | the person, private |
| id | the person: preferences, development plan, sealed secrets | the person, private |

Precedence in a conflict, strongest first: id, ego, collective, persona, superego. A memory or skill picks its
layer with `level:` in its frontmatter. `superego/layer.json` lists what superego owns outside memories and skills.
Other layers keep `layer.json` at their repo root. The manifest path for superego is `<apparatus>/superego`.
Old manifests pointing at the repo root still work. The loader finds the nested folder.
Details: [docs/operations.md](docs/operations.md).

## Quick start

Needs Python 3.10+, Git and a Claude Code or Codex install.

    git clone https://github.com/<user>/apparatus <your-folder>/apparatus
    <your-folder>/apparatus/install.sh          # macOS, Linux
    <your-folder>/apparatus/install.ps1         # Windows

The installer finds Python and runs `tools/onboard.py init`, which creates your private `self` and `id` repos
from `templates/`, restores the layers into `~/.claude`, composes `CLAUDE.md` and `AGENTS.md`, registers an
update job and runs the doctor. Check the result any time:

    python -I tools/onboard.py doctor

The folder that holds the layer repos is configurable with `--root` or `PSIQUE_ROOT`. Full guide:
[docs/install.md](docs/install.md).

## Repository map

| Path | What it is |
|---|---|
| `tools/` | Python command line tools: layers, compose, onboard, search, lint, decay, learn, scheduler |
| `tests/` | offline test suite and the contract test |
| `ci/` | CI gates, deny list, contract snapshot (`python -I ci/gates.py`) |
| `superego/` | the superego layer: universal agent rules, glossary, harness adapters, generic skills and hook scripts |
| `prompts/` | prompt texts for the unattended harvest, weekly and learning passes |
| `templates/` | starting points for persona, collective, ego, id and the meta repo |
| `kits/` | files a new collective repo receives (gates, hooks, CODEOWNERS) |
| `docs/` | contract, CI gates, cross-OS notes, release steps, operations, install guide |
| `sync.sh`, `harvest.sh`, `weekly.sh`, `restore.sh` | the hourly sync, session harvest, weekly pass and restore |
| `install.*`, `bootstrap.*` | installer and machine bootstrap entry points |

Text in `superego/global/`, `superego/rules/` and `superego/harness/` is loaded into every agent session. It has a size budget
(`tools/context_budget.py`), so detail goes to a skill or a doc.

## Documents

- [GOVERNANCE.md](GOVERNANCE.md): what belongs here, versioning, deprecation, the change bar.
- [docs/contract.md](docs/contract.md): the public contract other layers rely on.
- [CHANGELOG.md](CHANGELOG.md): what changed, by release.
- [docs/install.md](docs/install.md): installation.
- [docs/operations.md](docs/operations.md): routines, restore, search, decision inbox, learning loop.
- [docs/ci-gates.md](docs/ci-gates.md), [docs/cross-os.md](docs/cross-os.md), [docs/release.md](docs/release.md).

## Checks

    python -I -m unittest discover -s tests    # offline test suite
    python -I ci/gates.py                      # every gate, including the suite and the contract test

Every pull request needs a green local run and a CHANGELOG line. Hourly and weekly routines, restore on a
new machine, the self-learning loop and the secret backup are described in
[docs/operations.md](docs/operations.md).
