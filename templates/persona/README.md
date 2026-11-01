# persona (template)

Skeleton of a persona layer: one person's opinionated working practices, published on purpose and opt-in.
It loads after `superego` and before `collective`, so a team, a company or the person can override it.
Precedence, strongest first: `id`, `ego`, `collective`, `persona`, `superego`.

The name comes from Jung: the public face a person shows. Nothing private lives here; that is `id`.

Start one:

1. Copy this folder to a new repo and run `git init`.
2. Write your practices in `global/practices.md` and your skills in `skills/<name>/SKILL.md` with `level: persona`.
3. Add the repo to the `self` manifest between `superego` and `collective`:
   `{"level": "persona", "name": "persona", "path": "persona", "repo": "...", "active": true}`.
4. Run `tools/compose.py` to regenerate `~/.claude/CLAUDE.md`, and keep the always-loaded files inside the
   `persona` byte budget of the manifest (`tools/context_budget.py`).
