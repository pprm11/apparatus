# Agent context map

Claude Code and Codex use the private Claude home (`~/.claude`) as the live context. Codex reads a generated
`~/.codex/AGENTS.md` (`render_harness.py`); do not edit that generated file. The `self` repo composes
`CLAUDE.md` from the layer repos under the layers root.

Private memories and skills use their `level:`; unlabeled entries use the manifest default. Public persona
skills are authored in English in their own readonly repo: repository ownership identifies their layer, so
`level:` is not required. Composition adds private Portuguese aliases and local policy without altering
the source. Every layer declares its glossary in `layer.json`; `tools/lint_glossary.py` blocks undeclared
collisions.

Always loaded: `~/.claude/CLAUDE.md`, its layer globals and `harness/<harness>.md`, and
`~/.claude/rules/*.md`. Change these files only with the user's yes.

Project memories live in `~/.claude/projects/<key>/memory/`, each with a `MEMORY.md` index. Only the current
project index is loaded; read another project's index when its context is needed. Use `context-recall` to
search beyond the index and `context-ingest` for authorized memory writes and index rebuilds.

Composed procedures live in `~/.claude/skills/`; portable skills also link from `~/.codex/skills/`. Scripts
live in `~/.claude/scripts/`. Personal skills, hooks and scripts stay out of team branches and PRs; a team repo
receives only its task's scope.
