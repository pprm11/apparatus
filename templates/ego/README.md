# ego-<company> (template)

Skeleton of the "ego" layer: YOUR own application of a collective (one company). It is private and lives in
your account. It holds your notes, preferences and work context for that company: project memories, work skills,
your glossary additions, rules, maps and plans, and your decision-inbox items. What the team shares lives in the
collective, the only shared content layer. `tools/onboard.py init` creates one ego per attached collective from
this template; leaving a company means archiving or deleting this repo, the other layers stay.

Start a new one:

1. Copy this folder to a new repo, for example `<your-folder>/ego-acme`, and run `git init`.
2. Rename `global/glossario-empresa.md` to `glossario-<company>.md` and `global/regras-empresa.md` to
   `regras-<company>.md` (lowercase, no spaces), and replace `<company>` in `layer.json`: `name`, and the two
   names in `globals`. Add `rules`, `dirs` (for example `maps`, `plans`) and `files` as the company needs them.
3. Add the repo to `psique/manifest.json`, after `superego` and before `id`:
   `{"level": "ego", "name": "<company>", "path": "<your-folder>/ego-acme", "repo": "git@github.com:<user>/ego-acme.git", "active": true}`.
   Keep only one ego layer active at a time, since memories without `level:` go to the active ego.
4. Rename `memory/project-key/` to the key of a real project (the project path with `:`, `\` and `/`
   replaced by `-`) and keep its `MEMORY.md` as the index. Put the glossary and rules files in `~/.claude` under the same names, label memories and skills with
   `level: ego` in their frontmatter, run `superego/sync.sh --push`, then `tools/compose.py` to regenerate
   `~/.claude/CLAUDE.md`.

Leaving a company: set `"active": false` for its layer in the manifest, run `tools/compose.py`, and hand
over, archive or delete the repo.
