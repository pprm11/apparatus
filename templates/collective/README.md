# collective-<team> (template)

Skeleton of a team layer ("collective") of the agent context: the terms and rules a whole team shares,
loaded between `superego` and each person's `ego`. People consume it read-only (`"mode": "readonly"` in
`layer.json`); changes go through a PR in the team repo, never through the hourly sync of a person.

Start a new one (the usual way is `tools/onboard.py init --new-collective NAME`, which does all of this in
the person's own private repo, with the CI gates and the deny-list of other companies' terms):

1. Copy this folder to a new repo, for example `<your-folder>/collective-acme`, and run `git init`.
2. Replace `<team>` in `layer.json` (`name`, `company`) and the `{{...}}` markers in the text files
   (`{{team}}`, `{{github}}`, `{{iso}}`, `{{review}}`). Fill the glossary in the fixed format: a `Version:` line, the
   sections `## Collisions`, `## Standard terms` and `## How to read requests`. `tools/lint_glossary.py` checks it.
3. Add the repo to `psique/manifest.json` between `superego` and the `ego` layers:
   `{"level": "collective", "name": "<team>", "path": "<your-folder>/collective-acme", "repo": "...", "active": true}`.
4. Run `tools/compose.py` to regenerate `~/.claude/CLAUDE.md`. The team glossary is always loaded, so keep
   it to a few KiB; a term that already exists in the superego glossary with the same meaning is a duplicate
   (the lint warns) and should live in one place only.
